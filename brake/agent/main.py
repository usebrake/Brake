"""Brake user-session agent.

Owns:
  - the screen-capture watcher loop (NudeNet + anime NSFW)
  - the hardening loop (closes Task Manager / timedate / appwiz while protected)
  - the agent.pid file (so the service supervisor knows we're alive)

Spawned by:
  - the service's agent supervisor (CreateProcessAsUser into the active session)
  - the HKCU Run key at login (boot recovery + belt-and-suspenders)
  - the user manually (`python -m brake.agent`) for dev

Single-instance: bails out cleanly if another agent.pid is already alive.
"""
from __future__ import annotations

import logging
import os
import signal
import sys
import threading

from brake import paths
from brake.agent.hardening import HardeningLoop
from brake.lockout.recovery import spawn_resume_lockout_if_needed
from brake.service.watcher import Watcher
from brake.test_mode import log_banner_once

_log = logging.getLogger(__name__)


def _pid_file():
    return paths.data_dir() / "agent.pid"


def _another_agent_alive() -> bool:
    f = _pid_file()
    if not f.exists():
        return False
    try:
        pid = int(f.read_text().strip())
    except Exception:
        return False
    if pid == os.getpid():
        return False
    try:
        import psutil
        return psutil.pid_exists(pid)
    except Exception:
        return False


def _write_pid() -> None:
    _pid_file().write_text(str(os.getpid()), encoding="utf-8")


def _clear_pid() -> None:
    f = _pid_file()
    try:
        # Only clear if it's ours — protects against a race where another agent
        # has already written its own pid.
        if f.exists() and int(f.read_text().strip()) == os.getpid():
            f.unlink()
    except Exception:
        pass


def _configure_logging() -> None:
    handler = logging.FileHandler(paths.logs_dir() / "agent.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for h in list(root.handlers):
        if isinstance(h, logging.FileHandler):
            root.removeHandler(h)
    root.addHandler(handler)
    # also echo to stderr so foreground dev runs see output
    root.addHandler(logging.StreamHandler(sys.stderr))


def main() -> int:
    _configure_logging()
    if _another_agent_alive():
        _log.info("Another agent is alive; exiting.")
        return 0
    _write_pid()
    _log.info("Agent starting (pid=%s).", os.getpid())
    log_banner_once()
    spawn_resume_lockout_if_needed("agent-start")

    stop = threading.Event()

    def _shutdown(*_args) -> None:
        stop.set()
    for sig_name in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, sig_name, None)
        if sig is not None:
            try:
                signal.signal(sig, _shutdown)
            except Exception:
                pass

    hardening = HardeningLoop(stop)
    hardening.start()

    try:
        Watcher().run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        _clear_pid()
        _log.info("Agent stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
