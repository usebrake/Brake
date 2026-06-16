from __future__ import annotations

import importlib
import os
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _fresh(tmp: Path):
    os.environ["BRAKE_DATA_DIR"] = str(tmp)
    for name in list(importlib.sys.modules):
        if name.startswith("brake.") or name == "brake":
            importlib.sys.modules.pop(name, None)

    from brake.gui.controller import Controller
    from brake.state import State, StateStore
    from brake.state.crypto import hash_password

    return Controller, State, StateStore, hash_password


def test_installed_controller_does_not_direct_write_without_service(tmp: Path) -> None:
    Controller, State, StateStore, hash_password = _fresh(tmp)
    store = StateStore()
    store.save(State(password_hash=hash_password("password"), enabled=True, lockout_duration_minutes=3))

    controller = Controller(allow_direct_writes=False)
    controller.service_up = lambda: False  # type: ignore[method-assign]

    ok, err = controller.set_duration(5)
    assert not ok
    assert err == "service_unavailable"
    assert store.load().lockout_duration_minutes == 3
    print("  [ok] installed controller refuses direct writes without service")


def test_dev_controller_can_direct_write_without_service(tmp: Path) -> None:
    Controller, State, StateStore, hash_password = _fresh(tmp)
    store = StateStore()
    store.save(State(password_hash=hash_password("password"), enabled=True, lockout_duration_minutes=3))

    controller = Controller(allow_direct_writes=True)
    controller.service_up = lambda: False  # type: ignore[method-assign]

    ok, err = controller.set_duration(5)
    assert ok, err
    assert store.load().lockout_duration_minutes == 5
    print("  [ok] dev controller still allows direct writes without service")


def test_recovery_settings_require_password_to_loosen_when_enabled(tmp: Path) -> None:
    Controller, State, StateStore, hash_password = _fresh(tmp)
    store = StateStore()
    store.save(State(password_hash=hash_password("password"), enabled=True))

    controller = Controller(allow_direct_writes=True)
    controller.service_up = lambda: False  # type: ignore[method-assign]

    ok, err = controller.set_recovery_settings(10, False, 15)
    assert not ok
    assert err == "password_required"

    ok, err = controller.set_recovery_settings(10, False, 15, password="wrong")
    assert not ok
    assert err == "wrong_password"

    ok, err = controller.set_recovery_settings(10, False, 15, password="password")
    assert ok, err
    saved = store.load()
    assert saved is not None
    assert saved.recovery_unlock_delay_minutes == 10
    print("  [ok] enabled recovery loosening requires password")


def test_commitment_blocks_recovery_loosening_but_allows_stricter(tmp: Path) -> None:
    Controller, State, StateStore, hash_password = _fresh(tmp)
    store = StateStore()
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(timespec="seconds")
    store.save(State(
        password_hash=hash_password("password"),
        enabled=True,
        committed_until=future,
        recovery_unlock_delay_minutes=15,
        lockout_recovery_enabled=False,
        lockout_recovery_delay_minutes=15,
    ))

    controller = Controller(allow_direct_writes=True)
    controller.service_up = lambda: False  # type: ignore[method-assign]

    ok, err = controller.set_recovery_settings(15, True, 15, password="password")
    assert not ok
    assert err == "commitment_blocks_loosening_recovery"

    ok, err = controller.set_recovery_settings(20, False, 20)
    assert ok, err
    saved = store.load()
    assert saved is not None
    assert saved.recovery_unlock_delay_minutes == 20
    assert saved.lockout_recovery_enabled is False
    assert saved.lockout_recovery_delay_minutes == 20
    print("  [ok] commitment blocks easier recovery but allows stricter settings")


def test_shutdown_toggle_requires_password_to_loosen_when_enabled(tmp: Path) -> None:
    Controller, State, StateStore, hash_password = _fresh(tmp)
    store = StateStore()
    store.save(State(password_hash=hash_password("password"), enabled=True))

    controller = Controller(allow_direct_writes=True)
    controller.service_up = lambda: False  # type: ignore[method-assign]

    ok, err = controller.set_shutdown_after_lockout(False)
    assert not ok
    assert err == "password_required"

    ok, err = controller.set_shutdown_after_lockout(False, password="wrong")
    assert not ok
    assert err == "wrong_password"

    ok, err = controller.set_shutdown_after_lockout(False, password="password")
    assert ok, err
    saved = store.load()
    assert saved is not None
    assert saved.shutdown_after_lockout is False
    print("  [ok] enabled shutdown loosening requires password")


