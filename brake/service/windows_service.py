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


def _agent_supervisor(stop: threading.Event) -> None:
    """Ensure an agent is running in the active user session.

    Throttle: at most one spawn attempt per 3s, even if the spawn appears
    to have failed (so we don't tight-loop CreateProcessAsUser during the
    login screen, but a killed agent comes back within a couple seconds).
    """
    from brake.service.session_launcher import spawn_in_user_session
    last_attempt = 0.0
    last_autostart_check = 0.0
    while not stop.is_set():
        try:
            # Re-assert services are auto-start ~every 60s. Cheap, and
            # closes the `sc config disabled` bypass within a minute.
            if time.time() - last_autostart_check >= 60:
                last_autostart_check = time.time()
                _assert_services_auto_start()
            if not _agent_running():
                if time.time() - last_attempt >= 3:
                    last_attempt = time.time()
                    root = app_dir()
                    ok, pid = spawn_in_user_session(
                        agent_command(),
                        cwd=str(root),
                        extra_env=module_env(),
                    )
                    if ok:
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
