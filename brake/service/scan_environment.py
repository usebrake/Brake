"""Best-effort scan timing hints for fullscreen and screen sharing.

This module does not decide what is explicit. It only helps the watcher avoid
capturing during moments when Windows desktop composition is most fragile, such
as entering fullscreen video or running screen-share software.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional, Tuple

_log = logging.getLogger(__name__)

FULLSCREEN_TRANSITION_PAUSE_SECONDS = 2.0
SHARE_CLEAN_SCAN_INTERVAL_SECONDS = 5.0
_FULLSCREEN_TOLERANCE_PX = 4

_BROWSER_PROCESSES = {"chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe"}
_DEDICATED_SHARE_PROCESSES = {
    "discord.exe",
    "zoom.exe",
    "zoommtg.exe",
    "teams.exe",
    "ms-teams.exe",
    "obs32.exe",
    "obs64.exe",
    "streamlabs desktop.exe",
    "webex.exe",
    "webexmta.exe",
    "skype.exe",
    "slack.exe",
}
# Foreground-window titles that suggest a meeting or share is on screen.
# Bare app names (discord, obs, ...) are intentionally absent: those apps are
# matched by process name instead, so a browser tab merely mentioning them
# does not slow scanning.
_SHARE_TITLE_KEYWORDS = (
    "screen share",
    "screenshare",
    "sharing",
    "google meet",
    "zoom meeting",
    "microsoft teams",
    "slack huddle",
    "huddle",
)
# Background windows only count when their title clearly indicates an active
# share. A Discord/Slack/OBS window simply existing somewhere must not throttle
# every clean scan.
_ACTIVE_SHARE_TITLE_KEYWORDS = (
    "screen share",
    "screenshare",
    "sharing your screen",
    "is sharing",
    "you are sharing",
    "stop sharing",
    "huddle",
)

Rect = Tuple[int, int, int, int]


@dataclass(frozen=True)
class WindowSnapshot:
    hwnd: int = 0
    process_name: str = ""
    title: str = ""
    window_rect: Rect = (0, 0, 0, 0)
    monitor_rect: Rect = (0, 0, 0, 0)
    virtual_screen: Rect = (0, 0, 0, 0)
    fullscreen: bool = False
    share_sensitive: bool = False


def _rect_covers(container: Rect, candidate: Rect, tolerance: int = _FULLSCREEN_TOLERANCE_PX) -> bool:
    cl, ct, cr, cb = container
    wl, wt, wr, wb = candidate
    if wr <= wl or wb <= wt or cr <= cl or cb <= ct:
        return False
    return (
        wl <= cl + tolerance
        and wt <= ct + tolerance
        and wr >= cr - tolerance
        and wb >= cb - tolerance
    )


def _contains_share_keyword(title: str) -> bool:
    lowered = title.lower()
    return any(keyword in lowered for keyword in _SHARE_TITLE_KEYWORDS)


def _contains_active_share_keyword(title: str) -> bool:
    lowered = title.lower()
    return any(keyword in lowered for keyword in _ACTIVE_SHARE_TITLE_KEYWORDS)


class ScanEnvironmentMonitor:
    """Tracks scan timing conditions without changing detection policy."""

    def __init__(self, transition_pause_seconds: float = FULLSCREEN_TRANSITION_PAUSE_SECONDS) -> None:
        self.transition_pause_seconds = max(0.0, float(transition_pause_seconds))
        self._transition_until = 0.0
        self._last_fullscreen: Optional[bool] = None
        self._last_virtual_screen: Optional[Rect] = None
        self._last_logged_state: Optional[tuple[bool, bool]] = None
        self._process_cache: dict[int, tuple[float, str]] = {}
        # Walking every top-level window is too heavy for the watcher's fast
        # tick, so the background-share answer is cached briefly.
        self._background_share_cache: tuple[float, bool] = (0.0, False)
        self.last_snapshot: Optional[WindowSnapshot] = None

    def defer_seconds(self) -> float:
        now = time.monotonic()
        self.sample(now)
        return max(0.0, self._transition_until - now)

    def clean_scan_interval(self, base_interval: float) -> float:
        snapshot = self.sample(time.monotonic())
        if snapshot.share_sensitive:
            return max(float(base_interval), SHARE_CLEAN_SCAN_INTERVAL_SECONDS)
        return float(base_interval)

    def sample(self, now: Optional[float] = None) -> WindowSnapshot:
        now = time.monotonic() if now is None else now
        snapshot = self._snapshot()

        if self._last_fullscreen is not None and snapshot.fullscreen != self._last_fullscreen:
            self._transition_until = max(self._transition_until, now + self.transition_pause_seconds)
            _log.info(
                "scan debounce: fullscreen transition fullscreen=%s pause=%.1fs process=%s title=%s",
                snapshot.fullscreen,
                self.transition_pause_seconds,
                snapshot.process_name,
                snapshot.title[:80],
            )

        if self._last_virtual_screen is not None and snapshot.virtual_screen != self._last_virtual_screen:
            self._transition_until = max(self._transition_until, now + self.transition_pause_seconds)
            _log.info("scan debounce: display geometry changed pause=%.1fs", self.transition_pause_seconds)

        self._last_fullscreen = snapshot.fullscreen
        self._last_virtual_screen = snapshot.virtual_screen

        self.last_snapshot = snapshot
        state = (snapshot.fullscreen, snapshot.share_sensitive)
        if state != self._last_logged_state:
            self._last_logged_state = state
            _log.info(
                "scan environment: fullscreen=%s share_sensitive=%s process=%s title=%s",
                snapshot.fullscreen,
                snapshot.share_sensitive,
                snapshot.process_name,
                snapshot.title[:80],
            )
        return snapshot

    def _snapshot(self) -> WindowSnapshot:
        if not _is_windows_available():
            return WindowSnapshot()
        try:
            return self._windows_snapshot()
        except Exception as e:
            _log.debug("scan environment probe failed: %s", e)
            return WindowSnapshot()

    def _windows_snapshot(self) -> WindowSnapshot:
        import win32api      # type: ignore[import-not-found]
        import win32con      # type: ignore[import-not-found]
        import win32gui      # type: ignore[import-not-found]

        hwnd = int(win32gui.GetForegroundWindow() or 0)
        title = _window_title(hwnd)
        process_name = self._process_name(hwnd)
        window_rect = _safe_window_rect(hwnd)
        monitor_rect = _monitor_rect_for_window(hwnd)
        virtual_screen = (
            int(win32api.GetSystemMetrics(win32con.SM_XVIRTUALSCREEN)),
            int(win32api.GetSystemMetrics(win32con.SM_YVIRTUALSCREEN)),
            int(win32api.GetSystemMetrics(win32con.SM_XVIRTUALSCREEN) + win32api.GetSystemMetrics(win32con.SM_CXVIRTUALSCREEN)),
            int(win32api.GetSystemMetrics(win32con.SM_YVIRTUALSCREEN) + win32api.GetSystemMetrics(win32con.SM_CYVIRTUALSCREEN)),
        )
        fullscreen = _rect_covers(monitor_rect, window_rect) if hwnd else False
        share_sensitive = self._share_sensitive(process_name, title)
        if not share_sensitive:
            share_sensitive = self._any_share_window_visible_cached()
        return WindowSnapshot(
            hwnd=hwnd,
            process_name=process_name,
            title=title,
            window_rect=window_rect,
            monitor_rect=monitor_rect,
            virtual_screen=virtual_screen,
            fullscreen=fullscreen,
            share_sensitive=share_sensitive,
        )

    def _process_name(self, hwnd: int) -> str:
        if not hwnd:
            return ""
        try:
            import win32process  # type: ignore[import-not-found]

            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            return self._process_name_by_pid(int(pid))
        except Exception:
            return ""

    def _process_name_by_pid(self, pid: int) -> str:
        now = time.monotonic()
        cached = self._process_cache.get(pid)
        if cached and now - cached[0] < 10.0:
            return cached[1]
        try:
            import psutil  # type: ignore[import-not-found]

            name = (psutil.Process(pid).name() or "").lower()
        except Exception:
            name = ""
        self._process_cache[pid] = (now, name)
        if len(self._process_cache) > 128:
            stale = [key for key, value in self._process_cache.items() if now - value[0] > 30.0]
            for key in stale:
                self._process_cache.pop(key, None)
        return name

    def _share_sensitive(self, process_name: str, title: str) -> bool:
        process_name = process_name.lower()
        if process_name in _DEDICATED_SHARE_PROCESSES:
            return True
        if process_name in _BROWSER_PROCESSES and _contains_share_keyword(title):
            return True
        return _contains_share_keyword(title)

    def _any_share_window_visible_cached(self, ttl_seconds: float = 5.0) -> bool:
        now = time.monotonic()
        checked_at, value = self._background_share_cache
        if now - checked_at < ttl_seconds:
            return value
        value = self._any_share_window_visible()
        self._background_share_cache = (now, value)
        return value

    def _any_share_window_visible(self) -> bool:
        try:
            import win32gui      # type: ignore[import-not-found]
        except Exception:
            return False

        found = False

        def visit(hwnd, _extra):
            nonlocal found
            if found:
                return False
            try:
                if not win32gui.IsWindowVisible(hwnd):
                    return True
                title = _window_title(hwnd)
                if not title:
                    return True
                if _contains_active_share_keyword(title):
                    found = True
                    return False
            except Exception:
                return True
            return True

        try:
            win32gui.EnumWindows(visit, None)
        except Exception:
            return False
        return found


def _is_windows_available() -> bool:
    try:
        import win32api  # type: ignore[import-not-found]  # noqa: F401
        import win32gui  # type: ignore[import-not-found]  # noqa: F401
        return True
    except Exception:
        return False


def _window_title(hwnd: int) -> str:
    if not hwnd:
        return ""
    try:
        import win32gui  # type: ignore[import-not-found]

        return win32gui.GetWindowText(hwnd) or ""
    except Exception:
        return ""


def _safe_window_rect(hwnd: int) -> Rect:
    if not hwnd:
        return (0, 0, 0, 0)
    try:
        import win32gui  # type: ignore[import-not-found]

        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        return (int(left), int(top), int(right), int(bottom))
    except Exception:
        return (0, 0, 0, 0)


def _monitor_rect_for_window(hwnd: int) -> Rect:
    try:
        import win32api  # type: ignore[import-not-found]
        import win32con  # type: ignore[import-not-found]

        monitor = win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONEAREST)
        info = win32api.GetMonitorInfo(monitor)
        left, top, right, bottom = info.get("Monitor", (0, 0, 0, 0))
        return (int(left), int(top), int(right), int(bottom))
    except Exception:
        return (0, 0, 0, 0)