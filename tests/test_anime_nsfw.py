"""Tests for the illustrated/anime NSFW detector.

Covers the lean download policy, model-installed detection, and the scan
policy (threshold, region selection, batching, scan hints). The scoring tests
use a tiny fake model so they do not need the 343MB weights, but they run the
real preprocessing + region + softmax code path when torch is present.
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import types
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from PIL import Image

from brake.config import NudityConfig
from brake.detectors import anime_nsfw
from brake.detectors.anime_nsfw import (
    CONTEXT_THRESHOLD,
    MODEL_REVISION,
    _ALLOW_PATTERNS,
    AnimeNSFWDetector,
    model_installed,
)

_HAS_TORCH = importlib.util.find_spec("torch") is not None


def test_download_uses_lean_allowlist_and_pinned_revision() -> None:
    captured = {}

    def fake_snapshot_download(**kwargs):
        captured.update(kwargs)
        target = Path(kwargs["local_dir"])
        target.mkdir(parents=True, exist_ok=True)
        (target / "config.json").write_text("{}", encoding="utf-8")
        (target / "preprocessor_config.json").write_text("{}", encoding="utf-8")
        (target / "model.safetensors").write_bytes(b"\x00")
        return str(target)

    fake_hub = types.ModuleType("huggingface_hub")
    fake_hub.snapshot_download = fake_snapshot_download
    tmp = Path(tempfile.mkdtemp(prefix="brake-anime-dl-"))

    orig_hub = sys.modules.get("huggingface_hub")
    orig_model_dir = anime_nsfw.model_dir
    sys.modules["huggingface_hub"] = fake_hub
    anime_nsfw.model_dir = lambda: tmp  # type: ignore[assignment]
    try:
        anime_nsfw.download_model()
    finally:
        anime_nsfw.model_dir = orig_model_dir  # type: ignore[assignment]
        if orig_hub is not None:
            sys.modules["huggingface_hub"] = orig_hub
        else:
            sys.modules.pop("huggingface_hub", None)

    assert captured["allow_patterns"] == _ALLOW_PATTERNS
    assert captured["revision"] == MODEL_REVISION
    # The wasteful artifacts must never be in the allowlist.
    for junk in ("optimizer.pt", "pytorch_model.bin", "falconsai_yolov9_nsfw_model_quantized.pt"):
        assert junk not in _ALLOW_PATTERNS
    print("  [ok] download fetches only the 3 needed files at a pinned revision")


def test_model_installed_requires_config_processor_and_weights() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="brake-anime-installed-"))
    orig = anime_nsfw.model_dir
    anime_nsfw.model_dir = lambda: tmp  # type: ignore[assignment]
    try:
        assert model_installed() is False
        (tmp / "config.json").write_text("{}", encoding="utf-8")
        (tmp / "preprocessor_config.json").write_text("{}", encoding="utf-8")
        assert model_installed() is False  # weights still missing
        (tmp / "model.safetensors").write_bytes(b"\x00")
        assert model_installed() is True
    finally:
        anime_nsfw.model_dir = orig  # type: ignore[assignment]
    print("  [ok] model_installed needs config + processor + weights")


def test_disabled_config_short_circuits() -> None:
    det = AnimeNSFWDetector(NudityConfig(enabled=False))
    res = det.scan(Image.new("RGB", (800, 600), "black"))
    assert res.triggered is False
    assert det._model is None  # never attempted to load
    print("  [ok] disabled config returns negative without loading")


def _fake_loaded_detector(nsfw_score_by_size):
    """Detector with a fake torch-free scorer. ``nsfw_score_by_size`` maps a
    region's (w,h) -> nsfw score, so tests control per-region outputs."""
    det = AnimeNSFWDetector(NudityConfig(enabled=True))
    det._disabled = False
    det._model = object()  # non-None so _ensure_loaded short-circuits
    det._ensure_loaded = lambda: True  # type: ignore[assignment]

    def fake_score(images):
        # Score by the pre-crop region size recorded on the PIL image.
        return [nsfw_score_by_size(im.size) for im in images]

    det._score_regions = fake_score  # type: ignore[assignment]
    return det


def test_scan_triggers_above_threshold_only() -> None:
    high = _fake_loaded_detector(lambda size: 0.95)
    res = high.scan(Image.new("RGB", (300, 300), "white"))
    assert res.triggered is True
    assert res.severity == "context"
    assert res.confidence >= CONTEXT_THRESHOLD
    assert "POSSIBLE NSFW ART" in res.label

    low = _fake_loaded_detector(lambda size: CONTEXT_THRESHOLD - 0.01)
    res = low.scan(Image.new("RGB", (300, 300), "white"))
    assert res.triggered is False
    print("  [ok] scan triggers only at/above the context threshold")


