"""Entry: `python -m lockitup.service {install|start|stop|remove|debug}`."""
from __future__ import annotations

import sys
import threading

from lockitup.service.windows_service import (
    LockItUpService,
    _configure_file_logging,
    run_service,
)


def _debug() -> int:
    """Foreground run with no service registration. For dev only."""
    _configure_file_logging()
    print("LockItUpService: running in foreground (debug). Ctrl-C to stop.")
    stop = threading.Event()
    try:
        run_service(stop, wait_handle=None)
    except KeyboardInterrupt:
        stop.set()
    return 0


def main() -> int:
    if LockItUpService is None:
        print("pywin32 is required for service mode. Install with: pip install pywin32", file=sys.stderr)
        return 2

    if len(sys.argv) >= 2 and sys.argv[1].lower() == "debug":
        return _debug()

    import servicemanager           # type: ignore[import-not-found]
    import win32serviceutil         # type: ignore[import-not-found]

    if len(sys.argv) == 1:
        # invoked by the SCM
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(LockItUpService)
        servicemanager.StartServiceCtrlDispatcher()
        return 0

    # cli: install/start/stop/remove/update
    win32serviceutil.HandleCommandLine(LockItUpService)
    return 0


if __name__ == "__main__":
    sys.exit(main())
