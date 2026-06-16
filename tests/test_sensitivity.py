"""Unit tests for Brake's single default detection policy."""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
import tempfile

from PIL import Image

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_TEST_DATA_DIR = tempfile.TemporaryDirectory(prefix="brake-sensitivity-")
os.environ["BRAKE_DATA_DIR"] = _TEST_DATA_DIR.name


@dataclass
class _Call:
    duration: int
    reason: str
    message: str = ""
    shutdown_on_done: bool = False


class _Store:
    def __init__(
        self,
        *,
        anime_detection_enabled: bool = False,
        shutdown_after_lockout: bool = True,
    ) -> None:
        from brake.state.schema import State

        self.state = State(
            password_hash="hash",
            enabled=True,
            anime_detection_enabled=anime_detection_enabled,
            shutdown_after_lockout=shutdown_after_lockout,
        )

    def load(self):
        return self.state


class _CorruptStore:
    def load(self):
        from brake.state import StateTamperedError

        raise StateTamperedError("bad state")


class _Detector:
    accepts_scan_hints = False

    def __init__(self, result, name: str = "nudity") -> None:
        self.result = result
        self.name = name

    def scan(self, _img):
        return self.result


def _context_hit(label: str = "CONTEXT NUDITY (BUTTOCKS_EXPOSED)"):
    from brake.detectors.base import DetectionResult

    return DetectionResult(
        detector="nudity",
        triggered=True,
        confidence=0.86,
        label=label,
        severity="context",
        region="center",
    )


def _hard_hit(label: str = "EXPLICIT (MALE_GENITALIA_EXPOSED)"):
    from brake.detectors.base import DetectionResult

    return DetectionResult(
        detector="nudity",
        triggered=True,
        confidence=0.96,
        label=label,
        severity="hard",
        region="center",
    )


def _anime_context_hit(label: str = "POSSIBLE NSFW ART (full)"):
    from brake.detectors.base import DetectionResult

    return DetectionResult(
        detector="anime_nsfw",
        triggered=True,
        confidence=0.95,
        label=label,
        severity="context",
        region="center",
    )


def _watcher(*, anime_detection_enabled: bool = False, shutdown_after_lockout: bool = True):
    from brake.incident_memory import IncidentLedger
    from brake.service.watcher import Watcher

    incident_dir = Path(tempfile.mkdtemp(prefix="brake-incidents-"))
    return Watcher(
        store=_Store(
            anime_detection_enabled=anime_detection_enabled,
            shutdown_after_lockout=shutdown_after_lockout,
        ),
        incidents=IncidentLedger(
            file_path=incident_dir / "incidents.json",
            key_path=incident_dir / "state.key",
        ),
    )


def _patch_lockout(watcher_mod):
    calls: list[_Call] = []
    original = watcher_mod._spawn_lockout

    def fake(duration: int, reason: str, message: str = "", shutdown_on_done: bool = False) -> None:
        calls.append(_Call(duration, reason, message, shutdown_on_done))

    watcher_mod._spawn_lockout = fake
    return calls, original


def test_context_nudity_does_not_start_lockout() -> None:
    import brake.service.watcher as watcher_mod

    calls, original_spawn = _patch_lockout(watcher_mod)
    try:
        w = _watcher()
        wants_confirm = w._handle_detection(_context_hit())
    finally:
        watcher_mod._spawn_lockout = original_spawn

    assert calls == []
    assert wants_confirm is True
    print("  [ok] context nudity asks for confirmation without lockout")


def test_hard_explicit_triggers_full_lockout() -> None:
    import brake.service.watcher as watcher_mod

    calls, original_spawn = _patch_lockout(watcher_mod)
    try:
        w = _watcher()
        w._handle_detection(_hard_hit())
    finally:
        watcher_mod._spawn_lockout = original_spawn

    assert len(calls) == 1
    assert calls[0].duration == 15 * 60
    assert calls[0].shutdown_on_done is True
    assert "1st full lockout" in calls[0].message
    assert "Full lockout time: 15 minutes." in calls[0].message
    print("  [ok] hard explicit triggers full lockout")


def test_second_lockout_explains_scaled_duration() -> None:
    import brake.service.watcher as watcher_mod

    calls, original_spawn = _patch_lockout(watcher_mod)
    try:
        w = _watcher()
        w.incidents.record()
        w._handle_detection(_hard_hit())
    finally:
        watcher_mod._spawn_lockout = original_spawn

    assert len(calls) == 1
    assert calls[0].duration == 30 * 60
    assert calls[0].shutdown_on_done is True
    assert "2nd full lockout in the last 24 hours" in calls[0].message
    assert "Full lockout time: 30 minutes." in calls[0].message
    assert "Your computer will shut down when this timer ends." in calls[0].message
    print("  [ok] second lockout explains scaled duration")


def test_fail_secure_lockout_uses_fifteen_minute_base() -> None:
    import brake.service.watcher as watcher_mod
    from brake.incident_memory import IncidentLedger
    from brake.service.watcher import Watcher

    incident_dir = Path(tempfile.mkdtemp(prefix="brake-fail-secure-incidents-"))
    incidents = IncidentLedger(
        file_path=incident_dir / "incidents.json",
        key_path=incident_dir / "state.key",
    )
    for _ in range(3):
        incidents.record()

    calls, original_spawn = _patch_lockout(watcher_mod)
    try:
        w = Watcher(store=_CorruptStore(), incidents=incidents)
        w._handle_detection(_hard_hit())
    finally:
        watcher_mod._spawn_lockout = original_spawn

    assert len(calls) == 1
    assert calls[0].duration == 45 * 60
    assert "Full lockout time: 45 minutes." in calls[0].message
    print("  [ok] fail-secure lockout uses 15-minute base")