def test_targeted_profile_scans_one_region_full_scans_two() -> None:
    seen = {"full": 0, "targeted": 0}

    def make(mode):
        det = _fake_loaded_detector(lambda size: 0.0)

        def counting(images):
            seen[mode] = len(images)
            return [0.0 for _ in images]

        det._score_regions = counting  # type: ignore[assignment]
        return det

    big = Image.new("RGB", (1200, 800), "white")
    make("full").scan(big, profile="full")
    make("targeted").scan(big, profile="targeted")
    assert seen["full"] == 2      # full + center
    assert seen["targeted"] == 1  # full only
    print("  [ok] full profile scans full+center, targeted scans full only")


def test_changed_box_adds_region() -> None:
    counts = {}

    det = _fake_loaded_detector(lambda size: 0.0)

    def counting(images):
        counts["n"] = len(images)
        return [0.0 for _ in images]

    det._score_regions = counting  # type: ignore[assignment]
    det.scan(Image.new("RGB", (1200, 800), "white"), profile="full", changed_box=(100, 100, 600, 600))
    assert counts["n"] == 3  # full + center + changed
    print("  [ok] a changed-area hint adds a classified region")


def test_best_region_wins() -> None:
    # Center crop of a 1200x800 image is 600x400; make that region the hottest.
    def by_size(size):
        return 0.97 if size == (600, 400) else 0.10

    det = _fake_loaded_detector(by_size)
    res = det.scan(Image.new("RGB", (1200, 800), "white"), profile="full")
    assert res.triggered is True
    assert res.region == "center"
    print("  [ok] the highest-scoring region is reported")


def test_real_preprocessing_shape_and_range() -> None:
    if not _HAS_TORCH:
        print("  [skip] torch not installed")
        return
    import numpy as np
    import torch

    det = AnimeNSFWDetector(NudityConfig(enabled=True))
    det._torch = torch
    det._edge = 224
    det._mean = np.array([0.5, 0.5, 0.5], dtype=np.float32)
    det._std = np.array([0.5, 0.5, 0.5], dtype=np.float32)
    tensor = det._preprocess([Image.new("RGB", (900, 700), "white"), Image.new("RGB", (50, 50), "black")])
    assert tuple(tensor.shape) == (2, 3, 224, 224)
    # white -> (1-0.5)/0.5 = 1.0 ; black -> (0-0.5)/0.5 = -1.0
    assert abs(float(tensor[0].max()) - 1.0) < 1e-5
    assert abs(float(tensor[1].min()) + 1.0) < 1e-5
    print("  [ok] preprocessing yields (N,3,224,224) normalized to [-1,1]")


def test_real_scoring_with_tiny_model() -> None:
    if not _HAS_TORCH:
        print("  [skip] torch not installed")
        return
    import numpy as np
    import torch

    class _TinyModel(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.head = torch.nn.Linear(3 * 224 * 224, 2)

        def forward(self, pixel_values=None):
            flat = pixel_values.reshape(pixel_values.shape[0], -1)
            return types.SimpleNamespace(logits=self.head(flat))

    det = AnimeNSFWDetector(NudityConfig(enabled=True))
    det._torch = torch
    det._model = _TinyModel().eval()
    det._nsfw_index = 1
    det._edge = 224
    det._mean = np.array([0.5, 0.5, 0.5], dtype=np.float32)
    det._std = np.array([0.5, 0.5, 0.5], dtype=np.float32)
    scores = det._score_regions([Image.new("RGB", (300, 300), "white")])
    assert len(scores) == 1
    assert 0.0 <= scores[0] <= 1.0
    print("  [ok] real preprocess+softmax scoring path runs end-to-end")


def main() -> int:
    tests = [
        test_download_uses_lean_allowlist_and_pinned_revision,
        test_model_installed_requires_config_processor_and_weights,
        test_disabled_config_short_circuits,
        test_scan_triggers_above_threshold_only,
        test_targeted_profile_scans_one_region_full_scans_two,
        test_changed_box_adds_region,
        test_best_region_wins,
        test_real_preprocessing_shape_and_range,
        test_real_scoring_with_tiny_model,
    ]
    for fn in tests:
        print(f"\n{fn.__name__}")
        fn()
    print("\nAll tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
