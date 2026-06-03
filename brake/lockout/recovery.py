"""Recovery helpers for lockouts that survive restart.

The persistent lockout record uses an absolute wall-clock end time. If Windows
is off past that time, the lockout expires. If the user logs back in before
that time, this module re-spawns the fullscreen lockout with the remaining
time.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import time

from brake import paths
from brake.lockout.persistence import LockoutPersistence, _TamperedLockoutError
from brake.runtime import app_dir, lockout_command

_log = logging.getLogger(__name__)
_RESUME_LOCK_STALE_SECONDS = 10


def _resume_lock_file():
    return paths.data_dir() / "lockout-resume.lock"


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        import psutil
        return psutil.pid_exists(pid)
    except Exception:
        pass
    if sys.platform == "win32":
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def lockout_process_alive() -> bool:
    pid_file = paths.lockout_pid_file()
    if not pid_file.exists():
        return False
    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
    except Exception:
        return False
    if _pid_alive(pid):
        return True
    try:
        pid_file.unlink()
    except OSError:
        pass
    return False


def write_lockout_pid() -> None:
    paths.lockout_pid_file().write_text(str(os.getpid()), encoding="utf-8")
    try:
        _resume_lock_file().unlink()
    except FileNotFoundError:
        pass
    except OSError:
        pass


def clear_lockout_pid() -> None:
    pid_file = paths.lockout_pid_file()
    try:
        if pid_file.exists() and int(pid_file.read_text(encoding="utf-8").strip()) == os.getpid():
            pid_file.unlink()
    except Exception:
        pass


def active_lockout_exists() -> bool:
    persist = LockoutPersistence()
    try:
        record = persist.resume()
    except _TamperedLockoutError:
        return True
    if record is None:
        return False
    if record.is_expired():
        persist.clear()
        return False
    return True


def _acquire_resume_spawn_lock() -> bool:
    lock_path = _resume_lock_file()
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        try:
            age = time.time() - lock_path.stat().st_mtime
            if age > _RESUME_LOCK_STALE_SECONDS:
                lock_path.unlink()
                return _acquire_resume_spawn_lock()
        except OSError:
            pass
        return False
    try:
        os.write(fd, str(os.getpid()).encode("ascii"))
    finally:
        os.close(fd)
    return True


def _clear_resume_spawn_lock() -> None:
    try:
        _resume_lock_file().unlink()
    except FileNotFoundError:
        pass
    except OSError:
        pass


def spawn_resume_lockout_if_needed(source: str = "unknown") -> bool:
    """Spawn resume-mode lockout if a signed active lockout exists.

    Returns True when an active lockout exists, whether it spawned a new
    process or found one already running.
    """
    persist = LockoutPersistence()
    try:
        record = persist.resume()
    except _TamperedLockoutError:
        record = None
    else:
        if record is None:
            return False
        if record.is_expired():
            persist.clear()
            return False

    if lockout_process_alive():
        _log.info("Active lockout already has a live process; source=%s.", source)
        return True

    if not _acquire_resume_spawn_lock():
        _log.info("Active lockout resume already being spawned; source=%s.", source)
        return True

    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    try:
        subprocess.Popen(
            lockout_command([]),
            cwd=str(app_dir()),
            creationflags=creationflags,
            close_fds=True,
        )
        _log.warning("Resumed active lockout from %s.", source)
        return True
    except Exception as e:
        _clear_resume_spawn_lock()
        _log.exception("Failed to resume active lockout from %s: %s", source, e)
        return False
