"""HKCU Run-key autostart hook so a reboot mid-lockout still recovers.

We register `HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run\\Brake`
pointing at the boot recovery script. It runs on every user login, exits
silently if there's no active lockout, otherwise re-spawns the lockout
window with the remaining time.

HKCU is user-scope (no admin needed) and only fires when this user logs in.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from brake.runtime import frozen, lockout_command

_log = logging.getLogger(__name__)

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "Brake"

REPO_ROOT = Path(__file__).resolve().parent.parent
BOOT_SCRIPT = REPO_ROOT / "brake" / "boot.py"


def _pythonw_path() -> str:
    """Find pythonw.exe (windowless) so the recovery flash doesn't show a console."""
    exe = sys.executable
    candidate = exe.replace("python.exe", "pythonw.exe")
    return candidate if os.path.exists(candidate) else exe


def _build_command() -> str:
    if frozen():
        return " ".join(f'"{part}"' if " " in part else part for part in lockout_command([]))
    pythonw = _pythonw_path()
    return f'"{pythonw}" "{BOOT_SCRIPT}"'


def ensure_boot_entry() -> None:
    """Idempotently install the HKCU Run key entry."""
    if sys.platform != "win32":
        return
    import winreg
    cmd = _build_command()
    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, VALUE_NAME, 0, winreg.REG_SZ, cmd)
        _log.info("Autostart entry installed: %s", cmd)
    except OSError as e:
        _log.error("Failed to install autostart entry: %s", e)


def remove_boot_entry() -> None:
    if sys.platform != "win32":
        return
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            for value_name in (VALUE_NAME, "Brake"):
                try:
                    winreg.DeleteValue(k, value_name)
                except FileNotFoundError:
                    pass
        _log.info("Autostart entry removed.")
    except FileNotFoundError:
        pass
    except OSError as e:
        _log.error("Failed to remove autostart entry: %s", e)


def current_entry() -> str | None:
    if sys.platform != "win32":
        return None
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as k:
            value, _ = winreg.QueryValueEx(k, VALUE_NAME)
            return str(value)
    except FileNotFoundError:
        return None
