"""Tests for the illustrated/anime NSFW detector.

Covers the lean download + ONNX export policy, model-installed detection, the
cascade (cheap probe then escalate), and the corroboration trigger policy.
Scoring tests use a fake scorer / fake onnxruntime session so they need no
weights, but they exercise the real preprocessing + softmax + region code.
"""
from __future__ import annotations

import sys
import tempfile
import types
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import numpy as np
from PIL import Image

from brake.config import NudityConfig
from brake.detectors import anime_nsfw
from brake.detectors.anime_nsfw import (
    CONTEXT_THRESHOLD,
    ESCALATE_GATE,
    MODEL_REVISION,
    ONNX_INT8_NAME,
    TRIGGER_THRESHOLD,
    _ALLOW_PATTERNS,
    AnimeNSFWDetector,
    model_installed,
)


def test_download_lean_allowlist_pinned_revision_and_onnx_export() -> None:
    captured = {}
    tmp = Path(tempfile.mkdtemp(prefix="brake-anime-dl-"))

    def fake_snapshot_download(**kwargs):
        captured.update(kwargs)
        target = Path(kwargs["local_dir"])
        target.mkdir(parents=True, exist_ok=True)
        (target / "config.json").write_text("{}", encoding="utf-8")
        (target / "preprocessor_config.json").write_text("{}", encoding="utf-8")
        (target / "model.safetensors").write_bytes(b"\x00")
        return str(target)

    def fake_export(root):
        (Path(root) / ONNX_INT8_NAME).write_bytes(b"\x00")
        return Path(root) / ONNX_INT8_NAME

    fake_hub = types.ModuleType("huggingface_hub")
    fake_hub.snapshot_download = fake_snapshot_download
    orig_hub = sys.modules.get("huggingface_hub")
    orig_model_dir = anime_nsfw.model_dir
    orig_export = anime_nsfw._export_to_onnx
    sys.modules["huggingface_hub"] = fake_hub
    anime_nsfw.model_dir = lambda: tmp  # type: ignore[assignment]
    anime_nsfw._export_to_onnx = fake_export  # type: ignore[assignment]
    try:
        anime_nsfw.download_model()
    finally:
        anime_nsfw.model_dir = orig_model_dir  # type: ignore[assignment]
        anime_nsfw._export_to_onnx = orig_export  # type: ignore[assignment]
        if orig_hub is not None:
            sys.modules["huggingface_hub"] = orig_hub
        else:
            sys.modules.pop("huggingface_hub", None)

    assert captured["allow_patterns"] == _ALLOW_PATTERNS
    assert captured["revision"] == MODEL_REVISION
    for junk in ("optimizer.pt", "pytorch_model.bin", "falconsai_yolov9_nsfw_model_quantized.pt"):
        assert junk not in _ALLOW_PATTERNS
    assert (tmp / ONNX_INT8_NAME).exists()
    print("  [ok] download fetches 3 files at a pinned revision then exports ONNX")


def test_model_installed_accepts_onnx_or_legacy_weights() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="brake-anime-installed-"))
    orig = anime_nsfw.model_dir
    anime_nsfw.model_dir = lambda: tmp  # type: ignore[assignment]
    try:
        assert model_installed() is False
        (tmp / "config.json").write_text("{}", encoding="utf-8")
        (tmp / "preprocessor_config.json").write_text("{}", encoding="utf-8")
        assert model_installed() is False  # no runtime weights yet
        (tmp / ONNX_INT8_NAME).write_bytes(b"\x00")
        assert model_installed() is True  # onnx is the runtime format
        (tmp / ONNX_INT8_NAME).unlink()
        (tmp / "model.safetensors").write_bytes(b"\x00")
        assert model_installed() is True  # legacy torch weights still accepted
    finally:
        anime_nsfw.model_dir = orig  # type: ignore[assignment]
    print("  [ok] model_installed accepts onnx or legacy torch weights")


def test_disabled_config_short_circuits() -> None:
    det = AnimeNSFWDetector(NudityConfig(enabled=False))
    res = det.scan(Image.new("RGB", (800, 600), "black"))
    assert res.triggered is False
    assert det._session is None  # never attempted to load
    print("  [ok] disabled config returns negative without loading")


def _fake_loaded_detector(score_fn):
    """Detector with loading bypassed and a fake region scorer. ``score_fn``
    maps a region image's (w,h) -> nsfw score."""
    det = AnimeNSFWDetector(NudityConfig(enabled=True))
    det._disabled = False
    det._session = object()  # non-None
    det._ensure_loaded = lambda: True  # type: ignore[assignment]
    det._scored_counts = []

    def fake_score(images):
        det._scored_counts.append(len(images))
        return [score_fn(im.size) for im in images]

    det._score_regions = fake_score  # type: ignore[assignment]
    return det


def test_clean_settle_scan_is_one_pass() -> None:
    # A settle scan (changed box present) probes only the changed crop.
    det = _fake_loaded_detector(lambda size: 0.02)
    res = det.scan(Image.new("RGB", (1200, 800), "white"), profile="full", changed_box=(100, 100, 600, 600))
    assert res.triggered is False
    assert res.severity == "none"
    assert sum(det._scored_counts) == 1
    print("  [ok] a clean settle scan costs a single pass (changed crop only)")


def test_clean_periodic_scan_probes_full_and_center() -> None:
    # No changed box (startup / 15s periodic backstop): probe is full + center.
    det = _fake_loaded_detector(lambda size: 0.02)
    det.scan(Image.new("RGB", (1200, 800), "white"), profile="full")
    assert sum(det._scored_counts) == 2
    print("  [ok] a clean periodic scan probes full + center for coverage")


