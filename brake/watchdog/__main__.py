"""Entry: `python -m brake.watchdog {install|start|stop|remove}`."""
from __future__ import annotations

import sys

from brake.watchdog.watchdog_service import brakeWatchdog


def main() -> int:
    if BrakeWatchdog is None:
        print("pywin32 is required for service mode.", file=sys.stderr)
        return 2

    import servicemanager           # type: ignore[import-not-found]
    import win32serviceutil         # type: ignore[import-not-found]

    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(BrakeWatchdog)
        servicemanager.StartServiceCtrlDispatcher()
        return 0

    win32serviceutil.HandleCommandLine(BrakeWatchdog)
    return 0


if __name__ == "__main__":
    sys.exit(main())
