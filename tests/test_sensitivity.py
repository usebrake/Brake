"""Unit tests for the three-mode detection sensitivity behavior."""
from __future__ import annotations

import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
import tempfile
from dataclasses import dataclass
from typing import Callable

from PIL import Image

_TEST_DATA_DIR = tempfile.TemporaryDirectory(prefix="brake-sensitivity-")
os.environ["BRAKE_DATA_DIR"] = _TEST_DATA_DIR.name


@dataclass
class _Call:
    duration: int
    reason: str
    message: str = ""
    shutdown_on_done: bool = False


class _Store:
    def __init__(self, sensitivity: str) -> None:
        from brake.state.schema import State

        self.state = State(password_hash="hash", enabled=True, detection_sensitivity=sensitivity)

    def load(self):
        return self.state


class _Detector:
    def __init__(self, result) -> None:
        self.result = result

    def scan(self, _img):
        return self.result


def _context_hit(label: str = "CONTEXT NUDITY (BUTTOCKS_EXPOSED)"):
    from brake.detectors.base import DetectionResult

    return DetectionResult(
        detector="nudity",
        triggered=True,
        confidence=0.70,
        label=label,
        severity="context",
    )


def _strong_context_hit(label: str = "CONTEXT NUDITY (FEMALE_BREAST_EXPOSED)"):
    from brake.detectors.base import DetectionResult

    return DetectionResult(
        detector="nudity",
        triggered=True,
        confidence=0.86,
        label=label,
        severity="context",
    )


def _anime_context_hit(label: str = "POSSIBLE NSFW ART (full)"):
    from brake.detectors.base import DetectionResult

    return DetectionResult(
        detector="anime_nsfw",
        triggered=True,
        confidence=0.95,
        label=label,
        severity="context",
    )


def _hard_hit(label: str = "EXPLICIT (MALE_GENITALIA_EXPOSED)"):
    from brake.detectors.base import DetectionResult

    return DetectionResult(
        detector="nudity",
        triggered=True,
        confidence=0.80,
        label=label,
        severity="hard",
    )


def _very_high_hard_hit(label: str = "EXPLICIT (MALE_GENITALIA_EXPOSED)"):
    from brake.detectors.base import DetectionResult

    return DetectionResult(
        detector="nudity",
        triggered=True,
        confidence=0.96,
        label=label,
        severity="hard",
    )


def _soft_context_hit(label: str = "CONTEXT NUDITY (BUTTOCKS_EXPOSED)"):
    from brake.detectors.base import DetectionResult

    return DetectionResult(
        detector="nudity",
        triggered=False,
        confidence=0.66,
        label=label,
        severity="context",
    )


def _watcher(sensitivity: str):
    from brake.incident_memory import IncidentLedger
    from brake.service.watcher import Watcher

    incident_dir = Path(tempfile.mkdtemp(prefix="brake-incidents-"))
    return Watcher(
        store=_Store(sensitivity),
        incidents=IncidentLedger(file_path=incident_dir / "incidents.json", key_path=incident_dir / "state.key"),
    )


def _patch_lockout(watcher_mod):
    calls: list[_Call] = []
    original = watcher_mod._spawn_lockout

    def fake(duration: int, reason: str, message: str = "", shutdown_on_done: bool = False) -> None:
        calls.append(_Call(duration, reason, message, shutdown_on_done))

    watcher_mod._spawn_lockout = fake
    return calls, original


def _patch_monotonic(watcher_mod, values: list[float]) -> Callable[[], None]:
    original = watcher_mod.time.monotonic
    iterator = iter(values)
    last = values[-1] if values else 0.0

    def fake() -> float:
        nonlocal last
        try:
            last = next(iterator)
        except StopIteration:
            pass
        return last

    watcher_mod.time.monotonic = fake

    def restore() -> None:
        watcher_mod.time.monotonic = original

    return restore


def test_balanced_context_spawns_warning_no_shutdown() -> None:
    import brake.service.watcher as watcher_mod

    calls, original_spawn = _patch_lockout(watcher_mod)
    restore_time = _patch_monotonic(watcher_mod, [100.0])
    try:
        w = _watcher("balanced")
        w._handle_balanced_context(_context_hit())
    finally:
        watcher_mod._spawn_lockout = original_spawn
        restore_time()

    assert len(calls) == 1
    assert calls[0].duration == watcher_mod.BALANCED_WARNING_SECONDS
    assert calls[0].shutdown_on_done is False
    print("  [ok] balanced context spawns warning without shutdown")