def test_commitment_blocks_turning_shutdown_off_but_allows_on(tmp: Path) -> None:
    Controller, State, StateStore, hash_password = _fresh(tmp)
    store = StateStore()
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(timespec="seconds")
    store.save(State(
        password_hash=hash_password("password"),
        enabled=True,
        committed_until=future,
        shutdown_after_lockout=True,
    ))

    controller = Controller(allow_direct_writes=True)
    controller.service_up = lambda: False  # type: ignore[method-assign]

    ok, err = controller.set_shutdown_after_lockout(False, password="password")
    assert not ok
    assert err == "commitment_blocks_loosening_shutdown"

    saved = store.load()
    assert saved is not None
    saved.shutdown_after_lockout = False
    store.save(saved)

    ok, err = controller.set_shutdown_after_lockout(True)
    assert ok, err
    saved = store.load()
    assert saved is not None
    assert saved.shutdown_after_lockout is True
    print("  [ok] commitment blocks shutdown loosening but allows stricter setting")


def test_corrupt_state_status_is_fail_secure_not_off(tmp: Path) -> None:
    Controller, State, StateStore, hash_password = _fresh(tmp)
    store = StateStore()
    store.save(State(password_hash=hash_password("password"), enabled=False))
    store.state_path.write_text("", encoding="utf-8")

    controller = Controller(allow_direct_writes=True)
    controller.service_up = lambda: False  # type: ignore[method-assign]

    status = controller.status()
    assert status["initialized"] is True
    assert status["enabled"] is True
    assert status["fail_secure"] is True
    assert "valid JSON" in status["state_error"]
    print("  [ok] corrupt state reports fail-secure active status")


def test_failed_ipc_status_falls_back_to_fail_secure_state(tmp: Path) -> None:
    Controller, State, StateStore, hash_password = _fresh(tmp)
    store = StateStore()
    store.save(State(password_hash=hash_password("password"), enabled=False))
    store.state_path.write_text("", encoding="utf-8")

    controller = Controller(allow_direct_writes=True)
    controller.service_up = lambda: True  # type: ignore[method-assign]
    controller.ipc.status = lambda: {"ok": False, "error": "Expecting value"}  # type: ignore[method-assign]

    status = controller.status()
    assert status["enabled"] is True
    assert status["fail_secure"] is True
    print("  [ok] failed IPC status falls back to fail-secure")


def test_recovery_code_repairs_corrupt_state(tmp: Path) -> None:
    Controller, State, StateStore, hash_password = _fresh(tmp)
    from brake.state.recovery import RecoveryStore

    store = StateStore()
    store.save(State(password_hash=hash_password("password"), enabled=False))
    token = RecoveryStore().generate()
    store.state_path.write_text("", encoding="utf-8")

    controller = Controller(allow_direct_writes=True)
    controller.service_up = lambda: False  # type: ignore[method-assign]

    ok, err = controller.reset_password_with_recovery(token, "new-password")
    assert ok, err
    repaired = store.load()
    assert repaired is not None
    assert repaired.enabled is True
    status = controller.status()
    assert not status.get("fail_secure", False)
    assert status["enabled"] is True
    print("  [ok] recovery code repairs corrupt state")


def test_service_ipc_corrupt_state_status_and_repair(tmp: Path) -> None:
    _Controller, State, StateStore, hash_password = _fresh(tmp)
    from brake.service.ipc_server import IPCServer
    from brake.state.recovery import RecoveryStore

    store = StateStore()
    store.save(State(password_hash=hash_password("password"), enabled=False))
    token = RecoveryStore().generate()
    store.state_path.write_text("", encoding="utf-8")

    server = IPCServer(store, threading.Event())
    status = server._cmd_status()
    assert status["ok"] is True
    assert status["data"]["enabled"] is True
    assert status["data"]["fail_secure"] is True

    repaired = server._cmd_reset_password(token, "new-password")
    assert repaired["ok"] is True
    loaded = store.load()
    assert loaded is not None
    assert loaded.enabled is True
    assert not server._cmd_status()["data"].get("fail_secure", False)
    print("  [ok] service IPC reports and repairs corrupt state")


if __name__ == "__main__":
    base = Path(os.environ.get("TMP", ".")) / "brake-controller-tests"
    test_installed_controller_does_not_direct_write_without_service(base / "installed")
    test_dev_controller_can_direct_write_without_service(base / "dev")
    test_recovery_settings_require_password_to_loosen_when_enabled(base / "recovery-password")
    test_commitment_blocks_recovery_loosening_but_allows_stricter(base / "recovery-commitment")
    test_shutdown_toggle_requires_password_to_loosen_when_enabled(base / "shutdown-password")
    test_commitment_blocks_turning_shutdown_off_but_allows_on(base / "shutdown-commitment")
    test_corrupt_state_status_is_fail_secure_not_off(base / "corrupt-status")
    test_failed_ipc_status_falls_back_to_fail_secure_state(base / "ipc-status-fallback")
    test_recovery_code_repairs_corrupt_state(base / "corrupt-repair")
    test_service_ipc_corrupt_state_status_and_repair(base / "service-corrupt-repair")
