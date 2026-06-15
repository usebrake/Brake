"""Signed memory of recent full lockout incidents.

Brake is a reactive deterrent. A repeated relapse spiral should not receive
exactly the same consequence every time, so this ledger remembers recent full
lockouts and lets the watcher scale the next fresh lockout duration. The file
is HMAC-signed like state data; tampering fails secure to the capped multiplier.
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import List, Optional

from brake import paths
from brake.state import crypto
from brake.state.schema import LOCKOUT_DURATION_MAX
from brake.test_mode import t

_log = logging.getLogger(__name__)

INCIDENT_WINDOW_SECONDS = t(24 * 60 * 60, 60)
MULTIPLIER_CAP = 3
MAX_LOCKOUT_SECONDS = LOCKOUT_DURATION_MAX * 60


class IncidentMemoryTamperedError(RuntimeError):
    """Raised internally when incident memory fails integrity checks."""


def _canonical(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


class IncidentLedger:
    def __init__(self, file_path: Optional[Path] = None, key_path: Optional[Path] = None) -> None:
        self.path = file_path or paths.incident_file()
        self.key_path = key_path or paths.key_file()

    def _read_payload(self) -> dict:
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        try:
            payload = raw["payload"]
            signature = raw["hmac"]
        except (KeyError, TypeError) as e:
            raise IncidentMemoryTamperedError(f"missing fields: {e}") from e
        key = crypto.load_or_create_hmac_key(self.key_path)
        if not crypto.verify_signature(_canonical(payload), signature, key):
            raise IncidentMemoryTamperedError("HMAC verification failed")
        return payload

    def _load_recent(self, now: Optional[float] = None) -> Optional[List[float]]:
        now = float(time.time() if now is None else now)
        if not self.path.exists():
            return []
        try:
            payload = self._read_payload()
            timestamps = [float(v) for v in payload.get("timestamps", [])]
        except Exception as e:
            age = _file_age_seconds(self.path)
            if age is not None and age > INCIDENT_WINDOW_SECONDS:
                _log.critical(
                    "Incident memory unreadable but stale (age=%.0fs): %s. Clearing.",
                    age,
                    e,
                )
                self.clear()
                return []
            _log.critical("Incident memory unreadable or tampered (%s); fail-secure multiplier cap.", e)
            return None
        return self._prune(timestamps, now)

    @staticmethod
    def _prune(timestamps: List[float], now: float) -> List[float]:
        cutoff = now - INCIDENT_WINDOW_SECONDS
        return [ts for ts in timestamps if ts >= cutoff and ts <= now + 60]

    def recent_count(self, now: Optional[float] = None) -> int:
        now = float(time.time() if now is None else now)
        timestamps = self._load_recent(now)
        if timestamps is None:
            return MULTIPLIER_CAP
        return len(timestamps)

    def record(self, now: Optional[float] = None) -> None:
        now = float(time.time() if now is None else now)
        timestamps = self._load_recent(now)
        if timestamps is None:
            timestamps = []
        timestamps = self._prune([*timestamps, now], now)
        try:
            self._save(timestamps)
        except Exception as e:
            # Incident memory strengthens repeat consequences, but a write
            # failure must never stop the active lockout itself.
            _log.critical("Failed to write incident memory (%s); continuing lockout.", e)

    def scale(self, base_seconds: int, prior_count: int) -> int:
        multiplier = min(int(prior_count) + 1, MULTIPLIER_CAP)
        return min(int(base_seconds) * multiplier, MAX_LOCKOUT_SECONDS)

    def _save(self, timestamps: List[float]) -> None:
        key = crypto.load_or_create_hmac_key(self.key_path)
        payload = {"timestamps": [float(ts) for ts in timestamps]}
        envelope = {"payload": payload, "hmac": crypto.sign(_canonical(payload), key)}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(envelope, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

    def clear(self) -> None:
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass
        except Exception as e:
            _log.warning("Failed to clear incident memory: %s", e)


def _file_age_seconds(path: Path) -> Optional[float]:
    try:
        return max(0.0, time.time() - path.stat().st_mtime)
    except OSError:
        return None
