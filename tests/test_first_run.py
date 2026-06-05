"""First-run bootstrap tests."""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _reset_modules() -> None:
    for mod in [k for k in list(sys.modules) if k == "brake" or k.startswith("brake.")]:
        del sys.modules[mod]


def _clean(path: Path) -> Path:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)
    return path


def test_first_run_state_created_before_recovery(tmp: Path) -> None:
    os.environ["BRAKE_DATA_DIR"] = str(_clean(tmp))
    _reset_modules()

    from brake.state.first_run import ensure_first_run_state
    from brake.state.recovery import RecoveryStore
    from brake.state.store import StateStore

    store = StateStore()
    assert ensure_first_run_state(store) is True
    assert store.exists()
    assert store.key_path.exists()

    token = RecoveryStore().generate()
    assert token
    assert store.load() is not None
    print("  [ok] first-run state exists before recovery generation")


def test_first_run_allows_precreated_key_without_state(tmp: Path) -> None:
    os.environ["BRAKE_DATA_DIR"] = str(_clean(tmp))
    _reset_modules()

    from brake.state.crypto import load_or_create_hmac_key
    from brake.state.first_run import ensure_first_run_state
    from brake.state.store import StateStore

    store = StateStore()
    load_or_create_hmac_key(store.key_path)
    assert ensure_first_run_state(store) is True
    assert store.exists()
    print("  [ok] precreated key still allows first-run bootstrap")


def test_first_run_refuses_initialized_marker_without_state(tmp: Path) -> None:
    os.environ["BRAKE_DATA_DIR"] = str(_clean(tmp))
    _reset_modules()

    from brake.state.crypto import load_or_create_hmac_key
    from brake.state.first_run import ensure_first_run_state
    from brake.state.store import StateMissingError, StateStore

    store = StateStore()
    load_or_create_hmac_key(store.key_path)
    store.initialized_path.write_text("1", encoding="utf-8")
    try:
        ensure_first_run_state(store)
    except StateMissingError:
        print("  [ok] initialized marker without state refuses bootstrap")
        return
    raise AssertionError("expected StateMissingError")


if __name__ == "__main__":
    base = Path(os.environ.get("TMP", ".")) / "brake-first-run-tests"
    test_first_run_state_created_before_recovery(base / "a")
    test_first_run_allows_precreated_key_without_state(base / "b")
    test_first_run_refuses_initialized_marker_without_state(base / "c")
