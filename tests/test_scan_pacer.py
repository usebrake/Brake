"""Tests for the change-gated scan pacer."""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from PIL import Image, ImageDraw

from brake.service.scan_pacer import (
    ACTIVE_TICK_SECONDS,
    FramePacer,
    IDLE_AFTER_SECONDS,
    IDLE_TICK_SECONDS,
    SAFETY_SWEEP_SECONDS,
    SUSTAINED_AFTER_SECONDS,
)

_W, _H = 800, 450


def _frame(rect=None, shade=255) -> Image.Image:
    img = Image.new("RGB", (_W, _H), "black")
    if rect is not None:
        ImageDraw.Draw(img).rectangle(rect, fill=(shade, shade, shade))
    return img


def test_first_frame_scans_immediately() -> None:
    pacer = FramePacer()
    d = pacer.observe(_frame(), now=100.0)
    assert d.scan is True
    assert d.reason == "startup"
    assert d.sweep == "full"
    print("  [ok] first frame triggers a startup scan")


def test_static_screen_skips_inference_until_safety_sweep() -> None:
    pacer = FramePacer()
    pacer.observe(_frame(), now=100.0)
    d = pacer.observe(_frame(), now=100.4)
    assert d.scan is False
    d = pacer.observe(_frame(), now=100.0 + SAFETY_SWEEP_SECONDS + 0.1)
    assert d.scan is True
    assert d.reason == "periodic"
    print("  [ok] static screen scans only on the safety sweep")


