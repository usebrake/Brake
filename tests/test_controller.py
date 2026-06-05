from __future__ import annotations

import importlib
import os
from pathlib import Path


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


if __name__ == "__main__":
    base = Path(os.environ.get("TMP", ".")) / "brake-controller-tests"
    test_installed_controller_does_not_direct_write_without_service(base / "installed")
    test_dev_controller_can_direct_write_without_service(base / "dev")
