"""Spawn a process into the active user session from a LocalSystem service.

Uses WTSGetActiveConsoleSessionId → WTSQueryUserToken → DuplicateTokenEx →
CreateProcessAsUser. Returns (True, pid) on success, (False, None) otherwise.

If no user is logged in (login screen), returns (False, None) cleanly.
Logs but doesn't raise on failure — caller decides whether to retry.
"""
from __future__ import annotations

import logging
import os
import sys
from typing import List, Optional, Tuple

_log = logging.getLogger(__name__)

_NO_SESSION = 0xFFFFFFFF


def _quote(arg: str) -> str:
    if " " in arg and not (arg.startswith('"') and arg.endswith('"')):
        return f'"{arg}"'
    return arg


def spawn_in_user_session(command: List[str], cwd: Optional[str] = None,
                          extra_env: Optional[dict] = None) -> Tuple[bool, Optional[int]]:
    if sys.platform != "win32":
        return False, None
    try:
        import win32api          # type: ignore[import-not-found]
        import win32con          # type: ignore[import-not-found]
        import win32process      # type: ignore[import-not-found]
        import win32profile      # type: ignore[import-not-found]
        import win32security     # type: ignore[import-not-found]
        import win32ts           # type: ignore[import-not-found]
    except ImportError as e:
        _log.error("pywin32 missing: %s", e)
        return False, None

    try:
        session_id = win32ts.WTSGetActiveConsoleSessionId()
    except Exception as e:
        _log.error("WTSGetActiveConsoleSessionId failed: %s", e)
        return False, None
    if session_id == _NO_SESSION:
        _log.debug("No active console session (login screen).")
        return False, None

    try:
        user_token = win32ts.WTSQueryUserToken(session_id)
    except Exception as e:
        _log.warning("WTSQueryUserToken failed for session %s: %s", session_id, e)
        return False, None

    primary_token = None
    try:
        primary_token = win32security.DuplicateTokenEx(
            user_token,
            win32security.SecurityImpersonation,
            win32con.MAXIMUM_ALLOWED,
            win32security.TokenPrimary,
        )
    except Exception as e:
        _log.error("DuplicateTokenEx failed: %s", e)
        return False, None
    finally:
        try: win32api.CloseHandle(user_token)
        except Exception: pass

    try:
        env = win32profile.CreateEnvironmentBlock(primary_token, False)
        if extra_env:
            # Merge — env is a dict from pywin32
            env = dict(env)
            env.update(extra_env)
    except Exception as e:
        _log.warning("CreateEnvironmentBlock failed (continuing without env): %s", e)
        env = None

    si = win32process.STARTUPINFO()
    si.lpDesktop = r"winsta0\default"

    exe = command[0]
    cmd_line = " ".join(_quote(c) for c in command)
    flags = (win32con.NORMAL_PRIORITY_CLASS
             | win32con.CREATE_UNICODE_ENVIRONMENT
             | win32con.CREATE_NO_WINDOW)

    pid = None
    try:
        hProcess, hThread, pid, tid = win32process.CreateProcessAsUser(
            primary_token, exe, cmd_line, None, None, False,
            flags, env, cwd, si,
        )
        _log.info("Spawned in user session %s: pid=%s cmd=%s", session_id, pid, cmd_line)
        try: win32api.CloseHandle(hProcess)
        except Exception: pass
        try: win32api.CloseHandle(hThread)
        except Exception: pass
        return True, pid
    except Exception as e:
        _log.error("CreateProcessAsUser failed: %s", e)
        return False, None
    finally:
        try: win32api.CloseHandle(primary_token)
        except Exception: pass
