"""Stale corrupt runtime files must not permanently kill scanning."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from brake.escalation import ProbationStore, ProbationTamperedError, STALE_UNREADABLE_PROBATION_SECONDS
from brake.incident_memory import INCIDENT_WINDOW_SECONDS, IncidentLedger, MULTIPLIER_CAP
from brake.lockout.persistence import LockoutPersistence, STALE_UNREADABLE_LOCKOUT_SECONDS, _TamperedLockoutError


def _nul_file(path: Path, size: int = 256) -> None:
    path.write_bytes(b"\0" * size)


def _make_stale(path: Path, age_seconds: float) -> None:
    ts = time.time() - age_seconds
    os.utime(path, (ts, ts))


def test_stale_corrupt_lockout_is_cleared(tmp_path: Path) -> None:
    path = tmp_path / "lockout.json"
    _nul_file(path)
    _make_stale(path, STALE_UNREADABLE_LOCKOUT_SECONDS + 10)
    assert LockoutPersistence(path).resume() is None
    assert not path.exists()
    print("  [ok] stale corrupt lockout file clears instead of killing agent")


def test_recent_corrupt_lockout_fails_secure(tmp_path: Path) -> None:
    path = tmp_path / "lockout.json"
    _nul_file(path)
    try:
        LockoutPersistence(path).resume()
    except _TamperedLockoutError:
        print("  [ok] recent corrupt lockout file still fails secure")
        return
    raise AssertionError("recent corrupt lockout did not fail secure")


def test_stale_corrupt_probation_is_cleared(tmp_path: Path) -> None:
    path = tmp_path / "probation.json"
    _nul_file(path)
    _make_stale(path, STALE_UNREADABLE_PROBATION_SECONDS + 10)
    assert ProbationStore(path).load() is None
    assert not path.exists()
    print("  [ok] stale corrupt probation file clears instead of killing agent")


def test_recent_corrupt_probation_fails_secure(tmp_path: Path) -> None:
    path = tmp_path / "probation.json"
    _nul_file(path)
    try:
        ProbationStore(path).load()
    except ProbationTamperedError:
        print("  [ok] recent corrupt probation file still fails secure")
        return
    raise AssertionError("recent corrupt probation did not fail secure")


def test_stale_corrupt_incident_memory_is_cleared(tmp_path: Path) -> None:
    path = tmp_path / "incidents.json"
    _nul_file(path)
    _make_stale(path, INCIDENT_WINDOW_SECONDS + 10)
    ledger = IncidentLedger(file_path=path, key_path=tmp_path / "state.key")
    assert ledger.recent_count() == 0
    assert not path.exists()
    print("  [ok] stale corrupt incident memory clears instead of punishing forever")


def test_recent_corrupt_incident_memory_fails_secure_to_cap(tmp_path: Path) -> None:
    path = tmp_path / "incidents.json"
    _nul_file(path)
    ledger = IncidentLedger(file_path=path, key_path=tmp_path / "state.key")
    assert ledger.recent_count() == MULTIPLIER_CAP
    print("  [ok] recent corrupt incident memory still fails secure")


def main() -> int:
    import tempfile

    tests = [
        test_stale_corrupt_lockout_is_cleared,
        test_recent_corrupt_lockout_fails_secure,
        test_stale_corrupt_probation_is_cleared,
        test_recent_corrupt_probation_fails_secure,
        test_stale_corrupt_incident_memory_is_cleared,
        test_recent_corrupt_incident_memory_fails_secure_to_cap,
    ]
    for fn in tests:
        print(f"\n{fn.__name__}")
        with tempfile.TemporaryDirectory(prefix="brake-runtime-corruption-test-") as d:
            fn(Path(d))
    print("\nAll tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
