"""Optional illustrated/anime NSFW classifier.

NudeNet is an anatomy detector trained on photographs, so it can miss
illustrated content (anime, hentai, drawings, 3D renders). This detector adds
a whole-image NSFW classifier that fires on overall composition rather than
specific body parts, which complements NudeNet on stylized content.

Model: Falconsai/nsfw_image_detection, a ViT-base image classifier with two
labels, "normal" and "nsfw". It is a general NSFW classifier (the most widely
used one on the Hub), not anime-specialized, but being a whole-image model it
catches stylized content NudeNet's anatomy detector skips.

Design choices:

- Explicit install. Scanning never auto-downloads the model; the app fetches
  it only when the user opts in. We download ONLY the three files inference
  needs (config, safetensors weights, preprocessor config) pinned to a known
  revision, not the repo's training artifacts.
- Self-contained inference. We load the model directly and preprocess with
  PIL + NumPy, so torchvision is NOT required and the heavyweight transformers
  `pipeline` is avoided. Weights are dynamically INT8-quantized at load for a
  ~1.8x CPU speedup at negligible accuracy cost, and torch threads are capped.
- Optional dependency. If transformers/torch are missing the detector returns
  negative and NudeNet keeps working alone.
- Context only. In the beta it only ever produces context-severity hits; the
  watcher decides escalation per mode.
"""
from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
from PIL import Image

from brake import paths
from brake.config import NudityConfig
from brake.detectors.base import Detector, DetectionResult

_log = logging.getLogger(__name__)

MODEL_NAME = "Falconsai/nsfw_image_detection"
# Pin a known-good revision: reproducible installs and a supply-chain anchor
# so a future repo change cannot silently alter what users download/run.
MODEL_REVISION = "04367978d3474804ab1a00a9bd6548b741764069"
MODEL_DIR_NAME = "anime_nsfw_falconsai"

# Only the files inference needs. Excludes optimizer.pt (~686MB training
# state), pytorch_model.bin (~343MB duplicate of safetensors), and an
# unrelated bundled YOLO model (~87MB). Cuts the download from ~1.46GB to
# ~343MB.
_ALLOW_PATTERNS = ["config.json", "model.safetensors", "preprocessor_config.json"]

# Detector trigger floor. Kept equal to the lowest per-mode threshold the
# watcher applies (ANIME_STRICT_CONTEXT_CONFIDENCE), so the detector never
# pre-suppresses a score that strict mode would still act on. The watcher
# re-applies the mode-specific threshold on top of this.
CONTEXT_THRESHOLD = 0.86

_TORCH_THREADS = 2
_DEFAULT_EDGE = 224
# PIL resample code -> filter. ViTImageProcessor uses resample=2 (BILINEAR).
_RESAMPLE = {0: Image.NEAREST, 1: Image.LANCZOS, 2: Image.BILINEAR, 3: Image.BICUBIC, 4: Image.BOX, 5: Image.HAMMING}

_warned_missing_deps = False


def model_dir() -> Path:
    return paths.models_dir() / MODEL_DIR_NAME


def dependencies_available() -> bool:
    return (
        importlib.util.find_spec("transformers") is not None
        and importlib.util.find_spec("torch") is not None
    )


def model_installed() -> bool:
    root = model_dir()
    if not root.exists():
        return False
    has_config = (root / "config.json").exists()
    has_processor = (
        (root / "preprocessor_config.json").exists()
        or (root / "image_processor_config.json").exists()
    )
    # safetensors is what we fetch; .bin is accepted only for older installs.
    has_weights = any(root.glob("*.safetensors")) or any(root.glob("*.bin"))
    return has_config and has_processor and has_weights


def anime_model_status() -> str:
    if not dependencies_available():
        return "missing_dependencies"
    if not model_installed():
        return "not_installed"
    return "ready"


def download_model() -> None:
    if not dependencies_available():
        raise RuntimeError("missing_dependencies")
    try:
        from huggingface_hub import snapshot_download  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError("missing_dependencies") from exc

    target = model_dir()
    target.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id=MODEL_NAME,
        revision=MODEL_REVISION,
        local_dir=str(target),
        allow_patterns=_ALLOW_PATTERNS,
    )
    if not model_installed():
        raise RuntimeError("model_download_incomplete")


Box = Tuple[int, int, int, int]


