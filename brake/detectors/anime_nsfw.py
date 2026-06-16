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
  it only when the user opts in. We download ONLY the three files needed
  (config, safetensors weights, preprocessor config) pinned to a known
  revision, not the repo's training artifacts.
- ONNX runtime, not torch. The install step exports the ViT to an INT8 ONNX
  model and removes the torch weights (best-effort; freed on the next clean
  load if the OS still holds them). The long-lived agent runs the classifier
  on onnxruntime only (already a core dependency, shared with NudeNet), so
  torch and transformers are never imported in the agent. This takes the
  detector's resident memory from ~790MB (torch + INT8 quantize) down to
  ~120MB, with identical scores (measured max diff 0.0002) and the same
  per-frame speed.
- Self-contained preprocessing with PIL + NumPy (no torchvision).
- Cascade scanning. A cheap probe (whole screen + the changed/centre crop) is
  scored first; the extra corroboration crops only run when the probe looks
  possibly-NSFW, so clean screens cost one or two passes instead of three+.
- Context only. The detector emits context-severity results; the watcher
  decides escalation per mode.
"""
from __future__ import annotations

import importlib.util
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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

# Only the files needed to build the ONNX model. Excludes optimizer.pt
# (~686MB training state), pytorch_model.bin (~343MB duplicate), and an
# unrelated bundled YOLO model (~87MB).
_ALLOW_PATTERNS = ["config.json", "model.safetensors", "preprocessor_config.json"]

ONNX_INT8_NAME = "model.int8.onnx"
ONNX_FP32_NAME = "model.onnx"
# Torch weights are removed after the one-time ONNX export to save disk and to
# make clear they are not used at runtime.
_TORCH_WEIGHT_NAMES = ["model.safetensors", "pytorch_model.bin"]

# Suspicion floor. Scores here ask for another look; they do not lock.
CONTEXT_THRESHOLD = 0.86
# Whole-image NSFW classifiers are vulnerable to stylized game frames. A real
# illustrated hit must be corroborated by another region/crop before the
# watcher is allowed to treat it as explicit.
TRIGGER_THRESHOLD = 0.90
SECONDARY_CORROBORATION_THRESHOLD = 0.82
EXTREME_SINGLE_REGION_THRESHOLD = 0.985
# A probe region must reach this before the detector bothers scoring the
# remaining corroboration crops. Far below CONTEXT_THRESHOLD, so nothing that
# could become a suspect or trigger is ever gated out; clean screens (which
# score near zero) bail after the cheap probe.
ESCALATE_GATE = 0.50

_ORT_THREADS = 2
_DEFAULT_EDGE = 224
_MIN_REGION_PX = 96
_MIN_CHANGED_FRACTION = 0.20
# PIL resample code -> filter. ViTImageProcessor uses resample=2 (BILINEAR).
_RESAMPLE = {0: Image.NEAREST, 1: Image.LANCZOS, 2: Image.BILINEAR, 3: Image.BICUBIC, 4: Image.BOX, 5: Image.HAMMING}

_warned_missing_deps = False


def model_dir() -> Path:
    return paths.models_dir() / MODEL_DIR_NAME


def dependencies_available() -> bool:
    """Whether the model can be installed (downloaded + exported to ONNX).

    Runtime only needs onnxruntime (a core dependency); torch/transformers/onnx
    are needed solely for the one-time export at install time.
    """
    try:
        installer = importlib.import_module("brake.detectors.anime_onnx_export")
        return bool(installer.dependencies_available())
    except Exception:
        return False


def model_installed() -> bool:
    root = model_dir()
    if not root.exists():
        return False
    has_config = (root / "config.json").exists()
    has_processor = (
        (root / "preprocessor_config.json").exists()
        or (root / "image_processor_config.json").exists()
    )
    # The ONNX model is the runtime format. Torch weights are accepted only as
    # a pre-export (older install) state that the detector migrates on load.
    has_runtime = (
        (root / ONNX_INT8_NAME).exists()
        or any(root.glob("*.safetensors"))
        or any(root.glob("*.bin"))
    )
    return has_config and has_processor and has_runtime


def anime_model_status() -> str:
    if model_installed():
        return "ready"
    if dependencies_available():
        return "not_installed"
    return "missing_dependencies"


def _export_to_onnx(root: Path) -> Path:
    """Export the downloaded torch weights to an INT8 ONNX model.

    Heavy (imports torch + transformers + onnx); runs only at install time or
    as a one-time migration, never on the scan path. Returns the int8 path.
    """
    installer = importlib.import_module("brake.detectors.anime_onnx_export")
    return installer.export_to_onnx(
        root,
        edge=_DEFAULT_EDGE,
        fp32_name=ONNX_FP32_NAME,
        int8_name=ONNX_INT8_NAME,
        torch_weight_names=_TORCH_WEIGHT_NAMES,
    )


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
    _export_to_onnx(target)
    if not model_installed():
        raise RuntimeError("model_download_incomplete")


Box = Tuple[int, int, int, int]


class AnimeNSFWDetector(Detector):
    name = "anime_nsfw"
    # Watcher may pass profile/changed_box/zoom_region keyword hints.
    accepts_scan_hints = True

    def __init__(self, config: NudityConfig) -> None:
        self.config = config
        self._session = None
        self._disabled = False
        self._nsfw_index = 1
        self._edge = _DEFAULT_EDGE
        self._resample = Image.BILINEAR
        self._mean = np.array([0.5, 0.5, 0.5], dtype=np.float32)
        self._std = np.array([0.5, 0.5, 0.5], dtype=np.float32)
        self._last_boxes: Dict[str, Box] = {}

    def _ensure_loaded(self) -> bool:
        global _warned_missing_deps
        if self._disabled:
            return False
        if self._session is not None:
            return True
        if not model_installed():
            _log.info("anime_nsfw detector: model is not installed; skipping.")
            return False
        try:
            import onnxruntime as ort  # core dependency, shared with NudeNet
        except ImportError:
            if not _warned_missing_deps:
                _log.warning("anime_nsfw detector: onnxruntime missing; disabled.")
                _warned_missing_deps = True
            self._disabled = True
            return False

        onnx_path = model_dir() / ONNX_INT8_NAME
        if not onnx_path.exists():
            # Older install with only torch weights: export once, then run on
            # ONNX forever after. Imports torch only for this one migration.
            try:
                _log.info("anime_nsfw: migrating existing install to ONNX...")
                onnx_path = _export_to_onnx(model_dir())
            except Exception as e:
                _log.error("anime_nsfw: ONNX migration failed (%s); disabling.", e)
                self._disabled = True
                return False
        try:
            opts = ort.SessionOptions()
            opts.intra_op_num_threads = _ORT_THREADS
            opts.inter_op_num_threads = 1
            self._session = ort.InferenceSession(
                str(onnx_path), sess_options=opts, providers=["CPUExecutionProvider"]
            )
            self._input_name = self._session.get_inputs()[0].name
            self._read_label_index()
            self._read_preprocessor()
            self._cleanup_stale_weights()
            _log.info("anime_nsfw detector ready (onnx, edge=%d, nsfw_index=%d).", self._edge, self._nsfw_index)
            return True
        except Exception as e:
            _log.error("anime_nsfw detector failed to load: %s", e)
            self._disabled = True
            return False

    def _cleanup_stale_weights(self) -> None:
        """Remove torch weights left over once ONNX is in use.

        The export process keeps model.safetensors memory-mapped, so it cannot
        delete it on Windows; the first fresh agent load (no mmap) clears it.
        Best-effort and never fatal.
        """
        root = model_dir()
        for name in (ONNX_FP32_NAME, *_TORCH_WEIGHT_NAMES):
            f = root / name
            if not f.exists():
                continue
            try:
                freed = f.stat().st_size / 1e6
                f.unlink()
                _log.info("anime_nsfw: removed stale %s (%.0fMB freed).", name, freed)
            except OSError:
                pass

    def _read_label_index(self) -> None:
        self._nsfw_index = 1  # Falconsai default ordering
        try:
            cfg = json.loads((model_dir() / "config.json").read_text(encoding="utf-8"))
        except Exception:
            return
        for idx, label in (cfg.get("id2label") or {}).items():
            if str(label).lower() == "nsfw":
                self._nsfw_index = int(idx)
                return

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

    def _region_boxes(
        self,
        size: Tuple[int, int],
        profile: str,
        changed_box: Optional[Box],
        zoom_region: str,
    ) -> List[Tuple[str, Box]]:
        w, h = size
        boxes: list[tuple[str, Box]] = [("full", (0, 0, w, h))]
        # Whole-image classifier: a small illustration in a corner downscales
        # to nothing in the full view, so a center crop adds resolution there.
        # Skipped on the budget (targeted) profile to stay cheap.
        if profile != "targeted" and min(w, h) >= 500:
            cw, ch = w // 2, h // 2
            cx, cy = (w - cw) // 2, (h - ch) // 2
            boxes.append(("center", (cx, cy, cx + cw, cy + ch)))
        # When we know where the screen changed, classify exactly that area.
        if changed_box is not None:
            clamped = self._pad_and_clamp(changed_box, size)
            if clamped is not None:
                boxes.append(("changed", clamped))
        if zoom_region:
            parent = self._last_boxes.get(zoom_region)
            if parent is not None:
                boxes.extend(self._quadrants(zoom_region, parent))
        return boxes

    def _regions(
        self,
        image: Image.Image,
        profile: str,
        changed_box: Optional[Box],
        zoom_region: str,
    ) -> List[Tuple[str, Image.Image]]:
        named_boxes = self._region_boxes(image.size, profile, changed_box, zoom_region)
        self._last_boxes = dict(named_boxes)
        regions: list[tuple[str, Image.Image]] = []
        for name, box in named_boxes:
            if box == (0, 0, image.width, image.height):
                regions.append((name, image))
            else:
                regions.append((name, image.crop(box)))
        return regions

    @staticmethod
    def _pad_and_clamp(box: Box, size: Tuple[int, int]) -> Optional[Box]:
        width, height = size
        left, top, right, bottom = box
        min_w = int(width * _MIN_CHANGED_FRACTION)
        min_h = int(height * _MIN_CHANGED_FRACTION)
        if right - left < min_w:
            pad = (min_w - (right - left)) // 2 + 1
            left, right = left - pad, right + pad
        if bottom - top < min_h:
            pad = (min_h - (bottom - top)) // 2 + 1
            top, bottom = top - pad, bottom + pad
        left = max(0, int(left))
        top = max(0, int(top))
        right = min(width, int(right))
        bottom = min(height, int(bottom))
        if right - left < _MIN_REGION_PX or bottom - top < _MIN_REGION_PX:
            return None
        return (left, top, right, bottom)

    @staticmethod
    def _quadrants(parent_name: str, box: Box) -> List[Tuple[str, Box]]:
        left, top, right, bottom = box
        mid_x = (left + right) // 2
        mid_y = (top + bottom) // 2
        if mid_x - left < _MIN_REGION_PX or mid_y - top < _MIN_REGION_PX:
            return []
        return [
            (f"{parent_name}~q0", (left, top, mid_x, mid_y)),
            (f"{parent_name}~q1", (mid_x, top, right, mid_y)),
            (f"{parent_name}~q2", (left, mid_y, mid_x, bottom)),
            (f"{parent_name}~q3", (mid_x, mid_y, right, bottom)),
        ]

    def _preprocess(self, images: List[Image.Image]) -> np.ndarray:
        edge = self._edge
        arrays = [
            np.asarray(im.convert("RGB").resize((edge, edge), self._resample), dtype=np.float32) / 255.0
            for im in images
        ]
        batch = np.stack(arrays)  # (N, H, W, C)
        batch = (batch - self._mean) / self._std
        batch = np.transpose(batch, (0, 3, 1, 2))  # -> (N, C, H, W)
        return np.ascontiguousarray(batch, dtype=np.float32)

    def _score_regions(self, images: List[Image.Image]) -> List[float]:
        if not images:
            return []
        logits = self._session.run(None, {self._input_name: self._preprocess(images)})[0]
        logits = logits - logits.max(axis=1, keepdims=True)
        exp = np.exp(logits)
        probs = exp / exp.sum(axis=1, keepdims=True)
        return [float(probs[i, self._nsfw_index]) for i in range(len(images))]

    def _cascade_score(self, regions: List[Tuple[str, Image.Image]]) -> Dict[str, float]:
        """Score a cheap probe first; only run the rest if it looks possible.

        The probe is chosen to be both cheap and sufficient:

        - When the pacer gives a changed box (a "settle" scan after the screen
          moved), only that region is new content; the rest of the screen was
          scored on an earlier scan. So the probe is just the changed crop:
          one pass.
        - Otherwise (startup / window change / the periodic 15s backstop) the
          probe is the whole screen plus the centre crop, so a static screen
          is still covered thoroughly.

        If the probe stays below ESCALATE_GATE the screen is clean and we
        return — the best score is far below CONTEXT_THRESHOLD, identical to
        scoring everything. Only a warm probe pays for the full region set,
        which the corroboration logic then needs.
        """
        by_name = {name: img for name, img in regions}
        if "changed" in by_name:
            probe_names = ["changed"]
        else:
            probe_names = [n for n in ("full", "center") if n in by_name]

        scores = dict(zip(probe_names, self._score_regions([by_name[n] for n in probe_names])))
        if not scores or max(scores.values()) < ESCALATE_GATE:
            return scores

        rest = [(name, img) for name, img in regions if name not in scores]
        for (name, _img), score in zip(rest, self._score_regions([img for _, img in rest])):
            scores[name] = score
        return scores

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

        regions = self._regions(image, profile, changed_box, zoom_region)
        try:
            score_by_region = self._cascade_score(regions)
        except Exception as e:
            _log.error("anime_nsfw scan failed: %s", e)
            return DetectionResult.negative(self.name)

        best_score = 0.0
        best_region = ""
        for name, score in score_by_region.items():
            if score > best_score:
                best_score = score
                best_region = name

        top_scores = sorted(score_by_region.items(), key=lambda item: item[1], reverse=True)[:4]
        _log.info(
            "anime_nsfw: best=%s nsfw=%.2f regions=%d scores=%s",
            best_region or "?",
            best_score,
            len(regions),
            ",".join(f"{name}:{score:.2f}" for name, score in top_scores),
        )

        if self._corroborated(score_by_region):
            return DetectionResult(
                detector=self.name,
                triggered=True,
                confidence=best_score,
                label=f"POSSIBLE NSFW ART ({best_region})",
                severity="context",
                region=best_region,
                details=",".join(f"{name}:{score:.2f}" for name, score in top_scores),
            )
        if best_score >= CONTEXT_THRESHOLD:
            return DetectionResult(
                detector=self.name,
                triggered=False,
                confidence=best_score,
                label=f"SUSPECT NSFW ART ({best_region})",
                severity="context",
                region=best_region,
                details=",".join(f"{name}:{score:.2f}" for name, score in top_scores),
            )
        return DetectionResult.negative(self.name)

    @staticmethod
    def _corroborated(scores: Dict[str, float]) -> bool:
        if not scores:
            return False
        best = max(scores.values())
        if best < TRIGGER_THRESHOLD:
            return False

        high_regions = {
            region for region, score in scores.items()
            if score >= TRIGGER_THRESHOLD and region != "changed"
        }
        if len(high_regions) >= 2:
            return True

        secondary_regions = {
            region for region, score in scores.items()
            if score >= SECONDARY_CORROBORATION_THRESHOLD and region != "changed"
        }
        if best >= EXTREME_SINGLE_REGION_THRESHOLD and len(secondary_regions) >= 2:
            return True

        # A changed crop is useful supporting evidence, but never enough by
        # itself. Fast game animation often produces a hot changed crop.
        changed_score = scores.get("changed", 0.0)
        if changed_score >= TRIGGER_THRESHOLD and secondary_regions:
            return True

        return False
