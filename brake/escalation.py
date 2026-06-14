"""Signed escalation/probation state.

After a first detection, Brake writes a pending probation record and shuts
down after the initial lockout. On the next Windows boot, the agent activates a
short strict-watch window. If nudity is detected during that window, the watcher
issues the penalty lockout.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from brake import paths
from brake.state import crypto
from brake.state.schema import LOCKOUT_DURATION_MAX
from brake.test_mode import t

_log = logging.getLogger(__name__)


PROBATION_SECONDS = t(5 * 60, 30)
STALE_UNREADABLE_PROBATION_SECONDS = (LOCKOUT_DURATION_MAX * 60) + PROBATION_SECONDS + (5 * 60)


class ProbationTamperedError(RuntimeError):
    """Raised when probation.json fails HMAC verification."""


def _canonical(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def current_boot_marker() -> float:
    try:
        import psutil
        return float(psutil.boot_time())
    except Exception:
        return time.time()


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


@dataclass
class ProbationRecord:
    created_at: str
    created_boot_marker: float
    duration_seconds: int
    penalty_duration_seconds: int
    reason: str
    active_until: str = ""

    def is_pending(self) -> bool:
        return not self.active_until

    def should_activate(self, boot_marker: float) -> bool:
        return self.is_pending() and abs(float(self.created_boot_marker) - float(boot_marker)) > 1.0

    def activate(self, now: Optional[datetime] = None) -> None:
        now = now or _now()
        self.active_until = (now + timedelta(seconds=int(self.duration_seconds))).isoformat()

    def remaining_seconds(self) -> float:
        if not self.active_until:
            return 0.0
        end = datetime.fromisoformat(self.active_until)
        return max(0.0, (end - datetime.now(timezone.utc)).total_seconds())

    def is_expired(self) -> bool:
        return bool(self.active_until) and self.remaining_seconds() <= 0.0


class ProbationStore:
    def __init__(self, file_path: Optional[Path] = None) -> None:
        self.path = file_path or paths.probation_file()

    def create_pending(self, penalty_duration_seconds: int, reason: str) -> ProbationRecord:
        record = ProbationRecord(
            created_at=_now().isoformat(),
            created_boot_marker=current_boot_marker(),
            duration_seconds=PROBATION_SECONDS,
            penalty_duration_seconds=int(penalty_duration_seconds),
            reason=reason,
        )
        self.save(record)
        return record

    def load(self) -> Optional[ProbationRecord]:
        if not self.path.exists():
            return None
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as e:
            age = _file_age_seconds(self.path)
            if age is not None and age > STALE_UNREADABLE_PROBATION_SECONDS:
                _log.critical(
                    "Probation file unreadable but stale (age=%.0fs): %s. Clearing.",
                    age,
                    e,
                )
                self.clear()
                return None
            raise ProbationTamperedError(f"unreadable probation file: {e}") from e
        try:
            payload = raw["payload"]
            signature = raw["hmac"]
        except (KeyError, TypeError) as e:
            raise ProbationTamperedError(f"missing fields: {e}") from e
        key = crypto.load_or_create_hmac_key(paths.key_file())
        if not crypto.verify_signature(_canonical(payload), signature, key):
            raise ProbationTamperedError("HMAC verification failed")
        return ProbationRecord(**payload)

    def save(self, record: ProbationRecord) -> None:
        key = crypto.load_or_create_hmac_key(paths.key_file())
        payload = asdict(record)
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
            _log.warning("Failed to clear probation file: %s", e)


def _file_age_seconds(path: Path) -> Optional[float]:
    try:
        return max(0.0, time.time() - path.stat().st_mtime)
    except OSError:
        return None