def test_balanced_suppresses_second_hit_within_cooldown() -> None:
    import brake.service.watcher as watcher_mod

    calls, original_spawn = _patch_lockout(watcher_mod)
    restore_time = _patch_monotonic(watcher_mod, [100.0, 101.0])
    try:
        w = _watcher("balanced")
        w._handle_balanced_context(_context_hit())
        w._handle_balanced_context(_context_hit())
    finally:
        watcher_mod._spawn_lockout = original_spawn
        restore_time()

    assert len(calls) == 1
    print("  [ok] balanced cooldown suppresses immediate repeated warning")


def test_balanced_repeated_context_after_cooldown_escalates_full_lockout() -> None:
    import brake.service.watcher as watcher_mod

    calls, original_spawn = _patch_lockout(watcher_mod)
    restore_time = _patch_monotonic(watcher_mod, [100.0, 100.0 + watcher_mod.BALANCED_COOLDOWN_SECONDS + 1])
    try:
        w = _watcher("balanced")
        w._handle_balanced_context(_strong_context_hit())
        w._handle_balanced_context(_strong_context_hit())
    finally:
        watcher_mod._spawn_lockout = original_spawn
        restore_time()

    assert len(calls) == 2
    assert calls[0].shutdown_on_done is False
    assert calls[1].shutdown_on_done is True
    assert calls[1].duration == 15 * 60
    print("  [ok] balanced repeated strong context escalates to full lockout")


def test_balanced_weak_repeat_context_rewarns_instead_of_escalating() -> None:
    """A persistently misread game/UI screen (borderline scores) must never
    walk itself into the shutdown lockout. It re-warns at most."""
    import brake.service.watcher as watcher_mod

    calls, original_spawn = _patch_lockout(watcher_mod)
    restore_time = _patch_monotonic(watcher_mod, [100.0, 100.0 + watcher_mod.BALANCED_COOLDOWN_SECONDS + 1])
    try:
        w = _watcher("balanced")
        w._handle_balanced_context(_context_hit())  # 0.70 confidence
        w._handle_balanced_context(_context_hit())
    finally:
        watcher_mod._spawn_lockout = original_spawn
        restore_time()

    assert len(calls) == 2
    assert calls[0].shutdown_on_done is False
    assert calls[1].shutdown_on_done is False  # second warning, NOT lockout
    print("  [ok] weak repeat context re-warns instead of escalating")


def test_anime_context_never_starts_shutdown_flow() -> None:
    """Matches the documented standard-mode behavior: illustrated hits cause
    a short pause only, regardless of repetition."""
    import brake.service.watcher as watcher_mod

    calls, original_spawn = _patch_lockout(watcher_mod)
    restore_time = _patch_monotonic(
        watcher_mod, [100.0, 100.0 + watcher_mod.BALANCED_COOLDOWN_SECONDS + 1]
    )
    try:
        w = _watcher("balanced")
        w._handle_detection(_anime_context_hit())
        w._handle_detection(_anime_context_hit())
    finally:
        watcher_mod._spawn_lockout = original_spawn
        restore_time()

    assert len(calls) == 2
    assert all(c.shutdown_on_done is False for c in calls)
    print("  [ok] anime context hits never escalate to shutdown")


def test_balanced_second_context_after_warning_escalates() -> None:
    """Content that persists past the warning escalates without waiting out
    the old 60s warning cooldown."""
    import brake.service.watcher as watcher_mod

    calls, original_spawn = _patch_lockout(watcher_mod)
    # First hit at 100 spawns a warning that runs until 100 + warning length.
    # Second hit lands shortly after the warning ends, well inside the
    # warning cooldown, and must still escalate.
    second_at = 100.0 + watcher_mod.BALANCED_WARNING_SECONDS + 2.0
    restore_time = _patch_monotonic(watcher_mod, [100.0, second_at])
    try:
        w = _watcher("balanced")
        w._handle_balanced_context(_strong_context_hit())
        w._handle_balanced_context(_strong_context_hit())
    finally:
        watcher_mod._spawn_lockout = original_spawn
        restore_time()

    assert len(calls) == 2
    assert calls[0].shutdown_on_done is False
    assert calls[1].shutdown_on_done is True
    print("  [ok] strong context persisting past the warning escalates")


