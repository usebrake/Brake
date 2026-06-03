"""Foreground dev runner: `python -m brake`.

Watches state.enabled; when ENABLED, scans the screen every interval and
spawns the lockout subprocess on detection. Designed for terminal dev work
before the Windows Service wrapper exists (milestone 6).

Toggle protection from the GUI (`python -m brake.gui`) — both share the
same state.json on disk.
"""
from __future__ import annotations

import logging
import sys

from brake.service.watcher import Watcher


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    try:
        Watcher().run_forever()
    except KeyboardInterrupt:
        print("\nWatcher stopped by user.")
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
