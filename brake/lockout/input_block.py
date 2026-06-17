"""Low-level keyboard hook that swallows escape combos during a lockout.

Uses Win32 SetWindowsHookEx WH_KEYBOARD_LL via ctypes. No admin required —
the hook runs in the calling process's user session. Requires a Windows
message pump (Qt's event loop provides one).

What we block (matches Cold Turkey's surface area):
  - Windows key (LWIN, RWIN) — any modifier combo
  - Alt+Tab, Alt+F4, Alt+Esc, Alt+Space
  - Ctrl+Esc (Start menu)
  - Ctrl+Shift+Esc (Task Manager)

What we cannot block (kernel-level, would require a driver):
  - Ctrl+Alt+Del (raises Secure Desktop; user can sign out but service
    + watchdog re-trigger on next login)
"""
from __future__ import annotations

import ctypes
import logging
import sys
from ctypes import POINTER, Structure, WINFUNCTYPE, c_int, c_long, wintypes
from typing import Optional

_log = logging.getLogger(__name__)

# ---- Win32 constants ----
WH_KEYBOARD_LL = 13
HC_ACTION = 0
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104

LLKHF_ALTDOWN = 0x20

VK_TAB = 0x09
VK_CAPITAL = 0x14
VK_ESCAPE = 0x1B
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_LWIN = 0x5B
VK_RWIN = 0x5C
VK_F4 = 0x73
VK_SPACE = 0x20


class _KBDLLHOOKSTRUCT(Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", wintypes.WPARAM),
    ]


_HOOKPROC = WINFUNCTYPE(c_long, c_int, wintypes.WPARAM, wintypes.LPARAM)


class KeyboardBlocker:
    """Installable LL keyboard hook. Use as a context manager."""

    def __init__(self) -> None:
        self._hook_id: Optional[int] = None
        self._user32 = None
        self._kernel32 = None
        self._proc_ref = None  # keep the cb alive; GC would break the hook

    def __enter__(self) -> "KeyboardBlocker":
        self.install()
        return self

    def __exit__(self, *exc) -> None:
        self.uninstall()

    def install(self) -> None:
        if sys.platform != "win32":
            _log.warning("KeyboardBlocker is a no-op on non-Windows.")
            return
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        self._user32.SetWindowsHookExW.restype = wintypes.HHOOK
        self._user32.SetWindowsHookExW.argtypes = [
            c_int, _HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD,
        ]
        self._user32.CallNextHookEx.restype = wintypes.LPARAM
        self._user32.CallNextHookEx.argtypes = [
            wintypes.HHOOK, c_int, wintypes.WPARAM, wintypes.LPARAM,
        ]
        self._user32.GetAsyncKeyState.restype = wintypes.SHORT
        self._user32.GetAsyncKeyState.argtypes = [c_int]
        self._user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
        self._kernel32.GetModuleHandleW.restype = wintypes.HMODULE
        self._kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]

        self._proc_ref = _HOOKPROC(self._callback)
        hmod = self._kernel32.GetModuleHandleW(None)
        self._hook_id = self._user32.SetWindowsHookExW(
            WH_KEYBOARD_LL, self._proc_ref, hmod, 0,
        )
        if not self._hook_id:
            err = ctypes.get_last_error()
            raise OSError(f"SetWindowsHookExW failed (err={err})")
        _log.info("Keyboard hook installed.")

    def uninstall(self) -> None:
        if self._hook_id and self._user32:
            self._user32.UnhookWindowsHookEx(self._hook_id)
            _log.info("Keyboard hook removed.")
        self._hook_id = None
        self._proc_ref = None

    def _is_down(self, vk: int) -> bool:
        return bool(self._user32.GetAsyncKeyState(vk) & 0x8000)

    def _callback(self, n_code: int, w_param: int, l_param: int) -> int:
        if n_code != HC_ACTION or w_param not in (WM_KEYDOWN, WM_SYSKEYDOWN):
            return self._user32.CallNextHookEx(self._hook_id, n_code, w_param, l_param)

        kb = ctypes.cast(l_param, POINTER(_KBDLLHOOKSTRUCT))[0]
        vk = kb.vkCode
        alt = bool(kb.flags & LLKHF_ALTDOWN)
        ctrl = self._is_down(VK_CONTROL)
        shift = self._is_down(VK_SHIFT)

        if self._should_block(vk, alt=alt, ctrl=ctrl, shift=shift):
            return 1

        return self._user32.CallNextHookEx(self._hook_id, n_code, w_param, l_param)

    @staticmethod
    def _should_block(vk: int, *, alt: bool, ctrl: bool, shift: bool) -> bool:
        # Recovery entry must remain usable during lockout. Let regular text
        # input through, including Caps Lock and Shift-modified characters.
        if vk in (VK_CAPITAL, VK_SHIFT):
            return False

        # Windows keys: always swallow
        if vk in (VK_LWIN, VK_RWIN):
            return True
        # Alt+anything escapy
        if alt and vk in (VK_TAB, VK_F4, VK_ESCAPE, VK_SPACE):
            return True
        # Ctrl+Esc (Start) and Ctrl+Shift+Esc (Task Manager)
        if vk == VK_ESCAPE and (ctrl or shift):
            return True

        return False
