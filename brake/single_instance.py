"""Kernel-enforced single-instance lock via a named Windows mutex.

The old approach (read agent.pid, check the pid is alive, then write our own
pid) had two failure modes:

- check-then-write race: several agents starting at once all pass the check
  before any of them writes the file, so duplicates stack up
- pid reuse: a recycled pid makes a dead agent look alive, so no agent starts

A named mutex has neither problem. Creation is atomic in the kernel, the
handle is released automatically when the process dies, and the name is
scoped per logon session (``Local\\``) so one agent can run per session,
which matches how the service spawns agents.
"""
from __future__ import annotations

import logging
import sys
from typing import Optional

_log = logging.getLogger(__name__)

ERROR_ALREADY_EXISTS = 183

AGENT_MUTEX_NAME = "Local\\BrakeAgentSingleton"


class SingleInstanceLock:
    """Holds a named mutex for the lifetime of this object/process."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._handle: Optional[object] = None

    def acquire(self) -> bool:
        """Return True when this process now owns the name, False when
        another live process in this session already holds it."""
        if sys.platform != "win32":
            return True
        try:
            import win32api    # type: ignore[import-not-found]
            import win32event  # type: ignore[import-not-found]
        except ImportError:
            _log.warning("pywin32 unavailable; single-instance lock skipped.")
            return True
        try:
            handle = win32event.CreateMutex(None, False, self.name)
            already_exists = win32api.GetLastError() == ERROR_ALREADY_EXISTS
        except Exception as e:
            _log.warning("single-instance mutex failed (%s); continuing.", e)
            return True
        if already_exists:
            try:
                win32api.CloseHandle(handle)
            except Exception:
                pass
            return False
        self._handle = handle
        return True

    def release(self) -> None:
        if self._handle is None:
            return
        try:
            import win32api  # type: ignore[import-not-found]

            win32api.CloseHandle(self._handle)
        except Exception:
            pass
        self._handle = None