def test_shutdown_after_lockout_setting_is_respected() -> None:
    import brake.service.watcher as watcher_mod

    calls, original_spawn = _patch_lockout(watcher_mod)
    try:
        w = _watcher(shutdown_after_lockout=False)
        w._handle_detection(_hard_hit())
    finally:
        watcher_mod._spawn_lockout = original_spawn

    assert len(calls) == 1
    assert calls[0].shutdown_on_done is False
    print("  [ok] shutdown toggle controls full lockout consequence")


def test_illustrated_off_skips_illustrated_detector() -> None:
    import brake.service.watcher as watcher_mod

    original_capture = watcher_mod.capture_all_monitors
    try:
        watcher_mod.capture_all_monitors = lambda: Image.new("RGB", (10, 10), "black")
        w = _watcher(anime_detection_enabled=False)
        w.detectors = [_Detector(_anime_context_hit(), name="anime_nsfw")]
        hit, suspicion = w._scan_once()
    finally:
        watcher_mod.capture_all_monitors = original_capture

    assert hit is None
    assert suspicion is None
    print("  [ok] illustrated detector is skipped when off")


def test_illustrated_on_can_trigger_full_lockout() -> None:
    import brake.service.watcher as watcher_mod

    calls, original_spawn = _patch_lockout(watcher_mod)
    original_capture = watcher_mod.capture_all_monitors
    try:
        watcher_mod.capture_all_monitors = lambda: Image.new("RGB", (10, 10), "black")
        w = _watcher(anime_detection_enabled=True)
        w.detectors = [_Detector(_anime_context_hit(), name="anime_nsfw")]
        hit, _suspicion = w._scan_once()
        assert hit is not None
        assert hit.detector == "anime_nsfw"
        assert hit.severity == "hard"
        assert w._handle_detection(hit) is True
        assert calls == []
        w._handle_detection(hit)
    finally:
        watcher_mod.capture_all_monitors = original_capture
        watcher_mod._spawn_lockout = original_spawn

    assert len(calls) == 1
    assert calls[0].shutdown_on_done is True
    print("  [ok] illustrated detector needs two evidential hits before lockout")


def test_illustrated_runs_on_targeted_confirmation_only() -> None:
    import brake.service.watcher as watcher_mod

    original_capture = watcher_mod.capture_all_monitors
    try:
        watcher_mod.capture_all_monitors = lambda: Image.new("RGB", (10, 10), "black")
        w = _watcher(anime_detection_enabled=True)
        detector = _Detector(_anime_context_hit(), name="anime_nsfw")
        w.detectors = [detector]
        hit, suspicion = w._scan_once(profile="targeted")
        assert hit is None
        assert suspicion is None

        hit, _suspicion = w._scan_once(profile="targeted", zoom_region="full")
    finally:
        watcher_mod.capture_all_monitors = original_capture

    assert hit is not None
    assert hit.detector == "anime_nsfw"
    print("  [ok] illustrated targeted scans run only for confirmation")


def test_illustrated_immediate_confidence_still_needs_confirmation() -> None:
    import brake.service.watcher as watcher_mod

    calls, original_spawn = _patch_lockout(watcher_mod)
    try:
        w = _watcher(anime_detection_enabled=True)
        hit = _anime_context_hit()
        hit.confidence = 0.99
        converted = w._apply_anime_mode(hit)
        assert converted.triggered is True
        assert converted.severity == "hard"
        assert w._handle_detection(converted) is True
    finally:
        watcher_mod._spawn_lockout = original_spawn

    assert calls == []
    print("  [ok] illustrated high confidence cannot lock on one frame")


def test_periodic_rescan_cannot_confirm_hard_strike() -> None:
    import brake.service.watcher as watcher_mod

    calls, original_spawn = _patch_lockout(watcher_mod)
    try:
        w = _watcher()
        lower_confidence = _hard_hit()
        lower_confidence.confidence = 0.80
        assert w._handle_detection(lower_confidence) is True
        w._handle_detection(lower_confidence, evidential=False)
        assert calls == []
        w._handle_detection(lower_confidence, evidential=True)
    finally:
        watcher_mod._spawn_lockout = original_spawn

    assert len(calls) == 1
    assert calls[0].shutdown_on_done is True
    print("  [ok] periodic rescans cannot confirm a pending hard strike")


def main() -> int:
    tests = [
        test_context_nudity_does_not_start_lockout,
        test_hard_explicit_triggers_full_lockout,
        test_second_lockout_explains_scaled_duration,
        test_fail_secure_lockout_uses_fifteen_minute_base,
        test_shutdown_after_lockout_setting_is_respected,
        test_illustrated_off_skips_illustrated_detector,
        test_illustrated_on_can_trigger_full_lockout,
        test_illustrated_runs_on_targeted_confirmation_only,
        test_illustrated_immediate_confidence_still_needs_confirmation,
        test_periodic_rescan_cannot_confirm_hard_strike,
    ]
    for fn in tests:
        print(f"\n{fn.__name__}")
        fn()
    print("\nAll tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