def test_warm_probe_escalates_to_all_regions() -> None:
    det = _fake_loaded_detector(lambda size: 0.6)  # above ESCALATE_GATE
    det.scan(Image.new("RGB", (1200, 800), "white"), profile="full", changed_box=(100, 100, 600, 600))
    # changed probe is warm -> full + center also scored: 3 regions total.
    assert sum(det._scored_counts) == 3
    assert ESCALATE_GATE <= 0.6
    print("  [ok] a warm probe escalates to score every region")


def test_single_hot_region_is_suspect_not_trigger() -> None:
    # Only the center crop (600x400 of a 1200x800 image) is hot.
    det = _fake_loaded_detector(lambda size: 0.95 if size == (600, 400) else 0.05)
    res = det.scan(Image.new("RGB", (1200, 800), "white"), profile="full")
    assert res.triggered is False
    assert "SUSPECT" in res.label
    assert res.region == "center"
    print("  [ok] one hot region is a non-locking suspect, not a trigger")


def test_two_high_regions_trigger() -> None:
    det = _fake_loaded_detector(lambda size: 0.95)  # full and center both high
    res = det.scan(Image.new("RGB", (1200, 800), "white"), profile="full")
    assert res.triggered is True
    assert res.severity == "context"
    assert res.confidence >= TRIGGER_THRESHOLD
    print("  [ok] two corroborating high regions trigger a context hit")


def test_targeted_profile_scans_full_only() -> None:
    det = _fake_loaded_detector(lambda size: 0.02)
    det.scan(Image.new("RGB", (1200, 800), "white"), profile="targeted")
    assert sum(det._scored_counts) == 1  # full only, no center on targeted
    print("  [ok] targeted profile probes the full frame only")


def test_changed_crop_alone_cannot_trigger() -> None:
    # changed crop blazing hot, every stable region cold: must not trigger
    # (fast game animation produces hot changed crops).
    def by_name(size):
        # 1200x800 -> changed box (100,100,1100,700) clamps to >=0.20 frac.
        return 0.99 if size == (1000, 600) else 0.10

    det = _fake_loaded_detector(by_name)
    res = det.scan(Image.new("RGB", (1200, 800), "white"), profile="full", changed_box=(100, 100, 1100, 700))
    assert res.triggered is False
    print("  [ok] a hot changed crop alone does not trigger")


def test_corroboration_rules_directly() -> None:
    c = AnimeNSFWDetector._corroborated
    assert c({"full": 0.93, "center": 0.91}) is True              # two high
    assert c({"full": 0.95, "center": 0.50}) is False             # one high
    assert c({"full": 0.99, "center": 0.83, "top": 0.84}) is True  # extreme + 2 secondary
    assert c({"full": 0.20, "changed": 0.99}) is False            # changed alone
    assert c({"full": 0.91, "changed": 0.99}) is True             # changed + a high stable region
    assert c({"full": 0.5}) is False
    print("  [ok] corroboration rules behave as specified")


def test_real_preprocessing_shape_and_range() -> None:
    det = AnimeNSFWDetector(NudityConfig(enabled=True))
    det._edge = 224
    det._mean = np.array([0.5, 0.5, 0.5], dtype=np.float32)
    det._std = np.array([0.5, 0.5, 0.5], dtype=np.float32)
    arr = det._preprocess([Image.new("RGB", (900, 700), "white"), Image.new("RGB", (50, 50), "black")])
    assert isinstance(arr, np.ndarray)
    assert arr.shape == (2, 3, 224, 224)
    assert arr.dtype == np.float32
    assert abs(float(arr[0].max()) - 1.0) < 1e-5   # white -> +1
    assert abs(float(arr[1].min()) + 1.0) < 1e-5   # black -> -1
    print("  [ok] preprocessing yields float32 (N,3,224,224) normalized to [-1,1]")


def test_real_scoring_with_fake_onnx_session() -> None:
    det = AnimeNSFWDetector(NudityConfig(enabled=True))
    det._edge = 224
    det._mean = np.array([0.5, 0.5, 0.5], dtype=np.float32)
    det._std = np.array([0.5, 0.5, 0.5], dtype=np.float32)
    det._nsfw_index = 1
    det._input_name = "pixel_values"

    class _FakeSession:
        def run(self, _outputs, feed):
            x = feed["pixel_values"]
            n = x.shape[0]
            # logits where nsfw (index 1) wins -> softmax near 1.0
            return [np.tile(np.array([0.0, 8.0], dtype=np.float32), (n, 1))]

    det._session = _FakeSession()
    scores = det._score_regions([Image.new("RGB", (300, 300), "white"), Image.new("RGB", (40, 40), "black")])
    assert len(scores) == 2
    assert all(0.0 <= s <= 1.0 for s in scores)
    assert scores[0] > 0.99  # softmax of [0,8] at index 1
    print("  [ok] real preprocess + onnxruntime softmax path runs end-to-end")


def main() -> int:
    tests = [
        test_download_lean_allowlist_pinned_revision_and_onnx_export,
        test_model_installed_accepts_onnx_or_legacy_weights,
        test_disabled_config_short_circuits,
        test_clean_settle_scan_is_one_pass,
        test_clean_periodic_scan_probes_full_and_center,
        test_warm_probe_escalates_to_all_regions,
        test_single_hot_region_is_suspect_not_trigger,
        test_two_high_regions_trigger,
        test_targeted_profile_scans_full_only,
        test_changed_crop_alone_cannot_trigger,
        test_corroboration_rules_directly,
        test_real_preprocessing_shape_and_range,
        test_real_scoring_with_fake_onnx_session,
    ]
    for fn in tests:
        print(f"\n{fn.__name__}")
        fn()
    print("\nAll tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
