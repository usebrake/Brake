"""Tests for lockout completion consequences."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class _PersistClearFails:
    def __init__(self) -> None:
        self.cleared = False

    def resume(self):
        return None

    def clear(self) -> None:
        self.cleared = True
        raise PermissionError("locked")


def test_shutdown_attempted_even_if_lockout_clear_fails() -> None:
    import brake.lockout.__main__ as lockout_main

    calls: list[str] = []
    original_shutdown = lockout_main._shutdown_windows
    try:
        lockout_main._shutdown_windows = lambda: calls.append("shutdown")
        persist = _PersistClearFails()
        lockout_main._on_done(persist, True)()
    finally:
        lockout_main._shutdown_windows = original_shutdown

    assert persist.cleared is True
    assert calls == ["shutdown"]
    print("  [ok] shutdown still runs if lockout cleanup fails")


def test_lockout_recovery_ui_does_not_depend_on_shutdown() -> None:
    import brake.lockout.__main__ as lockout_main

    original_available = lockout_main.lockout_recovery_available
    try:
        lockout_main.lockout_recovery_available = lambda: True
        assert lockout_main._lockout_recovery_enabled_for_ui() is True
    finally:
        lockout_main.lockout_recovery_available = original_available

    print("  [ok] lockout recovery UI is independent of shutdown setting")


def test_explicit_data_dir_overrides_conflicting_environment() -> None:
    import os

    import brake.lockout.__main__ as lockout_main

    previous = os.environ.get("BRAKE_DATA_DIR")
    root = Path(tempfile.mkdtemp(prefix="brake-lockout-data-dir-"))
    wrong = root / "wrong"
    canonical = root / "canonical"
    try:
        os.environ["BRAKE_DATA_DIR"] = str(wrong)
        lockout_main._pin_data_dir(str(canonical))
        assert lockout_main.paths.data_dir() == canonical.resolve()
    finally:
        if previous is None:
            os.environ.pop("BRAKE_DATA_DIR", None)
        else:
            os.environ["BRAKE_DATA_DIR"] = previous

    print("  [ok] explicit lockout data directory wins over inherited environment")


def main() -> int:
    tests = [
        test_shutdown_attempted_even_if_lockout_clear_fails,
        test_lockout_recovery_ui_does_not_depend_on_shutdown,
        test_explicit_data_dir_overrides_conflicting_environment,
    ]
    for fn in tests:
        print(f"\n{fn.__name__}")
        fn()
    print("\nAll tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
