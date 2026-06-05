"""Smoke tests for Windows service entrypoint imports."""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def test_service_entrypoints_import_expected_classes() -> None:
    import brake.service.__main__ as service_main
    import brake.watchdog.__main__ as watchdog_main

    assert hasattr(service_main, "BrakeService")
    assert hasattr(watchdog_main, "BrakeWatchdog")
    print("  [ok] service entrypoints import expected classes")


if __name__ == "__main__":
    test_service_entrypoints_import_expected_classes()
