"""Brake user-session agent.

Owns:
  - the screen-capture watcher loop (NudeNet + anime NSFW)
  - the hardening loop (closes direct service/process bypass tools while protected)
  - the agent.pid file (so the service supervisor knows we're alive)

Spawned by:
  - the service's agent supervisor (CreateProcessAsUser into the active session)
  - the Electron app in repo-dev mode (passes --parent-pid so we die with it)
  - the user manually (`python -m brake.agent`) for dev

Single-instance: a named per-session mutex, acquired before anything else.
Duplicates exit immediately. agent.pid is written only as an advisory marker
for the service supervisor; it is never used to decide whether to run.
"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import threading
import time

from brake import paths
from brake.agent.hardening import HardeningLoop
from brake.lockout.recovery import spawn_resume_lockout_if_needed
from brake.service.watcher import Watcher
from brake.single_instance import AGENT_MUTEX_NAME, SingleInstanceLock
from brake.test_mode import log_banner_once

_log = logging.getLogger(__name__)


def _pid_file():
    return paths.data_dir() / "agent.pid"


def _write_pid() -> None:
    try:
        _pid_file().write_text(str(os.getpid()), encoding="utf-8")
    except Exception as e:
        # Advisory only — the mutex owns single-instance. Without the pid file
        # the supervisor may attempt extra spawns; they exit at the mutex.
        _log.warning("could not write agent.pid (%s); continuing.", e)


def _watch_parent(parent_pid: int) -> None:
    """Exit when the launching process dies (Electron dev agent only).

    Windows does not kill children with their parent, so a force-killed
    Electron would otherwise leave this agent orphaned and scanning.
    """
    try:
        import psutil
    except ImportError:
        return

    def poll() -> None:
        while True:
            if not psutil.pid_exists(parent_pid):
                _log.info("Parent process %s is gone; agent exiting.", parent_pid)
                os._exit(0)
            time.sleep(2.0)

    threading.Thread(target=poll, daemon=True, name="ParentWatch").start()


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

    parser = argparse.ArgumentParser(prog="brake.agent")
    parser.add_argument("--parent-pid", type=int, default=0)
    args, _unknown = parser.parse_known_args()

    lock = SingleInstanceLock(AGENT_MUTEX_NAME)
    if not lock.acquire():
        _log.info("Another agent already holds the session mutex; exiting.")
        return 0

    _write_pid()
    _log.info(
        "Agent starting (pid=%s, data_dir=%s).", os.getpid(), paths.data_dir()
    )
    log_banner_once()
    if args.parent_pid > 0:
        _watch_parent(args.parent_pid)
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
        lock.release()
        _log.info("Agent stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
