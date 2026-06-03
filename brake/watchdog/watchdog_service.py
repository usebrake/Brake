"""BrakeWatchdog — restarts BrakeService if the SCM reports it stopped.

`sc failure` is also configured by the installer for mutual revival.
"""
from __future__ import annotations

import logging
import threading
import time

from brake import paths

_log = logging.getLogger(__name__)

WATCHDOG_NAME = "BrakeWatchdog"
TARGET_NAME = "BrakeService"


try:
    import servicemanager           # type: ignore[import-not-found]
    import win32event               # type: ignore[import-not-found]
    import win32service             # type: ignore[import-not-found]
    import win32serviceutil         # type: ignore[import-not-found]
    _PYWIN32_OK = True
except ImportError:
    _PYWIN32_OK = False


def _configure_file_logging() -> None:
    handler = logging.FileHandler(paths.logs_dir() / "watchdog.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for h in list(root.handlers):
        if isinstance(h, logging.FileHandler):
            root.removeHandler(h)
    root.addHandler(handler)


def _restart_target_if_stopped(stop: threading.Event) -> None:
    while not stop.is_set():
        try:
            status = win32serviceutil.QueryServiceStatus(TARGET_NAME)[1]
            if status == win32service.SERVICE_STOPPED:
                _log.warning("%s is STOPPED — restarting", TARGET_NAME)
                try:
                    win32serviceutil.StartService(TARGET_NAME)
                except Exception as e:
                    _log.error("Failed to start %s: %s", TARGET_NAME, e)
        except Exception as e:
            _log.error("watchdog query error: %s", e)
        # Poll fast so killing the service leaves only a ~1s window before
        # the watchdog respawns it. Cheap call — just SCM status query.
        stop.wait(1)


if _PYWIN32_OK:
    class BrakeWatchdog(win32serviceutil.ServiceFramework):
        _svc_name_ = WATCHDOG_NAME
        _svc_display_name_ = "Brake Watchdog"
        _svc_description_ = "Restarts the Brake service if it stops."

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
            servicemanager.LogInfoMsg(f"{WATCHDOG_NAME} starting.")
            t = threading.Thread(target=_restart_target_if_stopped, args=(self._stop,),
                                 daemon=True, name="WatchdogLoop")
            t.start()
            win32event.WaitForSingleObject(self._wait, win32event.INFINITE)
            servicemanager.LogInfoMsg(f"{WATCHDOG_NAME} exited.")
else:
    BrakeWatchdog = None  # type: ignore[assignment]
