"""Tests for agent single-instance locking and run/pause state semantics.

Covers:
- the named-mutex single-instance lock
- watcher: fresh install must not scan; tamper/missing/corrupt fail-secure
- hardening: same semantics, and bad state never raises
- supervisor: pid-reuse-safe process signatures
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_TEST_DATA_DIR = tempfile.TemporaryDirectory(prefix="brake-lifecycle-")
os.environ["BRAKE_DATA_DIR"] = _TEST_DATA_DIR.name

from brake.single_instance import SingleInstanceLock  # noqa: E402


def _temp_store():
    from brake.state import StateStore

    d = Path(tempfile.mkdtemp(prefix="brake-state-", dir=_TEST_DATA_DIR.name))
    return StateStore(state_path=d / "state.json", key_path=d / "state.key")


def _watcher_with(store):
    from brake.service.watcher import Watcher

    return Watcher(store=store)


def test_single_instance_lock_blocks_second_holder() -> None:
    if sys.platform != "win32":
        print("  [skip] not Windows")
        return
    name = f"Local\\BrakeTestMutex{os.getpid()}"
    first = SingleInstanceLock(name)
    second = SingleInstanceLock(name)
    try:
        assert first.acquire() is True
        assert second.acquire() is False
    finally:
        first.release()
        second.release()
    print("  [ok] second holder of the mutex is rejected")


def test_single_instance_lock_reacquirable_after_release() -> None:
    if sys.platform != "win32":
        print("  [skip] not Windows")
        return
    name = f"Local\\BrakeTestMutexB{os.getpid()}"
    first = SingleInstanceLock(name)
    assert first.acquire() is True
    first.release()
    second = SingleInstanceLock(name)
    try:
        assert second.acquire() is True
    finally:
        second.release()
    print("  [ok] released mutex can be re-acquired")


def test_fresh_install_does_not_scan() -> None:
    store = _temp_store()
    w = _watcher_with(store)
    assert w._state_says_run() is False
    print("  [ok] fresh install (no state) does not scan")


def test_disabled_state_does_not_scan_enabled_does() -> None:
    from brake.state.schema import State

    store = _temp_store()
    store.save(State(password_hash="h", enabled=False))
    assert _watcher_with(store)._state_says_run() is False

    store2 = _temp_store()
    store2.save(State(password_hash="h", enabled=True))
    assert _watcher_with(store2)._state_says_run() is True
    print("  [ok] disabled state pauses scanning, enabled state scans")


def test_tampered_state_fails_secure_to_scanning() -> None:
    from brake.state.schema import State

    store = _temp_store()
    store.save(State(password_hash="h", enabled=False))
    raw = json.loads(store.state_path.read_text(encoding="utf-8"))
    raw["payload"]["enabled"] = True  # invalidates the HMAC
    store.state_path.write_text(json.dumps(raw), encoding="utf-8")
    assert _watcher_with(store)._state_says_run() is True
    print("  [ok] tampered state fails secure to scanning")


def test_deleted_state_after_init_fails_secure_without_crashing() -> None:
    from brake.state.schema import State

    store = _temp_store()
    store.save(State(password_hash="h", enabled=False))
    store.state_path.unlink()  # initialized marker remains
    w = _watcher_with(store)
    assert w._state_says_run() is True  # and must not raise
    print("  [ok] deleted state after init fails secure, no crash")


def test_corrupt_state_fails_secure_without_crashing() -> None:
    from brake.state.schema import State

    store = _temp_store()
    store.save(State(password_hash="h", enabled=False))
    store.state_path.write_text("{not valid json", encoding="utf-8")
    assert _watcher_with(store)._state_says_run() is True
    print("  [ok] corrupt state fails secure, no crash")


def test_hardening_protected_semantics() -> None:
    import threading

    from brake.agent.hardening import HardeningLoop
    from brake.state.schema import State

    loop = HardeningLoop(threading.Event())

    loop.store = _temp_store()
    assert loop._protected() is False  # fresh: nothing to protect

    loop = HardeningLoop(threading.Event())
    loop.store = _temp_store()
    loop.store.save(State(password_hash="h", enabled=True))
    assert loop._protected() is True

    loop = HardeningLoop(threading.Event())
    loop.store = _temp_store()
    loop.store.save(State(password_hash="h", enabled=False))
    loop.store.state_path.write_text("garbage", encoding="utf-8")
    assert loop._protected() is True  # corrupt: fail-secure, no raise
    print("  [ok] hardening: fresh off, enabled on, corrupt fail-secure")


def test_process_signature_detects_liveness_and_reuse() -> None:
    from brake.service.windows_service import _process_signature, _spawned_agent_alive

    sig = _process_signature(os.getpid())
    assert sig is not None
    assert _spawned_agent_alive(sig) is True
    assert _spawned_agent_alive(None) is False
    # A different create time means the pid was recycled by another process.
    forged = (sig[0], sig[1] - 1000.0)
    assert _spawned_agent_alive(forged) is False
    print("  [ok] process signature catches death and pid reuse")


def main() -> int:
    tests = [
        test_single_instance_lock_blocks_second_holder,
        test_single_instance_lock_reacquirable_after_release,
        test_fresh_install_does_not_scan,
        test_disabled_state_does_not_scan_enabled_does,
        test_tampered_state_fails_secure_to_scanning,
        test_deleted_state_after_init_fails_secure_without_crashing,
        test_corrupt_state_fails_secure_without_crashing,
        test_hardening_protected_semantics,
        test_process_signature_detects_liveness_and_reuse,
    ]
    for fn in tests:
        print(f"\n{fn.__name__}")
        fn()
    print("\nAll tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
