"""Phase 1: Unit tests for the BRAKE_TEST_MODE switch.

Verifies:
  - is_test_mode() correctly parses common truthy/falsy values
  - t(real, test) returns the right value for each mode
  - should_actually_shutdown() flips correctly
  - reading the env after import still works (no module-level caching trap)
  - constants in watcher/escalation reflect the mode at import time
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _reset_env(value: str | None) -> None:
    if value is None:
        os.environ.pop("BRAKE_TEST_MODE", None)
    else:
        os.environ["BRAKE_TEST_MODE"] = value
    # Force re-import of anything that reads the env at import time.
    for mod in [k for k in list(sys.modules) if k == "brake" or k.startswith("brake.")]:
        del sys.modules[mod]


def test_truthy_values() -> None:
    for v in ("1", "true", "TRUE", "yes", "on", "True"):
        _reset_env(v)
        from brake.test_mode import is_test_mode
        assert is_test_mode(), f"{v!r} should be truthy"
    print("  [ok] truthy values recognized")


def test_falsy_values() -> None:
    for v in (None, "", "0", "false", "no", "off", "anything-else"):
        _reset_env(v)
        from brake.test_mode import is_test_mode
        assert not is_test_mode(), f"{v!r} should be falsy"
    print("  [ok] falsy values rejected (default = production)")


def test_t_helper_returns_real_in_prod() -> None:
    _reset_env(None)
    from brake.test_mode import t
    assert t(600, 5) == 600
    assert t(1, 999) == 1
    print("  [ok] t(real, test) returns real in production")


def test_t_helper_returns_test_in_test_mode() -> None:
    _reset_env("1")
    from brake.test_mode import t
    assert t(600, 5) == 5
    assert t(1, 999) == 999
    print("  [ok] t(real, test) returns test value when enabled")


def test_shutdown_flag() -> None:
    _reset_env(None)
    from brake.test_mode import should_actually_shutdown
    assert should_actually_shutdown() is True
    _reset_env("1")
    # Re-import to pick up new env
    from brake.test_mode import should_actually_shutdown as f2
    assert f2() is False
    print("  [ok] should_actually_shutdown() flips with the env")


def test_watcher_constants_compress_under_test_mode() -> None:
    _reset_env("1")
    from brake.service import watcher as w_test
    assert w_test.PENALTY_MIN_SECONDS == 20

    _reset_env(None)
    from brake.service import watcher as w_prod
    assert w_prod.PENALTY_MIN_SECONDS == 10 * 60
    print("  [ok] watcher constants reflect mode at import time")


def test_probation_constant_compresses_under_test_mode() -> None:
    _reset_env("1")
    from brake import escalation as e_test
    assert e_test.PROBATION_SECONDS == 30

    _reset_env(None)
    from brake import escalation as e_prod
    assert e_prod.PROBATION_SECONDS == 5 * 60
    print("  [ok] PROBATION_SECONDS reflects mode at import time")


def main() -> int:
    tests = [
        test_truthy_values,
        test_falsy_values,
        test_t_helper_returns_real_in_prod,
        test_t_helper_returns_test_in_test_mode,
        test_shutdown_flag,
        test_watcher_constants_compress_under_test_mode,
        test_probation_constant_compresses_under_test_mode,
    ]
    saved = os.environ.get("BRAKE_TEST_MODE")
    try:
        for fn in tests:
            print(f"\n{fn.__name__}")
            fn()
    finally:
        _reset_env(saved)
    print("\nAll tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
