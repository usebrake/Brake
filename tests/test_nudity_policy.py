"""Unit tests for NudityDetector scoring policy: hard/context thresholds,
the sub-threshold suspicion band, and the multiple-findings thumbnail rule."""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from PIL import Image

from brake.config import NudityConfig
from brake.detectors.nudity import NudityDetector


class _FakeNudeNet:
    def __init__(self, findings: list[dict]) -> None:
        self.findings = findings

    def detect(self, _arr):
        return [dict(f) for f in self.findings]


def _detector(findings: list[dict]) -> NudityDetector:
    det = NudityDetector(NudityConfig(enabled=True))
    det._detector = _FakeNudeNet(findings)
    return det


# Small image so only the "full" region is scanned (no tiling below 500px).
_IMG = Image.new("RGB", (100, 100), "black")


def test_hard_hit_above_threshold_triggers_hard() -> None:
    det = _detector([{"class": "MALE_GENITALIA_EXPOSED", "score": 0.60}])
    res = det.scan(_IMG)
    assert res.triggered is True
    assert res.severity == "hard"
    print("  [ok] hard class above threshold triggers hard")


def test_hard_near_miss_reports_suspicion_only() -> None:
    det = _detector([{"class": "MALE_GENITALIA_EXPOSED", "score": 0.40}])
    res = det.scan(_IMG)
    assert res.triggered is False
    assert res.severity == "hard"
    assert "SUSPECT" in res.label
    print("  [ok] hard near-miss reports non-triggering suspicion")


def test_hard_score_below_suspicion_band_is_negative() -> None:
    det = _detector([{"class": "MALE_GENITALIA_EXPOSED", "score": 0.20}])
    res = det.scan(_IMG)
    assert res.triggered is False
    assert res.severity == "none"
    print("  [ok] low hard score stays fully negative")


def test_soft_context_reports_suspicion_only() -> None:
    det = _detector([{"class": "FEMALE_BREAST_EXPOSED", "score": 0.68}])
    res = det.scan(_IMG)
    assert res.triggered is False
    assert res.severity == "context"
    print("  [ok] single soft context finding stays non-triggering")


def test_two_soft_findings_do_not_trigger_multiple_rule() -> None:
    det = _detector([
        {"class": "FEMALE_BREAST_EXPOSED", "score": 0.68},
        {"class": "FEMALE_BREAST_EXPOSED", "score": 0.70},
    ])
    res = det.scan(_IMG)
    assert res.triggered is False
    print("  [ok] two soft findings stay below the multiple-findings rule")


def test_three_soft_findings_in_one_region_trigger_context() -> None:
    det = _detector([
        {"class": "FEMALE_BREAST_EXPOSED", "score": 0.66},
        {"class": "FEMALE_BREAST_EXPOSED", "score": 0.68},
        {"class": "BUTTOCKS_EXPOSED", "score": 0.70},
    ])
    res = det.scan(_IMG)
    assert res.triggered is True
    assert res.severity == "context"
    assert "MULTIPLE" in res.label
    assert abs(res.confidence - 0.70) < 1e-9
    print("  [ok] three soft findings in one region trigger context")


def test_mixed_hard_suspicion_findings_trigger_multiple_rule() -> None:
    # An image-search grid: several small explicit thumbnails, each scoring
    # below the per-class hard thresholds.
    det = _detector([
        {"class": "FEMALE_GENITALIA_EXPOSED", "score": 0.38},
        {"class": "MALE_GENITALIA_EXPOSED", "score": 0.41},
        {"class": "FEMALE_BREAST_EXPOSED", "score": 0.67},
    ])
    res = det.scan(_IMG)
    assert res.triggered is True
    assert res.severity == "context"
    assert "MULTIPLE" in res.label
    print("  [ok] grid of sub-threshold explicit findings triggers context")


def test_findings_spread_across_regions_do_not_combine() -> None:
    # The same body part shows up in overlapping tiles; per-region counting
    # must not add those together.
    det = _detector([])
    det._detector = _FakeNudeNet([])

    # Bypass scan() region logic by feeding findings with distinct regions
    # through the same code path: emulate detect() being called once per
    # region by tagging regions directly.
    class _RegionFake:
        def __init__(self) -> None:
            self.calls = 0

        def detect(self, _arr):
            self.calls += 1
            return [{"class": "FEMALE_BREAST_EXPOSED", "score": 0.68}]

    big = Image.new("RGB", (1200, 800), "black")  # large enough to tile
    det = NudityDetector(NudityConfig(enabled=True))
    det._detector = _RegionFake()
    res = det.scan(big)
    # One soft finding per region: suspicion only, never the multiple rule.
    assert res.triggered is False
    assert res.severity == "context"
    print("  [ok] one finding per region does not combine into the multiple rule")


class _CountingFake:
    def __init__(self) -> None:
        self.calls = 0

    def detect(self, _arr):
        self.calls += 1
        return []


def _counting_detector() -> tuple[NudityDetector, _CountingFake]:
    det = NudityDetector(NudityConfig(enabled=True))
    fake = _CountingFake()
    det._detector = fake
    return det, fake


_BIG = Image.new("RGB", (1200, 800), "black")


def test_full_profile_scans_seven_regions() -> None:
    det, fake = _counting_detector()
    det.scan(_BIG)
    assert fake.calls == 7, fake.calls
    print("  [ok] full profile scans 7 regions")


def test_targeted_profile_scans_two_regions() -> None:
    det, fake = _counting_detector()
    det.scan(_BIG, profile="targeted")
    assert fake.calls == 2, fake.calls
    print("  [ok] targeted profile scans only full + video_center")


def test_changed_box_adds_one_region() -> None:
    det, fake = _counting_detector()
    det.scan(_BIG, changed_box=(100, 100, 500, 450))
    assert fake.calls == 8, fake.calls
    assert "changed" in det._last_boxes
    print("  [ok] changed-area hint adds a dedicated crop")


def test_zoom_region_adds_subquadrants_and_chains() -> None:
    det, fake = _counting_detector()
    det.scan(_BIG)  # records region boxes
    before = fake.calls
    det.scan(_BIG, zoom_region="video_center")
    assert fake.calls - before == 11, fake.calls - before  # 7 + 4 sub-tiles
    assert "video_center~q0" in det._last_boxes
    before = fake.calls
    det.scan(_BIG, zoom_region="video_center~q0")
    assert fake.calls - before == 11  # second zoom level chains
    print("  [ok] zoom confirmation splits the suspect region and can chain")


def test_result_reports_winning_region() -> None:
    det = _detector([{"class": "MALE_GENITALIA_EXPOSED", "score": 0.60}])
    res = det.scan(_IMG)
    assert res.region == "full"
    print("  [ok] results report the region the finding came from")


def main() -> int:
    tests = [
        test_hard_hit_above_threshold_triggers_hard,
        test_hard_near_miss_reports_suspicion_only,
        test_hard_score_below_suspicion_band_is_negative,
        test_soft_context_reports_suspicion_only,
        test_two_soft_findings_do_not_trigger_multiple_rule,
        test_three_soft_findings_in_one_region_trigger_context,
        test_mixed_hard_suspicion_findings_trigger_multiple_rule,
        test_findings_spread_across_regions_do_not_combine,
        test_full_profile_scans_seven_regions,
        test_targeted_profile_scans_two_regions,
        test_changed_box_adds_one_region,
        test_zoom_region_adds_subquadrants_and_chains,
        test_result_reports_winning_region,
    ]
    for fn in tests:
        print(f"\n{fn.__name__}")
        fn()
    print("\nAll tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