def test_change_burst_scans_at_once_with_changed_box() -> None:
    pacer = FramePacer()
    pacer.observe(_frame(), now=100.0)
    pacer.observe(_frame(), now=105.0)  # calm gap so the next change is a burst
    rect = (300, 150, 520, 330)
    d = pacer.observe(_frame(rect), now=105.4)
    assert d.scan is True
    assert d.reason == "burst"
    assert d.changed_box is not None
    left, top, right, bottom = d.changed_box
    cx, cy = (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
    assert left <= cx <= right and top <= cy <= bottom
    print("  [ok] change burst scans immediately and localizes the change")


def test_settle_scan_after_change_stops() -> None:
    pacer = FramePacer()
    pacer.observe(_frame(), now=100.0)
    pacer.observe(_frame(), now=105.0)
    d = pacer.observe(_frame((100, 100, 400, 300)), now=105.4)   # burst scan
    assert d.scan is True and d.reason == "burst"
    # More change after the burst (scroll continues), no scan yet.
    pacer.observe(_frame((300, 100, 700, 350)), now=105.8)
    d = pacer.observe(_frame((300, 100, 700, 350)), now=106.2)   # now static
    assert d.scan is True
    assert d.reason == "settle"
    assert d.changed_box is not None  # carries the change since last scan
    print("  [ok] settled frame is scanned right after change stops")


def test_settle_skipped_when_frame_already_scanned() -> None:
    # The burst scanned the exact frame the screen settled on: a settle
    # re-scan of identical pixels is wasted inference and is skipped.
    pacer = FramePacer()
    pacer.observe(_frame(), now=100.0)
    pacer.observe(_frame(), now=105.0)
    d = pacer.observe(_frame((100, 100, 400, 300)), now=105.4)   # burst scan
    assert d.scan is True
    d = pacer.observe(_frame((100, 100, 400, 300)), now=105.8)   # static, same frame
    assert d.scan is False
    print("  [ok] settle skipped when the settled frame was already scanned")


def test_burst_uses_targeted_sweep() -> None:
    pacer = FramePacer()
    pacer.observe(_frame(), now=100.0)
    pacer.observe(_frame(), now=105.0)
    d = pacer.observe(_frame((100, 100, 400, 300)), now=105.4)
    assert d.scan is True and d.reason == "burst"
    assert d.sweep == "targeted"
    print("  [ok] burst scans run the cheap targeted profile")


def test_accumulated_change_carries_across_skipped_ticks() -> None:
    pacer = FramePacer()
    pacer.observe(_frame(), now=100.0)
    pacer.observe(_frame(), now=105.0)
    pacer.observe(_frame((50, 50, 200, 200)), now=105.4)        # burst scan, accum reset
    pacer.observe(_frame((500, 250, 750, 420)), now=105.8)      # change, no scan
    d = pacer.observe(_frame((500, 250, 750, 420)), now=106.2)  # settle scan
    assert d.scan is True
    left, top, right, bottom = d.changed_box
    assert left <= 625 <= right and top <= 335 <= bottom  # right-area center
    print("  [ok] change accumulated across skipped ticks reaches the next scan")


def test_power_saver_stretches_repeat_cadences() -> None:
    pacer = FramePacer(sustained_scan_seconds=2.0)
    pacer.power_saver = True
    pacer.observe(_frame(), now=100.0)
    d = pacer.observe(_frame(), now=100.5)
    assert abs(d.tick_seconds - 0.6) < 1e-9  # active tick 0.4 * 1.5
    d = pacer.observe(_frame(), now=100.0 + IDLE_AFTER_SECONDS + 1.0)
    assert abs(d.tick_seconds - 1.5) < 1e-9  # idle tick 1.0 * 1.5
    print("  [ok] power saver stretches tick cadences 1.5x")


def test_sustained_change_uses_budgeted_targeted_cadence() -> None:
    pacer = FramePacer(sustained_scan_seconds=2.0)
    now = 100.0
    pacer.observe(_frame(), now=now)
    toggle = False
    scans = []
    # Alternate frames every 0.4s for 8 seconds, like video playback.
    while now < 108.0:
        now += 0.4
        toggle = not toggle
        rect = (200, 100, 600, 350) if toggle else (200, 100, 600, 349)
        frame = _frame(rect, shade=255 if toggle else 40)
        d = pacer.observe(frame, now=now)
        if d.scan:
            scans.append((round(now - 100.0, 1), d.reason, d.sweep))
    sustained = [s for s in scans if s[1] == "sustained"]
    assert sustained, f"expected sustained scans, got {scans}"
    # Sustained scans must be spaced by at least the budget.
    times = [s[0] for s in sustained]
    assert all(b - a >= 1.9 for a, b in zip(times, times[1:])), times
    # Within the full-sweep refresh window they run the cheap targeted profile.
    assert any(s[2] == "targeted" for s in sustained)
    print("  [ok] sustained change scans on a budgeted targeted cadence")


def test_idle_screen_slows_ticks() -> None:
    pacer = FramePacer()
    pacer.observe(_frame(), now=100.0)
    d = pacer.observe(_frame(), now=100.0 + IDLE_AFTER_SECONDS + 1.0)
    assert d.tick_seconds == IDLE_TICK_SECONDS
    d = pacer.observe(_frame((0, 0, 300, 300)), now=100.0 + IDLE_AFTER_SECONDS + 2.0)
    assert d.tick_seconds == ACTIVE_TICK_SECONDS
    print("  [ok] ticks slow when idle and speed back up on change")


def test_forced_confirm_scan_is_targeted() -> None:
    pacer = FramePacer()
    pacer.observe(_frame(), now=100.0)
    d = pacer.observe(_frame(), now=100.4, force_scan=True, force_reason="confirm")
    assert d.scan is True
    assert d.reason == "confirm"
    assert d.sweep == "targeted"
    print("  [ok] forced confirmation scan runs the targeted profile")


def test_window_change_forces_full_scan() -> None:
    pacer = FramePacer()
    pacer.observe(_frame(), now=100.0)
    d = pacer.observe(_frame(), now=100.4, force_scan=True, force_reason="window")
    assert d.scan is True
    assert d.reason == "window"
    assert d.sweep == "full"
    print("  [ok] window change forces an immediate full scan")


def main() -> int:
    tests = [
        test_first_frame_scans_immediately,
        test_static_screen_skips_inference_until_safety_sweep,
        test_change_burst_scans_at_once_with_changed_box,
        test_settle_scan_after_change_stops,
        test_settle_skipped_when_frame_already_scanned,
        test_burst_uses_targeted_sweep,
        test_accumulated_change_carries_across_skipped_ticks,
        test_power_saver_stretches_repeat_cadences,
        test_sustained_change_uses_budgeted_targeted_cadence,
        test_idle_screen_slows_ticks,
        test_forced_confirm_scan_is_targeted,
        test_window_change_forces_full_scan,
    ]
    for fn in tests:
        print(f"\n{fn.__name__}")
        fn()
    print("\nAll tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
