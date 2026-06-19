"""Uninstall policy tests."""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _fresh(tmp: Path):
    os.environ["BRAKE_DATA_DIR"] = str(tmp)
    for mod in [k for k in list(sys.modules) if k == "brake" or k.startswith("brake.")]:
        del sys.modules[mod]
    from brake import uninstall_guard
    from brake.state import State, StateStore, crypto
    return uninstall_guard, State, StateStore, crypto


def test_no_state_allows_uninstall(tmp: Path) -> None:
    uninstall_guard, *_ = _fresh(tmp)
    assert uninstall_guard.main() == 0
    print("  [ok] no state allows uninstall")


def test_disabled_without_commitment_allows_uninstall(tmp: Path) -> None:
    uninstall_guard, State, StateStore, crypto = _fresh(tmp)
    state = State(password_hash=crypto.hash_password("pw"), enabled=False)
    StateStore().save(state)
    assert uninstall_guard.main() == 0
    print("  [ok] disabled protection without commitment allows uninstall")


def test_enabled_without_commitment_blocks_uninstall(tmp: Path) -> None:
    uninstall_guard, State, StateStore, crypto = _fresh(tmp)
    state = State(password_hash=crypto.hash_password("pw"), enabled=True)
    StateStore().save(state)

    uninstall_guard._block_with_dialog = lambda _message: None

    assert uninstall_guard.main() == 1
    print("  [ok] enabled protection blocks uninstall")


def test_enabled_without_commitment_does_not_accept_recovery_code(tmp: Path) -> None:
    uninstall_guard, State, StateStore, crypto = _fresh(tmp)
    state = State(password_hash=crypto.hash_password("pw"), enabled=True)
    StateStore().save(state)

    uninstall_guard._block_with_dialog = lambda _message: None

    assert uninstall_guard.main() == 1
    saved = StateStore().load()
    assert saved is not None
    assert saved.enabled is True
    assert saved.recovery_unlock_after is None
    print("  [ok] enabled protection does not accept recovery inside uninstall")


def test_active_commitment_rejects_normal_password(tmp: Path) -> None:
    uninstall_guard, State, StateStore, crypto = _fresh(tmp)
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(timespec="seconds")
    state = State(password_hash=crypto.hash_password("pw"), enabled=True, committed_until=future)
    StateStore().save(state)

    uninstall_guard._block_with_dialog = lambda _message: None

    assert uninstall_guard.main() == 1
    print("  [ok] active commitment rejects normal password")


def test_active_commitment_does_not_accept_recovery_code(tmp: Path) -> None:
    uninstall_guard, State, StateStore, crypto = _fresh(tmp)
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(timespec="seconds")
    state = State(password_hash=crypto.hash_password("pw"), enabled=True, committed_until=future)
    StateStore().save(state)

    uninstall_guard._block_with_dialog = lambda _message: None

    assert uninstall_guard.main() == 1
    saved = StateStore().load()
    assert saved is not None
    assert saved.enabled is True
    assert saved.commitment_active()
    assert saved.recovery_unlock_after is None
    print("  [ok] active commitment does not accept recovery inside uninstall")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="brake-uninstall-") as td:
        tmp = Path(td)
        print(f"Using temp dir: {tmp}")
        for fn in (
            test_no_state_allows_uninstall,
            test_disabled_without_commitment_allows_uninstall,
            test_enabled_without_commitment_blocks_uninstall,
            test_enabled_without_commitment_does_not_accept_recovery_code,
            test_active_commitment_rejects_normal_password,
            test_active_commitment_does_not_accept_recovery_code,
        ):
            sub = tmp / fn.__name__
            sub.mkdir()
            print(f"\n{fn.__name__}")
            fn(sub)
    print("\nAll tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
