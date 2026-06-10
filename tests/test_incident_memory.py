"""Tests for signed repeated-lockout incident memory."""
from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from brake.incident_memory import INCIDENT_WINDOW_SECONDS, MAX_LOCKOUT_SECONDS, MULTIPLIER_CAP, IncidentLedger


def _ledger(tmp: Path) -> IncidentLedger:
    return IncidentLedger(file_path=tmp / "incidents.json", key_path=tmp / "state.key")


def test_signing_round_trip(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    ledger.record(now=1000.0)
    assert ledger.recent_count(now=1001.0) == 1
    raw = json.loads((tmp_path / "incidents.json").read_text(encoding="utf-8"))
    assert "payload" in raw and "hmac" in raw
    print("  [ok] incident memory signs and reloads")


def test_window_prunes_old_incidents(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    ledger.record(now=1000.0)
    ledger.record(now=1005.0)
    assert ledger.recent_count(now=1005.0 + INCIDENT_WINDOW_SECONDS + 1) == 0
    print("  [ok] incident memory decays outside the window")


def test_scale_progression_and_cap(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    base = 15 * 60
    assert ledger.scale(base, 0) == 15 * 60
    assert ledger.scale(base, 1) == 30 * 60
    assert ledger.scale(base, 2) == 45 * 60
    assert ledger.scale(base, 99) == min(base * MULTIPLIER_CAP, MAX_LOCKOUT_SECONDS)
    assert ledger.scale(50 * 60, 2) == MAX_LOCKOUT_SECONDS
    print("  [ok] incident memory scales duration and caps at max")


def test_tamper_fails_secure_to_cap(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    ledger.record(now=1000.0)
    raw = json.loads((tmp_path / "incidents.json").read_text(encoding="utf-8"))
    raw["payload"]["timestamps"].append(1001.0)
    (tmp_path / "incidents.json").write_text(json.dumps(raw), encoding="utf-8")
    assert ledger.recent_count(now=1002.0) == MULTIPLIER_CAP
    print("  [ok] tampered incident memory fails secure")


def test_clear(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    ledger.record(now=1000.0)
    ledger.clear()
    assert ledger.recent_count(now=1001.0) == 0
    print("  [ok] incident memory clears")


def main() -> int:
    import tempfile

    tests = [
        test_signing_round_trip,
        test_window_prunes_old_incidents,
        test_scale_progression_and_cap,
        test_tamper_fails_secure_to_cap,
        test_clear,
    ]
    for fn in tests:
        print(f"\n{fn.__name__}")
        with tempfile.TemporaryDirectory(prefix="brake-incidents-test-") as d:
            fn(Path(d))
    print("\nAll tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
