"""Round-trip + tamper + migration tests for the state store."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _fresh_store(tmp: Path):
    os.environ["BRAKE_DATA_DIR"] = str(tmp)
    for mod in [k for k in list(sys.modules) if k == "brake" or k.startswith("brake.")]:
        del sys.modules[mod]
    from brake.state import State, StateStore, StateTamperedError
    from brake.state import crypto
    return StateStore(state_path=tmp / "state.json", key_path=tmp / "state.key"), State, StateTamperedError, crypto


def _write_envelope(tmp: Path, payload: dict, crypto_mod) -> None:
    from brake.state.store import _canonical

    key = crypto_mod.load_or_create_hmac_key(tmp / "state.key")
    envelope = {"payload": payload, "hmac": crypto_mod.sign(_canonical(payload), key)}
    (tmp / "state.json").write_text(json.dumps(envelope), encoding="utf-8")


def test_roundtrip_and_password_verify(tmp: Path) -> None:
    store, State, _, crypto_mod = _fresh_store(tmp)
    pw = "correct horse battery staple"
    state = State(
        password_hash=crypto_mod.hash_password(pw),
        enabled=True,
        lockout_duration_minutes=5,
        detection_sensitivity="strict",
    )
    store.save(state)

    loaded = store.load()
    assert loaded is not None
    assert loaded.enabled is True
    assert loaded.lockout_duration_minutes == 5
    assert loaded.lockout_duration_seconds() == 300
    assert loaded.committed_until is None
    assert loaded.detection_sensitivity == "balanced"
    assert loaded.anime_detection_enabled is False
    assert loaded.anime_detection_mode == "standard"
    assert loaded.shutdown_after_lockout is True
    assert loaded.recovery_unlock_after is None
    assert loaded.recovery_unlock_delay_minutes == 15
    assert loaded.lockout_recovery_enabled is False
    assert loaded.lockout_recovery_delay_minutes == 15
    assert crypto_mod.verify_password(loaded.password_hash, pw)
    assert not crypto_mod.verify_password(loaded.password_hash, "wrong")
    print("  [ok] roundtrip + password verify (v11 schema)")


def test_invalid_sensitivity_coerces_to_balanced(tmp: Path) -> None:
    _, State, _, crypto_mod = _fresh_store(tmp)
    state = State(password_hash=crypto_mod.hash_password("x"), detection_sensitivity="whatever")
    assert state.detection_sensitivity == "balanced"
    print("  [ok] invalid sensitivity coerces to balanced")


def test_duration_clamping(tmp: Path) -> None:
    _, State, _, crypto_mod = _fresh_store(tmp)
    too_high = State(password_hash=crypto_mod.hash_password("x"), lockout_duration_minutes=999)
    too_low = State(password_hash=crypto_mod.hash_password("x"), lockout_duration_minutes=0)
    assert too_high.lockout_duration_minutes == 60
    assert too_low.lockout_duration_minutes == 1
    print("  [ok] lockout_duration_minutes clamped to [1, 60]")


def test_recovery_cooldown_clamping(tmp: Path) -> None:
    _, State, _, crypto_mod = _fresh_store(tmp)
    state = State(
        password_hash=crypto_mod.hash_password("x"),
        recovery_unlock_delay_minutes=999,
        lockout_recovery_delay_minutes=0,
        lockout_recovery_enabled=1,
    )
    assert state.recovery_unlock_delay_minutes == 60
    assert state.lockout_recovery_delay_minutes == 1
    assert state.lockout_recovery_enabled is True
    assert state.recovery_unlock_delay_seconds() == 60 * 60
    assert state.lockout_recovery_delay_seconds() == 60
    print("  [ok] recovery cooldown settings clamp to [1, 60]")


def test_commitment_active(tmp: Path) -> None:
    from datetime import datetime, timedelta, timezone

    _, State, _, crypto_mod = _fresh_store(tmp)
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(timespec="seconds")
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(timespec="seconds")
    active = State(password_hash=crypto_mod.hash_password("x"), committed_until=future)
    expired = State(password_hash=crypto_mod.hash_password("x"), committed_until=past)
    assert active.commitment_active()
    assert not expired.commitment_active()
    print("  [ok] committed_until reports active only while in the future")


def test_tamper_detection(tmp: Path) -> None:
    store, State, StateTamperedError, crypto_mod = _fresh_store(tmp)
    state = State(password_hash=crypto_mod.hash_password("pw"), enabled=True)
    store.save(state)
    raw = json.loads((tmp / "state.json").read_text(encoding="utf-8"))
    raw["payload"]["enabled"] = False
    (tmp / "state.json").write_text(json.dumps(raw, indent=2), encoding="utf-8")
    try:
        store.load()
    except StateTamperedError:
        print("  [ok] tampered enabled flag rejected")
        return
    raise AssertionError("Tampered state was accepted!")


def test_missing_state_returns_none(tmp: Path) -> None:
    store, *_ = _fresh_store(tmp)
    assert store.load() is None
    print("  [ok] missing state returns None")


def test_deletion_bypass_refused(tmp: Path) -> None:
    store, State, _, crypto_mod = _fresh_store(tmp)
    from brake.state import StateMissingError

    state = State(password_hash=crypto_mod.hash_password("pw"), enabled=True)
    store.save(state)
    assert (tmp / "state.initialized").exists()
    (tmp / "state.json").unlink()
    try:
        store.load()
    except StateMissingError:
        print("  [ok] deletion-bypass refused (initialized marker still present)")
        return
    raise AssertionError("Deletion bypass was not detected!")


def test_v1_to_v9_migration(tmp: Path) -> None:
    store, _, _, crypto_mod = _fresh_store(tmp)
    v1_payload = {
        "password_hash": crypto_mod.hash_password("pw"),
        "enabled": True,
        "locked_until": "2099-01-01T00:00:00+00:00",
        "created_at": "2026-05-01T00:00:00+00:00",
        "schema_version": 1,
    }
    _write_envelope(tmp, v1_payload, crypto_mod)

    loaded = store.load()
    assert loaded is not None
    assert loaded.schema_version == 11
    assert loaded.enabled is True
    assert loaded.lockout_duration_minutes == 15
    assert loaded.committed_until is None
    assert loaded.detection_sensitivity == "balanced"
    assert loaded.anime_detection_enabled is False
    assert loaded.anime_detection_mode == "standard"
    assert loaded.recovery_unlock_after is None
    assert loaded.recovery_unlock_delay_minutes == 15
    assert loaded.lockout_recovery_enabled is False
    assert loaded.lockout_recovery_delay_minutes == 15
    assert not hasattr(loaded, "locked_until")
    assert not hasattr(loaded, "ocr_enabled")

    raw = json.loads((tmp / "state.json").read_text(encoding="utf-8"))
    assert raw["payload"]["schema_version"] == 11
    assert "locked_until" not in raw["payload"]
    assert "ocr_enabled" not in raw["payload"]
    print("  [ok] v1 -> v9 migration drops old fields and seeds balanced")


def test_v2_to_v9_migration_seeds_balanced(tmp: Path) -> None:
    store, _, _, crypto_mod = _fresh_store(tmp)
    payload = {
        "password_hash": crypto_mod.hash_password("pw"),
        "enabled": True,
        "lockout_duration_minutes": 9,
        "created_at": "2026-05-01T00:00:00+00:00",
        "schema_version": 2,
    }
    _write_envelope(tmp, payload, crypto_mod)

    loaded = store.load()
    assert loaded is not None
    assert loaded.schema_version == 11
    assert loaded.lockout_duration_minutes == 9
    assert loaded.detection_sensitivity == "balanced"
    assert loaded.anime_detection_enabled is False
    assert loaded.anime_detection_mode == "standard"
    assert loaded.recovery_unlock_after is None
    print("  [ok] v2 -> v9 migration seeds balanced")


def test_v3_to_v9_migration_drops_ocr_and_seeds_balanced(tmp: Path) -> None:
    store, _, _, crypto_mod = _fresh_store(tmp)
    payload = {
        "password_hash": crypto_mod.hash_password("pw"),
        "enabled": True,
        "lockout_duration_minutes": 8,
        "ocr_enabled": True,
        "created_at": "2026-05-01T00:00:00+00:00",
        "schema_version": 3,
    }
    _write_envelope(tmp, payload, crypto_mod)

    loaded = store.load()
    assert loaded is not None
    assert loaded.schema_version == 11
    assert loaded.lockout_duration_minutes == 8
    assert loaded.detection_sensitivity == "balanced"
    assert loaded.anime_detection_enabled is False
    assert loaded.anime_detection_mode == "standard"
    assert loaded.recovery_unlock_after is None
    assert not hasattr(loaded, "ocr_enabled")
    print("  [ok] v3 -> v9 migration drops ocr and seeds balanced")


def test_v4_to_v9_migration_drops_ocr_and_seeds_balanced(tmp: Path) -> None:
    store, _, _, crypto_mod = _fresh_store(tmp)
    v4_payload = {
        "password_hash": crypto_mod.hash_password("pw"),
        "enabled": True,
        "lockout_duration_minutes": 7,
        "ocr_enabled": True,
        "committed_until": None,
        "created_at": "2026-05-01T00:00:00+00:00",
        "schema_version": 4,
    }
    _write_envelope(tmp, v4_payload, crypto_mod)

    loaded = store.load()
    assert loaded is not None
    assert loaded.schema_version == 11
    assert loaded.lockout_duration_minutes == 7
    assert loaded.detection_sensitivity == "balanced"
    assert loaded.anime_detection_enabled is False
    assert loaded.anime_detection_mode == "standard"
    assert loaded.recovery_unlock_after is None
    assert not hasattr(loaded, "ocr_enabled")

    raw = json.loads((tmp / "state.json").read_text(encoding="utf-8"))
    assert raw["payload"]["schema_version"] == 11
    assert "ocr_enabled" not in raw["payload"]
    print("  [ok] v4 -> v9 migration drops ocr, preserves duration, seeds balanced")


def test_v5_to_v9_migration_seeds_balanced(tmp: Path) -> None:
    store, _, _, crypto_mod = _fresh_store(tmp)
    payload = {
        "password_hash": crypto_mod.hash_password("pw"),
        "enabled": True,
        "lockout_duration_minutes": 6,
        "committed_until": None,
        "created_at": "2026-05-01T00:00:00+00:00",
        "schema_version": 5,
    }
    _write_envelope(tmp, payload, crypto_mod)

    loaded = store.load()
    assert loaded is not None
    assert loaded.schema_version == 11
    assert loaded.lockout_duration_minutes == 6
    assert loaded.detection_sensitivity == "balanced"
    assert loaded.anime_detection_enabled is False
    assert loaded.anime_detection_mode == "standard"
    assert loaded.recovery_unlock_after is None
    print("  [ok] v5 -> v9 migration seeds balanced")


def test_v6_to_v9_migration_seeds_anime_defaults(tmp: Path) -> None:
    store, _, _, crypto_mod = _fresh_store(tmp)
    payload = {
        "password_hash": crypto_mod.hash_password("pw"),
        "enabled": True,
        "lockout_duration_minutes": 6,
        "committed_until": None,
        "detection_sensitivity": "strict",
        "created_at": "2026-05-01T00:00:00+00:00",
        "schema_version": 6,
    }
    _write_envelope(tmp, payload, crypto_mod)

    loaded = store.load()
    assert loaded is not None
    assert loaded.schema_version == 11
    assert loaded.detection_sensitivity == "balanced"
    assert loaded.anime_detection_enabled is False
    assert loaded.anime_detection_mode == "standard"
    assert loaded.recovery_unlock_after is None
    print("  [ok] v6 -> v9 migration seeds anime defaults")


def test_v7_to_v9_migration_seeds_anime_mode(tmp: Path) -> None:
    store, _, _, crypto_mod = _fresh_store(tmp)
    payload = {
        "password_hash": crypto_mod.hash_password("pw"),
        "enabled": True,
        "lockout_duration_minutes": 6,
        "committed_until": None,
        "detection_sensitivity": "balanced",
        "anime_detection_enabled": True,
        "created_at": "2026-05-01T00:00:00+00:00",
        "schema_version": 7,
    }
    _write_envelope(tmp, payload, crypto_mod)

    loaded = store.load()
    assert loaded is not None
    assert loaded.schema_version == 11
    assert loaded.anime_detection_enabled is True
    assert loaded.anime_detection_mode == "standard"
    assert loaded.recovery_unlock_after is None
    print("  [ok] v7 -> v9 migration seeds anime mode")


def test_v8_to_v9_migration_seeds_recovery_unlock(tmp: Path) -> None:
    store, _, _, crypto_mod = _fresh_store(tmp)
    payload = {
        "password_hash": crypto_mod.hash_password("pw"),
        "enabled": True,
        "lockout_duration_minutes": 6,
        "committed_until": None,
        "detection_sensitivity": "balanced",
        "anime_detection_enabled": True,
        "anime_detection_mode": "strict",
        "created_at": "2026-05-01T00:00:00+00:00",
        "schema_version": 8,
    }
    _write_envelope(tmp, payload, crypto_mod)

    loaded = store.load()
    assert loaded is not None
    assert loaded.schema_version == 11
    assert loaded.anime_detection_enabled is True
    assert loaded.anime_detection_mode == "standard"
    assert loaded.recovery_unlock_after is None
    assert loaded.recovery_unlock_delay_minutes == 15
    assert loaded.lockout_recovery_enabled is False
    assert loaded.lockout_recovery_delay_minutes == 15
    print("  [ok] v8 -> v9 migration seeds recovery unlock default")


def test_v9_to_v11_migration_seeds_recovery_settings_and_shutdown(tmp: Path) -> None:
    store, _, _, crypto_mod = _fresh_store(tmp)
    payload = {
        "password_hash": crypto_mod.hash_password("pw"),
        "enabled": True,
        "lockout_duration_minutes": 6,
        "committed_until": None,
        "detection_sensitivity": "balanced",
        "anime_detection_enabled": True,
        "anime_detection_mode": "strict",
        "recovery_unlock_after": None,
        "created_at": "2026-05-01T00:00:00+00:00",
        "schema_version": 9,
    }
    _write_envelope(tmp, payload, crypto_mod)

    loaded = store.load()
    assert loaded is not None
    assert loaded.schema_version == 11
    assert loaded.detection_sensitivity == "balanced"
    assert loaded.anime_detection_mode == "standard"
    assert loaded.recovery_unlock_delay_minutes == 15
    assert loaded.lockout_recovery_enabled is False
    assert loaded.lockout_recovery_delay_minutes == 15
    assert loaded.shutdown_after_lockout is True
    print("  [ok] v9 -> v11 migration seeds recovery settings and shutdown")


def test_recovery_unlock_schedule_and_apply(tmp: Path) -> None:
    store, State, _, crypto_mod = _fresh_store(tmp)
    from datetime import datetime, timedelta, timezone
    from brake.state.recovery_unlock import apply_due_recovery_unlock, schedule_recovery_unlock

    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(timespec="seconds")
    state = State(
        password_hash=crypto_mod.hash_password("pw"),
        enabled=True,
        committed_until=future,
        recovery_unlock_delay_minutes=2,
    )
    store.save(state)

    scheduled = schedule_recovery_unlock(store, state, delay_seconds=60)
    pending = store.load()
    assert pending is not None
    assert pending.enabled is True
    assert pending.commitment_active()
    assert pending.recovery_unlock_after == scheduled
    assert pending.recovery_unlock_pending()

    pending.recovery_unlock_after = None
    store.save(pending)
    scheduled = schedule_recovery_unlock(store, pending)
    pending = store.load()
    assert pending is not None
    assert pending.recovery_unlock_after == scheduled
    remaining = pending.recovery_unlock_after_dt() - datetime.now(timezone.utc)
    assert 100 <= remaining.total_seconds() <= 130

    pending.recovery_unlock_after = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(timespec="seconds")
    store.save(pending)
    applied = apply_due_recovery_unlock(store)
    assert applied is not None
    assert applied.enabled is False
    assert applied.committed_until is None
    assert applied.recovery_unlock_after is None
    print("  [ok] recovery unlock waits, then clears protection and commitment")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="brake-test-") as td:
        tmp = Path(td)
        print(f"Using temp dir: {tmp}")
        for fn in (
            test_roundtrip_and_password_verify,
            test_invalid_sensitivity_coerces_to_balanced,
            test_duration_clamping,
            test_recovery_cooldown_clamping,
            test_commitment_active,
            test_tamper_detection,
            test_missing_state_returns_none,
            test_deletion_bypass_refused,
            test_v1_to_v9_migration,
            test_v2_to_v9_migration_seeds_balanced,
            test_v3_to_v9_migration_drops_ocr_and_seeds_balanced,
            test_v4_to_v9_migration_drops_ocr_and_seeds_balanced,
            test_v5_to_v9_migration_seeds_balanced,
            test_v6_to_v9_migration_seeds_anime_defaults,
            test_v7_to_v9_migration_seeds_anime_mode,
            test_v8_to_v9_migration_seeds_recovery_unlock,
            test_v9_to_v11_migration_seeds_recovery_settings_and_shutdown,
            test_recovery_unlock_schedule_and_apply,
        ):
            sub = tmp / fn.__name__
            sub.mkdir()
            print(f"\n{fn.__name__}")
            fn(sub)
    print("\nAll tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
