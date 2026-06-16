"""Tests for the structured detection-event log."""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _fresh(tmp: Path):
    os.environ["BRAKE_DATA_DIR"] = str(tmp)
    for name in list(importlib.sys.modules):
        if name.startswith("brake.") or name == "brake":
            importlib.sys.modules.pop(name, None)
    from brake.detection_events import append_detection_event, list_detection_events
    from brake.detectors.base import DetectionResult

    return append_detection_event, list_detection_events, DetectionResult


def test_detection_events_store_only_meaningful_hits(tmp_path: Path) -> None:
    append_event, list_events, DetectionResult = _fresh(tmp_path)

    append_event(DetectionResult.negative("nudity"), action="observed")
    append_event(
        DetectionResult(
            detector="anime_nsfw",
            triggered=False,
            confidence=0.91,
            label="SUSPECT NSFW ART (full)",
            severity="context",
            region="full",
        ),
        action="observed",
        scan_reason="sustained",
        profile="full",
    )

    events = list_events()
    assert len(events) == 1
    assert events[0]["detector"] == "anime_nsfw"
    assert events[0]["severity"] == "context"
    assert events[0]["scanReason"] == "sustained"
    print("  [ok] detection events store only meaningful hits")


def test_detection_events_limit_and_order(tmp_path: Path) -> None:
    append_event, list_events, DetectionResult = _fresh(tmp_path)

    for i in range(5):
        append_event(
            DetectionResult(
                detector="nudity",
                triggered=True,
                confidence=0.7 + i / 100,
                label=f"CONTEXT NUDITY ({i})",
                severity="context",
                region="full",
            ),
            action="detected",
        )

    events = list_events(3)
    assert len(events) == 3
    assert events[0]["label"] == "CONTEXT NUDITY (4)"
    assert events[-1]["label"] == "CONTEXT NUDITY (2)"
    print("  [ok] detection events limit and newest-first order")


def main() -> int:
    import tempfile

    tests = [
        test_detection_events_store_only_meaningful_hits,
        test_detection_events_limit_and_order,
    ]
    for fn in tests:
        print(f"\n{fn.__name__}")
        with tempfile.TemporaryDirectory(prefix="brake-detection-events-test-") as d:
            fn(Path(d))
    print("\nAll tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