def test_periodic_rescan_cannot_confirm_hard_strike() -> None:
    """A safety sweep of unchanged pixels must not confirm its own pending
    strike; only a fresh frame or a zoomed pass may."""
    import brake.service.watcher as watcher_mod

    calls, original_spawn = _patch_lockout(watcher_mod)
    restore_time = _patch_monotonic(watcher_mod, [100.0, 102.0, 104.0])
    try:
        w = _watcher("balanced")
        assert w._handle_detection(_hard_hit()) is True       # arms pending
        w._handle_detection(_hard_hit(), evidential=False)    # periodic rescan
        assert calls == []                                    # no lockout yet
        w._handle_detection(_hard_hit(), evidential=True)     # real confirmation
    finally:
        watcher_mod._spawn_lockout = original_spawn
        restore_time()

    assert len(calls) == 1
    assert calls[0].shutdown_on_done is True
    print("  [ok] periodic rescans cannot confirm a pending hard strike")


def test_strict_first_context_hit_requests_fast_confirmation() -> None:
    import brake.service.watcher as watcher_mod

    calls, original_spawn = _patch_lockout(watcher_mod)
    restore_time = _patch_monotonic(watcher_mod, [100.0])
    try:
        w = _watcher("strict")
        needs_fast_confirm = w._handle_strict_context(_context_hit())
    finally:
        watcher_mod._spawn_lockout = original_spawn
        restore_time()

    assert calls == []
    assert needs_fast_confirm is True
    assert w._last_strict_pending_label == "CONTEXT NUDITY (BUTTOCKS_EXPOSED)"
    print("  [ok] strict first context hit requests fast confirmation")


def test_strict_second_context_hit_confirms_full_lockout() -> None:
    import brake.service.watcher as watcher_mod

    calls, original_spawn = _patch_lockout(watcher_mod)
    restore_time = _patch_monotonic(watcher_mod, [100.0, 101.0])
    try:
        w = _watcher("strict")
        hit = _context_hit()
        assert w._handle_strict_context(hit) is True
        assert w._handle_strict_context(hit) is False
    finally:
        watcher_mod._spawn_lockout = original_spawn
        restore_time()

    assert len(calls) == 1
    assert calls[0].duration == 15 * 60
    assert calls[0].shutdown_on_done is True
    print("  [ok] strict confirmed context triggers full lockout")


def test_light_scan_ignores_context_hits() -> None:
    import brake.service.watcher as watcher_mod

    original_capture = watcher_mod.capture_all_monitors
    try:
        watcher_mod.capture_all_monitors = lambda: Image.new("RGB", (10, 10), "black")
        w = _watcher("light")
        w.detectors = [_Detector(_context_hit())]
        hit, _suspicion = w._scan_once()
        assert hit is None
    finally:
        watcher_mod.capture_all_monitors = original_capture
    print("  [ok] light scan ignores context hits")


def test_soft_context_scan_does_not_trigger_warning() -> None:
    import brake.service.watcher as watcher_mod

    original_capture = watcher_mod.capture_all_monitors
    try:
        watcher_mod.capture_all_monitors = lambda: Image.new("RGB", (10, 10), "black")
        w = _watcher("balanced")
        w.detectors = [_Detector(_soft_context_hit())]
        hit, suspicion = w._scan_once()
        assert hit is None
        assert suspicion is not None
        assert suspicion.severity == "context"
    finally:
        watcher_mod.capture_all_monitors = original_capture
    print("  [ok] soft context scan does not trigger warning but marks suspicion")


def test_balanced_hard_first_hit_requests_fast_confirmation() -> None:
    import brake.service.watcher as watcher_mod

    calls, original_spawn = _patch_lockout(watcher_mod)
    restore_time = _patch_monotonic(watcher_mod, [100.0])
    try:
        w = _watcher("balanced")
        needs_fast_confirm = w._handle_detection(_hard_hit())
    finally:
        watcher_mod._spawn_lockout = original_spawn
        restore_time()

    assert calls == []
    assert needs_fast_confirm is True
    assert w._last_hard_pending_label == "EXPLICIT (MALE_GENITALIA_EXPOSED)"
    print("  [ok] balanced hard first hit requests fast confirmation")


def test_light_hard_first_hit_keeps_old_confirmation_flow() -> None:
    import brake.service.watcher as watcher_mod

    calls, original_spawn = _patch_lockout(watcher_mod)
    restore_time = _patch_monotonic(watcher_mod, [100.0])
    try:
        w = _watcher("light")
        needs_fast_confirm = w._handle_detection(_hard_hit())
    finally:
        watcher_mod._spawn_lockout = original_spawn
        restore_time()

    assert calls == []
    assert needs_fast_confirm is False
    assert w._last_hard_pending_label == "EXPLICIT (MALE_GENITALIA_EXPOSED)"
    print("  [ok] light hard first hit keeps old confirmation flow")


