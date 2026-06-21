"""Tests for recovery-code emergency release during an active lockout."""
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

    from brake.lockout.emergency import apply_lockout_recovery, lockout_recovery_available
    from brake.lockout.persistence import LockoutPersistence
    from brake.state import State, StateStore
    from brake.state.crypto import hash_password
    from brake.state.recovery import RecoveryStore

    store = StateStore(state_path=tmp / "state.json", key_path=tmp / "state.key")
    recovery_store = RecoveryStore(file_path=tmp / "recovery.json")
    persistence = LockoutPersistence(file_path=tmp / "lockout.json")
    return apply_lockout_recovery, lockout_recovery_available, persistence, recovery_store, State, store, hash_password


def test_lockout_recovery_available_by_default(tmp: Path) -> None:
    _, available, _, _, State, store, hash_password = _fresh(tmp)
    store.save(State(password_hash=hash_password("password"), enabled=True))
    assert available(store) is True
    print("  [ok] lockout recovery is available by default")


def test_wrong_recovery_code_does_not_change_lockout(tmp: Path) -> None:
    apply_recovery, _, persistence, recovery_store, State, store, hash_password = _fresh(tmp)
    store.save(State(
        password_hash=hash_password("password"),
        enabled=True,
        lockout_recovery_enabled=True,
        lockout_recovery_delay_minutes=7,
    ))
    recovery_store.generate()
    original = persistence.start(30 * 60, "TEST", message="Original", shutdown_on_done=True)

    ok, error, new_end_at = apply_recovery(
        "wrong",
        store=store,
        recovery_store=recovery_store,
        persistence=persistence,
    )
    assert ok is False
    assert error == "wrong_recovery_code"
    assert new_end_at is None
    after = persistence.resume()
    assert after is not None
    assert after.end_at == original.end_at
    assert after.shutdown_on_done is True
    print("  [ok] wrong recovery code leaves active lockout unchanged")


def test_recovery_code_replaces_lockout_timer_and_skips_shutdown(tmp: Path) -> None:
    apply_recovery, _, persistence, recovery_store, State, store, hash_password = _fresh(tmp)
    future = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(timespec="seconds")
    store.save(State(
        password_hash=hash_password("password"),
        enabled=True,
        committed_until=future,
        lockout_recovery_enabled=True,
        lockout_recovery_delay_minutes=7,
    ))
    token = recovery_store.generate()
    persistence.start(30 * 60, "TEST", message="Original", shutdown_on_done=True)

    ok, message, new_end_at = apply_recovery(
        token,
        store=store,
        recovery_store=recovery_store,
        persistence=persistence,
    )
    assert ok is True
    assert "Emergency release pending" in message
    assert new_end_at is not None
    after = persistence.resume()
    assert after is not None
    assert after.duration_seconds == 7 * 60
    assert after.shutdown_on_done is False
    remaining = after.end_dt() - datetime.now(timezone.utc)
    assert 390 <= remaining.total_seconds() <= 430

    saved = store.load()
    assert saved is not None
    assert saved.enabled is True
    assert saved.commitment_active()
    print("  [ok] valid recovery code starts lockout release without disabling protection")


def main() -> int:
    tests = [
        test_lockout_recovery_available_by_default,
        test_wrong_recovery_code_does_not_change_lockout,
        test_recovery_code_replaces_lockout_timer_and_skips_shutdown,
    ]
    for fn in tests:
        print(f"\n{fn.__name__}")
        with tempfile.TemporaryDirectory(prefix="brake-lockout-emergency-") as d:
            fn(Path(d))
    print("\nAll tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
