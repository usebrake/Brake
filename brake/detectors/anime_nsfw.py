"""Optional illustrated/anime NSFW classifier.

NudeNet is trained on real photographs of people, so it can miss illustrated
content such as hentai, anime, drawings, and renders. This detector runs a
separate image classifier downloaded into Brake's local data folder.

Design choices:

- Explicit install. The model is heavy, so scanning never auto-downloads it.
  The app downloads it only when the user clicks install.
- Optional dependency. If transformers and torch are missing, the detector
  returns negative and NudeNet keeps working alone.
- Limited regions. The model is CPU-heavy, so it scans the full screen and a
  center crop instead of tiling many regions.
- Context only. It never triggers shutdown-level hard lockouts in the beta.
"""
from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from typing import List, Tuple

from PIL import Image

from brake import paths
from brake.config import NudityConfig
from brake.detectors.base import Detector, DetectionResult

_log = logging.getLogger(__name__)

MODEL_NAME = "Falconsai/nsfw_image_detection"
MODEL_DIR_NAME = "anime_nsfw_falconsai"
CONTEXT_THRESHOLD = 0.86

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
        local_dir=str(target),
        local_dir_use_symlinks=False,
    )
    if not model_installed():
        raise RuntimeError("model_download_incomplete")


class AnimeNSFWDetector(Detector):
    name = "anime_nsfw"

    def __init__(self, config: NudityConfig) -> None:
        self.config = config
        self._pipeline = None
        self._disabled = False

    def _ensure_loaded(self) -> bool:
        global _warned_missing_deps
        if self._disabled:
            return False
        if self._pipeline is not None:
            return True
        try:
            from transformers import pipeline  # type: ignore[import-not-found]
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
            _log.info("Loading %s from %s...", MODEL_NAME, model_dir())
            self._pipeline = pipeline("image-classification", model=str(model_dir()))
            _log.info("anime_nsfw detector ready.")
            return True
        except Exception as e:
            _log.error("anime_nsfw detector failed to load: %s", e)
            self._disabled = True
            return False

    def _regions(self, image: Image.Image) -> List[Tuple[str, Image.Image]]:
        regions: list[tuple[str, Image.Image]] = [("full", image)]
        w, h = image.size
        if min(w, h) >= 500:
            cw, ch = w // 2, h // 2
            cx, cy = (w - cw) // 2, (h - ch) // 2
            regions.append(("center", image.crop((cx, cy, cx + cw, cy + ch))))
        return regions

    def _score_image(self, img: Image.Image) -> float:
        assert self._pipeline is not None
        results = self._pipeline(img)
        for item in results:
            if str(item.get("label", "")).lower() == "nsfw":
                return float(item.get("score", 0.0))
        return 0.0

    def scan(self, image: Image.Image) -> DetectionResult:
        if not self.config.enabled:
            return DetectionResult.negative(self.name)
        if not self._ensure_loaded():
            return DetectionResult.negative(self.name)

        best_region = ""
        best_score = 0.0
        try:
            for name, region in self._regions(image):
                score = self._score_image(region)
                if score > best_score:
                    best_score = score
                    best_region = name
        except Exception as e:
            _log.error("anime_nsfw scan failed: %s", e)
            return DetectionResult.negative(self.name)

        _log.info("anime_nsfw: best=%s nsfw=%.2f", best_region or "?", best_score)

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
