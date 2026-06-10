"""Tests for fullscreen/share-aware scan timing hints."""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from brake.service.scan_environment import (
    ScanEnvironmentMonitor,
    WindowSnapshot,
    _contains_active_share_keyword,
    _rect_covers,
)


def test_rect_covers_with_tolerance() -> None:
    monitor = (0, 0, 1920, 1080)
    assert _rect_covers(monitor, (-2, -2, 1921, 1081))
    assert not _rect_covers(monitor, (100, 100, 1800, 900))
    print("  [ok] fullscreen rect matching uses tolerance")


def test_fullscreen_transition_sets_debounce() -> None:
    monitor = ScanEnvironmentMonitor(transition_pause_seconds=2.0)
    snapshots = iter([
        WindowSnapshot(fullscreen=False),
        WindowSnapshot(fullscreen=True, process_name="video.exe", title="Video"),
    ])
    monitor._snapshot = lambda: next(snapshots)  # type: ignore[method-assign]
    monitor.sample(now=100.0)
    monitor.sample(now=101.0)
    assert monitor._transition_until == 103.0
    print("  [ok] fullscreen transition arms scan debounce")


def test_share_sensitive_clean_scan_interval() -> None:
    monitor = ScanEnvironmentMonitor()
    monitor._snapshot = lambda: WindowSnapshot(share_sensitive=True)  # type: ignore[method-assign]
    assert monitor.clean_scan_interval(3) == 5.0
    assert monitor.clean_scan_interval(10) == 10.0
    print("  [ok] share-sensitive clean scans are gently slowed")


def test_foreground_share_detection_uses_process_not_app_name_in_title() -> None:
    monitor = ScanEnvironmentMonitor()
    # Dedicated share apps are still matched by process name.
    assert monitor._share_sensitive("discord.exe", "#general - Discord")
    assert monitor._share_sensitive("zoom.exe", "Zoom")
    # A browser tab merely mentioning an app name must not throttle scanning.
    assert not monitor._share_sensitive("chrome.exe", "best discord moments - YouTube - Google Chrome")
    assert not monitor._share_sensitive("chrome.exe", "OBS tutorial - Google Chrome")
    # Real meeting/share titles still count.
    assert monitor._share_sensitive("chrome.exe", "Google Meet - weekly sync")
    assert monitor._share_sensitive("chrome.exe", "Zoom Meeting - Zoom")
    print("  [ok] foreground share detection matches apps by process, not title mentions")


def test_background_windows_need_active_share_titles() -> None:
    # A background Discord/Slack window simply existing is not a share.
    assert not _contains_active_share_keyword("#general - Discord")
    assert not _contains_active_share_keyword("Slack - workspace")
    # Active-share indicator windows do count.
    assert _contains_active_share_keyword("Zoom is sharing your screen")
    assert _contains_active_share_keyword("Stop sharing")
    assert _contains_active_share_keyword("Slack huddle")
    print("  [ok] background windows only count with active share titles")


def main() -> int:
    for fn in (
        test_rect_covers_with_tolerance,
        test_fullscreen_transition_sets_debounce,
        test_share_sensitive_clean_scan_interval,
        test_foreground_share_detection_uses_process_not_app_name_in_title,
        test_background_windows_need_active_share_titles,
    ):
        print(f"\n{fn.__name__}")
        fn()
    print("\nAll tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())