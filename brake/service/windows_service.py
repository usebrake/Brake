"""BrakeService — Windows Service hosting IPC + user-session agent supervision.

Install:   python -m brake.service install
Start:     sc start BrakeService     (or: python -m brake.service start)
Stop:      sc stop BrakeService
Remove:    python -m brake.service remove
Debug:     python -m brake.service debug   (runs in foreground, no install needed)

This service runs as LocalSystem. It does NOT capture the screen itself —
session 0 isolation prevents that. Instead it spawns the user-session agent
(via CreateProcessAsUser) which owns the watcher + lockout + hardening.
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from brake import paths
from brake.runtime import agent_command, app_dir, module_env
from brake.state import StateStore

_log = logging.getLogger(__name__)

SERVICE_NAME = "BrakeService"
SERVICE_DISPLAY = "Brake"
SERVICE_DESCRIPTION = "Brake state authority and user-session agent supervisor."


# One spawn attempt at most per this many seconds.
SPAWN_BACKOFF_SECONDS = 5.0
# How long a freshly spawned agent may run without writing agent.pid before
# we log a diagnostic (slow cold-start imports are normal; minutes are not).
SPAWN_STARTUP_GRACE_SECONDS = 60.0


def _agent_pid_file() -> Path:
    return paths.data_dir() / "agent.pid"


def _agent_running() -> bool:
    f = _agent_pid_file()
    if not f.exists():
        return False
    try:
        pid = int(f.read_text().strip())
    except Exception:
        return False
    try:
        import psutil
        return psutil.pid_exists(pid)
    except Exception:
        return False


def _process_signature(pid: int):
    """(pid, create_time) identity tuple, or None when the pid is gone.

    The create time guards against pid reuse: a recycled pid belongs to a
    different process and must not count as our agent.
    """
    try:
        import psutil

        return (pid, psutil.Process(pid).create_time())
    except Exception:
        return None


def _spawned_agent_alive(signature) -> bool:
    if signature is None:
        return False
    current = _process_signature(signature[0])
    return current is not None and abs(current[1] - signature[1]) < 1.0


try:
    import servicemanager           # type: ignore[import-not-found]
    import win32event               # type: ignore[import-not-found]
    import win32service             # type: ignore[import-not-found]
    import win32serviceutil         # type: ignore[import-not-found]
    _PYWIN32_OK = True
except ImportError:
    _PYWIN32_OK = False


if _PYWIN32_OK:
    class BrakeService(win32serviceutil.ServiceFramework):
        _svc_name_ = SERVICE_NAME
        _svc_display_name_ = SERVICE_DISPLAY
        _svc_description_ = SERVICE_DESCRIPTION

        def __init__(self, args):
            super().__init__(args)
            self._wait = win32event.CreateEvent(None, 0, 0, None)
            self._stop = threading.Event()

        def SvcStop(self):
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            self._stop.set()
            win32event.SetEvent(self._wait)

        def SvcDoRun(self):
            _configure_file_logging()
            servicemanager.LogInfoMsg(f"{SERVICE_NAME} starting.")
            try:
                run_service(self._stop, self._wait)
            finally:
                servicemanager.LogInfoMsg(f"{SERVICE_NAME} exited.")
else:
    BrakeService = None  # type: ignore[assignment]


def _configure_file_logging() -> None:
    handler = logging.FileHandler(paths.logs_dir() / "service.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    # avoid duplicate handlers on debug re-run
    for h in list(root.handlers):
        if isinstance(h, logging.FileHandler):
            root.removeHandler(h)
    root.addHandler(handler)


def _assert_services_auto_start() -> None:
    """Re-assert that both Brake services have start type 'auto'.

    An admin can run `sc config BrakeService start= disabled` to keep
    the service from coming back after the next reboot. We periodically
    check and revert any such change while the service is running.
    """
    import subprocess
    for svc in ("BrakeService", "BrakeWatchdog"):
        try:
            # Re-asserts unconditionally — `sc config start= auto` is a no-op
            # if it's already auto, and a fix if someone flipped it.
            subprocess.run(
                ["sc.exe", "config", svc, "start=", "auto"],
                check=False, capture_output=True, timeout=5,
            )
        except Exception as e:
            _log.warning("failed to re-assert auto-start for %s: %s", svc, e)


def _agent_env() -> dict:
    """Environment for the spawned agent.

    BRAKE_DATA_DIR is pinned to the service's own data dir so the agent can
    never disagree with the service about where state and agent.pid live.
    A mismatch here used to cause endless respawns and agents scanning
    against an empty (unprotected) state directory.
    """
    env = dict(module_env() or {})
    env["BRAKE_DATA_DIR"] = str(paths.data_dir())
    return env


def _agent_supervisor(stop: threading.Event) -> None:
    """Ensure exactly one agent is running in the active user session.

    The agent enforces single-instance with a session mutex; this loop only
    avoids useless spawn churn. It never respawns while the process it
    spawned is still alive (cold-start imports can take many seconds before
    agent.pid appears), and it backs off between attempts.
    """
    from brake.service.session_launcher import spawn_in_user_session
    last_attempt = 0.0
    last_autostart_check = 0.0
    spawned_signature = None
    spawned_at = 0.0
    slow_start_logged = False
    while not stop.is_set():
        try:
            # Re-assert services are auto-start ~every 60s. Cheap, and
            # closes the `sc config disabled` bypass within a minute.
            if time.time() - last_autostart_check >= 60:
                last_autostart_check = time.time()
                _assert_services_auto_start()

            if _agent_running():
                slow_start_logged = False
            elif _spawned_agent_alive(spawned_signature):
                # Our spawn is alive but has not written agent.pid yet
                # (still importing) or cannot write it. Either way another
                # spawn would just exit at the agent mutex — don't churn.
                if (
                    not slow_start_logged
                    and time.time() - spawned_at >= SPAWN_STARTUP_GRACE_SECONDS
                ):
                    slow_start_logged = True
                    _log.warning(
                        "Agent pid=%s alive for %.0fs without agent.pid — "
                        "check data-dir permissions (%s).",
                        spawned_signature[0],
                        time.time() - spawned_at,
                        _agent_pid_file(),
                    )
            elif time.time() - last_attempt >= SPAWN_BACKOFF_SECONDS:
                last_attempt = time.time()
                root = app_dir()
                ok, pid = spawn_in_user_session(
                    agent_command(),
                    cwd=str(root),
                    extra_env=_agent_env(),
                )
                if ok:
                    spawned_signature = _process_signature(pid)
                    spawned_at = time.time()
                    slow_start_logged = False
                    _log.info("Agent spawned (pid=%s).", pid)
                else:
                    _log.debug("Agent spawn skipped or failed; will retry.")
        except Exception as e:
            _log.exception("agent supervisor error: %s", e)
        stop.wait(1)


def run_service(stop: threading.Event, wait_handle=None) -> None:
    """Run the service body. Usable directly for `debug` mode."""
    from brake.service.ipc_server import IPCServer

    store = StateStore()

    ipc = IPCServer(store, stop)
    ipc.start()

    sup = threading.Thread(target=_agent_supervisor, args=(stop,), daemon=True, name="AgentSupervisor")
    sup.start()

    if wait_handle is not None:
        import win32event
        win32event.WaitForSingleObject(wait_handle, win32event.INFINITE)
    else:
        # debug / foreground
        try:
            while not stop.is_set():
                time.sleep(1)
        except KeyboardInterrupt:
            stop.set()