class AnimeNSFWDetector(Detector):
    name = "anime_nsfw"
    # Watcher may pass profile/changed_box/zoom_region keyword hints.
    accepts_scan_hints = True

    def __init__(self, config: NudityConfig) -> None:
        self.config = config
        self._model = None
        self._disabled = False
        self._nsfw_index = 1
        self._edge = _DEFAULT_EDGE
        self._resample = Image.BILINEAR
        self._mean = np.array([0.5, 0.5, 0.5], dtype=np.float32)
        self._std = np.array([0.5, 0.5, 0.5], dtype=np.float32)

    def _ensure_loaded(self) -> bool:
        global _warned_missing_deps
        if self._disabled:
            return False
        if self._model is not None:
            return True
        try:
            import torch  # type: ignore[import-not-found]
            from transformers import AutoModelForImageClassification  # type: ignore[import-not-found]
        except ImportError:
            if not _warned_missing_deps:
                _log.warning(
                    "anime_nsfw detector: transformers/torch not installed; "
                    "illustrated-content detection disabled."
                )
                _warned_missing_deps = True
            self._disabled = True
            return False
        if not model_installed():
            _log.info("anime_nsfw detector: model is not installed; skipping.")
            return False
        try:
            # Heaviest model in the pipeline: cap threads so it does not fan
            # across every core (measured: no wall-time gain, far more CPU).
            torch.set_num_threads(_TORCH_THREADS)
            _log.info("Loading %s from %s (one-time, ~15s)...", MODEL_NAME, model_dir())
            model = AutoModelForImageClassification.from_pretrained(str(model_dir()))
            model.eval()
            # Dynamic INT8 quantization of the Linear layers: ~1.8x faster on
            # CPU with negligible accuracy change. Fall back to fp32 if a
            # platform lacks the qint8 kernels.
            try:
                model = torch.quantization.quantize_dynamic(
                    model, {torch.nn.Linear}, dtype=torch.qint8
                )
                _log.info("anime_nsfw: using INT8-quantized weights.")
            except Exception as e:
                _log.warning("anime_nsfw: INT8 quantization unavailable (%s); using fp32.", e)
            self._model = model
            self._torch = torch
            self._read_label_index(model)
            self._read_preprocessor()
            _log.info("anime_nsfw detector ready (edge=%d, nsfw_index=%d).", self._edge, self._nsfw_index)
            return True
        except Exception as e:
            _log.error("anime_nsfw detector failed to load: %s", e)
            self._disabled = True
            return False

    def _read_label_index(self, model) -> None:
        id2label = getattr(model.config, "id2label", None) or {}
        for idx, label in id2label.items():
            if str(label).lower() == "nsfw":
                self._nsfw_index = int(idx)
                return
        self._nsfw_index = 1  # Falconsai default ordering

    def _read_preprocessor(self) -> None:
        import json

        cfg_path = model_dir() / "preprocessor_config.json"
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception:
            return
        size = cfg.get("size") or {}
        self._edge = int(size.get("height") or size.get("shortest_edge") or _DEFAULT_EDGE)
        self._resample = _RESAMPLE.get(int(cfg.get("resample", 2)), Image.BILINEAR)
        self._mean = np.array(cfg.get("image_mean", [0.5, 0.5, 0.5]), dtype=np.float32)
        self._std = np.array(cfg.get("image_std", [0.5, 0.5, 0.5]), dtype=np.float32)

    def _regions(
        self,
        image: Image.Image,
        profile: str,
        changed_box: Optional[Box],
    ) -> List[Tuple[str, Image.Image]]:
        regions: list[tuple[str, Image.Image]] = [("full", image)]
        w, h = image.size
        # Whole-image classifier: a small illustration in a corner downscales
        # to nothing in the full view, so a center crop adds resolution there.
        # Skipped on the budget (targeted) profile to stay cheap.
        if profile != "targeted" and min(w, h) >= 500:
            cw, ch = w // 2, h // 2
            cx, cy = (w - cw) // 2, (h - ch) // 2
            regions.append(("center", image.crop((cx, cy, cx + cw, cy + ch))))
        # When we know where the screen changed, classify exactly that area.
        if changed_box is not None:
            left, top, right, bottom = (int(v) for v in changed_box)
            left = max(0, left); top = max(0, top)
            right = min(w, right); bottom = min(h, bottom)
            if right - left >= 64 and bottom - top >= 64:
                regions.append(("changed", image.crop((left, top, right, bottom))))
        return regions

    def _preprocess(self, images: List[Image.Image]):
        edge = self._edge
        arrays = [
            np.asarray(im.convert("RGB").resize((edge, edge), self._resample), dtype=np.float32) / 255.0
            for im in images
        ]
        batch = np.stack(arrays)  # (N, H, W, C)
        batch = (batch - self._mean) / self._std
        batch = np.transpose(batch, (0, 3, 1, 2))  # -> (N, C, H, W)
        return self._torch.from_numpy(np.ascontiguousarray(batch))

    def _score_regions(self, images: List[Image.Image]) -> List[float]:
        torch = self._torch
        with torch.inference_mode():
            pixel_values = self._preprocess(images)
            logits = self._model(pixel_values=pixel_values).logits
            probs = torch.softmax(logits, dim=-1)
        return [float(probs[i, self._nsfw_index]) for i in range(len(images))]

    def scan(
        self,
        image: Image.Image,
        *,
        profile: str = "full",
        changed_box: Optional[Box] = None,
        zoom_region: str = "",
    ) -> DetectionResult:
        if not self.config.enabled:
            return DetectionResult.negative(self.name)
        if not self._ensure_loaded():
            return DetectionResult.negative(self.name)

        regions = self._regions(image, profile, changed_box)
        try:
            scores = self._score_regions([img for _, img in regions])
        except Exception as e:
            _log.error("anime_nsfw scan failed: %s", e)
            return DetectionResult.negative(self.name)

        best_score = 0.0
        best_region = ""
        for (name, _img), score in zip(regions, scores):
            if score > best_score:
                best_score = score
                best_region = name

        _log.info("anime_nsfw: best=%s nsfw=%.2f regions=%d", best_region or "?", best_score, len(regions))

        if best_score >= CONTEXT_THRESHOLD:
            return DetectionResult(
                detector=self.name,
                triggered=True,
                confidence=best_score,
                label=f"POSSIBLE NSFW ART ({best_region})",
                severity="context",
                region=best_region,
            )
        return DetectionResult.negative(self.name)
