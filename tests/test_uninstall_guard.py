"""Uninstall policy tests."""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _fresh(tmp: Path):
    os.environ["LOCKITUP_DATA_DIR"] = str(tmp)
    for mod in [k for k in list(sys.modules) if k == "lockitup" or k.startswith("lockitup.")]:
        del sys.modules[mod]
    from lockitup import uninstall_guard
    from lockitup.state import State, StateStore, crypto
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


def test_enabled_without_commitment_rejects_wrong_password(tmp: Path) -> None:
    uninstall_guard, State, StateStore, crypto = _fresh(tmp)
    state = State(password_hash=crypto.hash_password("pw"), enabled=True)
    StateStore().save(state)

    uninstall_guard._prompt_dialog = lambda _prompt: "wrong"
    uninstall_guard._block_with_dialog = lambda _message: None
    uninstall_guard.is_backdoor = lambda _typed: False

    assert uninstall_guard.main() == 1
    print("  [ok] enabled protection rejects wrong password")


def test_enabled_without_commitment_accepts_password(tmp: Path) -> None:
    uninstall_guard, State, StateStore, crypto = _fresh(tmp)
    state = State(password_hash=crypto.hash_password("pw"), enabled=True)
    StateStore().save(state)

    uninstall_guard._prompt_dialog = lambda _prompt: "pw"
    uninstall_guard.is_backdoor = lambda _typed: False

    assert uninstall_guard.main() == 0
    print("  [ok] enabled protection accepts password")


def test_enabled_without_commitment_recovery_schedules_cooldown(tmp: Path) -> None:
    uninstall_guard, State, StateStore, crypto = _fresh(tmp)
    state = State(password_hash=crypto.hash_password("pw"), enabled=True)
    StateStore().save(state)

    uninstall_guard._prompt_dialog = lambda _prompt: "recovery-code"
    uninstall_guard._block_with_dialog = lambda _message: None
    uninstall_guard.is_backdoor = lambda _typed: False
    from lockitup.state.recovery import RecoveryStore
    RecoveryStore.verify = lambda _self, typed: typed == "recovery-code"  # type: ignore[method-assign]

    assert uninstall_guard.main() == 1
    saved = StateStore().load()
    assert saved is not None
    assert saved.enabled is True
    assert saved.recovery_unlock_after is not None
    print("  [ok] enabled protection recovery schedules cooldown before uninstall")


def test_active_commitment_rejects_normal_password(tmp: Path) -> None:
    uninstall_guard, State, StateStore, crypto = _fresh(tmp)
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(timespec="seconds")
    state = State(password_hash=crypto.hash_password("pw"), enabled=True, committed_until=future)
    StateStore().save(state)

    uninstall_guard._prompt_dialog = lambda _prompt: "pw"
    uninstall_guard._block_with_dialog = lambda _message: None
    uninstall_guard.is_backdoor = lambda _typed: False

    assert uninstall_guard.main() == 1
    print("  [ok] active commitment rejects normal password")


def test_active_commitment_recovery_schedules_cooldown(tmp: Path) -> None:
    uninstall_guard, State, StateStore, crypto = _fresh(tmp)
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(timespec="seconds")
    state = State(password_hash=crypto.hash_password("pw"), enabled=True, committed_until=future)
    StateStore().save(state)

    uninstall_guard._prompt_dialog = lambda _prompt: "recovery-code"
    uninstall_guard._block_with_dialog = lambda _message: None
    uninstall_guard.is_backdoor = lambda _typed: False
    from lockitup.state.recovery import RecoveryStore
    RecoveryStore.verify = lambda _self, typed: typed == "recovery-code"  # type: ignore[method-assign]

    assert uninstall_guard.main() == 1
    saved = StateStore().load()
    assert saved is not None
    assert saved.enabled is True
    assert saved.commitment_active()
    assert saved.recovery_unlock_after is not None
    print("  [ok] active commitment recovery schedules cooldown before uninstall")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="lockitup-uninstall-") as td:
        tmp = Path(td)
        print(f"Using temp dir: {tmp}")
        for fn in (
            test_no_state_allows_uninstall,
            test_disabled_without_commitment_allows_uninstall,
            test_enabled_without_commitment_rejects_wrong_password,
            test_enabled_without_commitment_accepts_password,
            test_enabled_without_commitment_recovery_schedules_cooldown,
            test_active_commitment_rejects_normal_password,
            test_active_commitment_recovery_schedules_cooldown,
        ):
            sub = tmp / fn.__name__
            sub.mkdir()
            print(f"\n{fn.__name__}")
            fn(sub)
    print("\nAll tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
