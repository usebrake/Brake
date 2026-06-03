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


def _hard_hit(label: str = "EXPLICIT (MALE_GENITALIA_EXPOSED)"):
    from brake.detectors.base import DetectionResult

    return DetectionResult(
        detector="nudity",
        triggered=True,
        confidence=0.88,
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
    from brake.service.watcher import Watcher

    return Watcher(store=_Store(sensitivity))


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
    print("  [ok] balanced cooldown suppresses repeated warning")


def test_strict_first_hit_only_sets_pending() -> None:
    import brake.service.watcher as watcher_mod

    calls, original_spawn = _patch_lockout(watcher_mod)
    restore_time = _patch_monotonic(watcher_mod, [100.0])
    try:
        w = _watcher("strict")
        w._handle_strict_context(_context_hit())
    finally:
        watcher_mod._spawn_lockout = original_spawn
        restore_time()

    assert calls == []
    assert w._last_strict_pending_label == "CONTEXT NUDITY (BUTTOCKS_EXPOSED)"
    print("  [ok] strict first hit sets pending only")


def test_strict_second_hit_confirms_within_window() -> None:
    import brake.service.watcher as watcher_mod

    calls, original_spawn = _patch_lockout(watcher_mod)
    restore_time = _patch_monotonic(watcher_mod, [100.0, 105.0, 105.0])
    try:
        w = _watcher("strict")
        hit = _context_hit()
        w._handle_strict_context(hit)
        w._handle_strict_context(hit)
    finally:
        watcher_mod._spawn_lockout = original_spawn
        restore_time()

    assert len(calls) == 1
    assert calls[0].duration == watcher_mod.STRICT_PENALTY_LADDER[0]
    assert calls[0].shutdown_on_done is False
    print("  [ok] strict second hit confirms within window")


def test_strict_cumulative_ladder() -> None:
    import brake.service.watcher as watcher_mod

    calls, original_spawn = _patch_lockout(watcher_mod)
    restore_time = _patch_monotonic(watcher_mod, [100.0, 101.0, 102.0])
    try:
        w = _watcher("strict")
        hit = _context_hit()
        w._apply_strict_context_penalty(hit)
        w._apply_strict_context_penalty(hit)
        w._apply_strict_context_penalty(hit)
    finally:
        watcher_mod._spawn_lockout = original_spawn
        restore_time()

    assert [c.duration for c in calls] == watcher_mod.STRICT_PENALTY_LADDER
    assert all(not c.shutdown_on_done for c in calls)
    print("  [ok] strict cumulative ladder uses 30s, 60s, 120s")


def test_strict_reset_after_idle_window() -> None:
    import brake.service.watcher as watcher_mod

    calls, original_spawn = _patch_lockout(watcher_mod)
    restore_time = _patch_monotonic(watcher_mod, [100.0, 101.0 + watcher_mod.STRICT_RESET_SECONDS])
    try:
        w = _watcher("strict")
        hit = _context_hit()
        w._apply_strict_context_penalty(hit)
        w._apply_strict_context_penalty(hit)
    finally:
        watcher_mod._spawn_lockout = original_spawn
        restore_time()

    assert [c.duration for c in calls] == [
        watcher_mod.STRICT_PENALTY_LADDER[0],
        watcher_mod.STRICT_PENALTY_LADDER[0],
    ]
    print("  [ok] strict idle reset drops next penalty back to first rung")


def test_light_scan_ignores_context_hits() -> None:
    import brake.service.watcher as watcher_mod

    original_capture = watcher_mod.capture_all_monitors
    try:
        watcher_mod.capture_all_monitors = lambda: Image.new("RGB", (10, 10), "black")
        w = _watcher("light")
        w.detectors = [_Detector(_context_hit())]
        assert w._scan_once() is None
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
        assert w._scan_once() is None
    finally:
        watcher_mod.capture_all_monitors = original_capture
    print("  [ok] soft context scan does not trigger warning")


def test_hard_first_hit_only_sets_pending() -> None:
    import brake.service.watcher as watcher_mod

    calls, original_spawn = _patch_lockout(watcher_mod)
    restore_time = _patch_monotonic(watcher_mod, [100.0])
    try:
        w = _watcher("balanced")
        w._handle_hard(_hard_hit())
    finally:
        watcher_mod._spawn_lockout = original_spawn
        restore_time()

    assert calls == []
    assert w._last_hard_pending_label == "EXPLICIT (MALE_GENITALIA_EXPOSED)"
    print("  [ok] hard first hit sets pending only")


def test_very_high_hard_hit_immediately_confirms_lockout() -> None:
    import brake.service.watcher as watcher_mod

    calls, original_spawn = _patch_lockout(watcher_mod)
    restore_time = _patch_monotonic(watcher_mod, [100.0])
    try:
        w = _watcher("balanced")
        w._handle_hard(_very_high_hard_hit())
    finally:
        watcher_mod._spawn_lockout = original_spawn
        restore_time()

    assert len(calls) == 1
    assert calls[0].shutdown_on_done is True
    assert w._last_hard_pending_label == ""
    print("  [ok] very high hard hit immediately confirms full lockout")


def test_hard_second_hit_confirms_lockout() -> None:
    import brake.service.watcher as watcher_mod

    calls, original_spawn = _patch_lockout(watcher_mod)
    restore_time = _patch_monotonic(watcher_mod, [100.0, 104.0])
    try:
        w = _watcher("balanced")
        hit = _hard_hit()
        w._handle_hard(hit)
        w._handle_hard(hit)
    finally:
        watcher_mod._spawn_lockout = original_spawn
        restore_time()

    assert len(calls) == 1
    assert calls[0].shutdown_on_done is True
    print("  [ok] hard second hit confirms full lockout")


def test_hard_second_hit_can_change_label() -> None:
    import brake.service.watcher as watcher_mod

    calls, original_spawn = _patch_lockout(watcher_mod)
    restore_time = _patch_monotonic(watcher_mod, [100.0, 112.0])
    try:
        w = _watcher("balanced")
        w._handle_hard(_hard_hit("EXPLICIT (MALE_GENITALIA_EXPOSED)"))
        w._handle_hard(_hard_hit("EXPLICIT (FEMALE_GENITALIA_EXPOSED)"))
    finally:
        watcher_mod._spawn_lockout = original_spawn
        restore_time()

    assert len(calls) == 1
    assert calls[0].shutdown_on_done is True
    print("  [ok] hard second hit confirms even when video label changes")


def main() -> int:
    tests = [
        test_balanced_context_spawns_warning_no_shutdown,
        test_balanced_suppresses_second_hit_within_cooldown,
        test_strict_first_hit_only_sets_pending,
        test_strict_second_hit_confirms_within_window,
        test_strict_cumulative_ladder,
        test_strict_reset_after_idle_window,
        test_light_scan_ignores_context_hits,
        test_soft_context_scan_does_not_trigger_warning,
        test_hard_first_hit_only_sets_pending,
        test_very_high_hard_hit_immediately_confirms_lockout,
        test_hard_second_hit_confirms_lockout,
        test_hard_second_hit_can_change_label,
    ]
    for fn in tests:
        print(f"\n{fn.__name__}")
        fn()
    print("\nAll tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