def test_very_high_hard_hit_immediately_confirms_lockout() -> None:
    import brake.service.watcher as watcher_mod

    calls, original_spawn = _patch_lockout(watcher_mod)
    restore_time = _patch_monotonic(watcher_mod, [100.0])
    try:
        w = _watcher("balanced")
        w._handle_detection(_very_high_hard_hit())
    finally:
        watcher_mod._spawn_lockout = original_spawn
        restore_time()

    assert len(calls) == 1
    assert calls[0].duration == 15 * 60
    assert calls[0].shutdown_on_done is True
    assert w._last_hard_pending_label == ""
    print("  [ok] very high hard hit immediately confirms full lockout")


def test_repeated_hard_lockout_in_window_doubles_duration() -> None:
    import brake.service.watcher as watcher_mod

    calls, original_spawn = _patch_lockout(watcher_mod)
    restore_time = _patch_monotonic(watcher_mod, [100.0, 101.0])
    try:
        w = _watcher("balanced")
        w._handle_detection(_very_high_hard_hit())
        w._handle_detection(_very_high_hard_hit())
    finally:
        watcher_mod._spawn_lockout = original_spawn
        restore_time()

    assert len(calls) == 2
    assert calls[0].duration == 15 * 60
    assert calls[1].duration == 30 * 60
    assert all(call.shutdown_on_done for call in calls)
    print("  [ok] repeated hard lockout in incident window doubles duration")


def test_hard_second_hit_confirms_lockout() -> None:
    import brake.service.watcher as watcher_mod

    calls, original_spawn = _patch_lockout(watcher_mod)
    restore_time = _patch_monotonic(watcher_mod, [100.0, 104.0])
    try:
        w = _watcher("balanced")
        hit = _hard_hit()
        w._handle_detection(hit)
        w._handle_detection(hit)
    finally:
        watcher_mod._spawn_lockout = original_spawn
        restore_time()

    assert len(calls) == 1
    assert calls[0].duration == 15 * 60
    assert calls[0].shutdown_on_done is True
    print("  [ok] hard second hit confirms full lockout")


def test_hard_second_hit_can_change_label() -> None:
    import brake.service.watcher as watcher_mod

    calls, original_spawn = _patch_lockout(watcher_mod)
    restore_time = _patch_monotonic(watcher_mod, [100.0, 112.0])
    try:
        w = _watcher("balanced")
        w._handle_detection(_hard_hit("EXPLICIT (MALE_GENITALIA_EXPOSED)"))
        w._handle_detection(_hard_hit("EXPLICIT (FEMALE_GENITALIA_EXPOSED)"))
    finally:
        watcher_mod._spawn_lockout = original_spawn
        restore_time()

    assert len(calls) == 1
    assert calls[0].duration == 15 * 60
    assert calls[0].shutdown_on_done is True
    print("  [ok] hard second hit confirms even when video label changes")


def test_strict_hard_hit_immediately_full_locks() -> None:
    import brake.service.watcher as watcher_mod

    calls, original_spawn = _patch_lockout(watcher_mod)
    restore_time = _patch_monotonic(watcher_mod, [100.0])
    try:
        w = _watcher("strict")
        needs_fast_confirm = w._handle_detection(_hard_hit())
    finally:
        watcher_mod._spawn_lockout = original_spawn
        restore_time()

    assert needs_fast_confirm is False
    assert len(calls) == 1
    assert calls[0].shutdown_on_done is True
    print("  [ok] strict hard hit immediately full-locks")


def main() -> int:
    tests = [
        test_balanced_context_spawns_warning_no_shutdown,
        test_balanced_suppresses_second_hit_within_cooldown,
        test_balanced_repeated_context_after_cooldown_escalates_full_lockout,
        test_balanced_weak_repeat_context_rewarns_instead_of_escalating,
        test_anime_context_never_starts_shutdown_flow,
        test_balanced_second_context_after_warning_escalates,
        test_periodic_rescan_cannot_confirm_hard_strike,
        test_strict_first_context_hit_requests_fast_confirmation,
        test_strict_second_context_hit_confirms_full_lockout,
        test_light_scan_ignores_context_hits,
        test_soft_context_scan_does_not_trigger_warning,
        test_balanced_hard_first_hit_requests_fast_confirmation,
        test_light_hard_first_hit_keeps_old_confirmation_flow,
        test_very_high_hard_hit_immediately_confirms_lockout,
        test_repeated_hard_lockout_in_window_doubles_duration,
        test_hard_second_hit_confirms_lockout,
        test_hard_second_hit_can_change_label,
        test_strict_hard_hit_immediately_full_locks,
    ]
    for fn in tests:
        print(f"\n{fn.__name__}")
        fn()
    print("\nAll tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
