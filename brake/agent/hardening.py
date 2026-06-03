"""Close Task Manager / appwiz / timedate windows while protection is enabled.

Runs in the user session (the only session where it has visibility of user
windows). Matches by case-insensitive title substring; PostMessage WM_CLOSE
on the offending top-level window.
"""
from __future__ import annotations

import ctypes
import logging
import threading
from ctypes import wintypes
from typing import List

from brake.config import load_settings
from brake.state import StateStore, StateTamperedError

_log = logging.getLogger(__name__)

# Title substrings (case-insensitive) we close while protected.
DEFAULT_BLOCK_TITLES: List[str] = [
    # Process / service control
    "Task Manager",
    "Resource Monitor",
    "Services",                 # services.msc — main way to stop the service
    "Computer Management",      # contains Services snap-in too
    "System Configuration",     # msconfig — disables services at boot
    # Registry / policy editors — can flip the service to disabled
    "Registry Editor",
    "Group Policy",             # gpedit.msc
    "Local Security Policy",    # secpol.msc
    # Install/uninstall paths
    "Programs and Features",
    "Apps & features",
    "Installed apps",           # newer Windows 11 wording
    "Add or remove programs",
    "Brake Uninstall",
    "Brake Uninstall",
    # Less obvious bypasses
    "Date and time",
    "Date & time",
    "Control Panel",            # parent for several of the above
]

WM_CLOSE = 0x0010


def _user32():
    return ctypes.WinDLL("user32", use_last_error=True)


_EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def _list_visible_hwnds() -> List[int]:
    user32 = _user32()
    handles: list[int] = []

    @_EnumWindowsProc
    def cb(hwnd, _lparam):
        if user32.IsWindowVisible(hwnd):
            handles.append(hwnd)
        return True

    user32.EnumWindows(cb, 0)
    return handles


def _window_title(hwnd: int) -> str:
    user32 = _user32()
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


class HardeningLoop(threading.Thread):
    daemon = True

    def __init__(self, stop_event: threading.Event) -> None:
        super().__init__(name="HardeningLoop")
        self.stop_event = stop_event
        self.store = StateStore()
        settings = load_settings()
        self.poll_seconds = max(0.05, settings.hardening.poll_interval_ms / 1000.0)
        self.titles = [t.lower() for t in DEFAULT_BLOCK_TITLES]

    def _protected(self) -> bool:
        try:
            s = self.store.load()
        except StateTamperedError:
            return True  # fail-secure: keep hardening on
        return bool(s and s.enabled)

    def run(self) -> None:
        _log.info("Hardening loop starting (poll=%.2fs, titles=%d).",
                  self.poll_seconds, len(self.titles))
        user32 = _user32()
        while not self.stop_event.is_set():
            try:
                if self._protected():
                    for hwnd in _list_visible_hwnds():
                        title = _window_title(hwnd).lower()
                        if not title:
                            continue
                        for pattern in self.titles:
                            if pattern in title:
                                user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
                                _log.warning("hardening: closed '%s'", title)
                                break
            except Exception as e:
                _log.exception("hardening loop error: %s", e)
            self.stop_event.wait(self.poll_seconds)
        _log.info("Hardening loop stopped.")
