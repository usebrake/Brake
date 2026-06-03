"""Persistent lockout state — survives shutdown, restart, hibernate, sleep.

On lockout start we write `lockout.json` with an absolute wall-clock end
timestamp. On reboot, the boot recovery script reads this file and re-spawns
the lockout if `end_at` is still in the future. The file is HMAC-signed with
the same machine key as state.json so editing it doesn't help — a failed
signature is treated as tampering and a full default-duration lockout is
re-applied (fail-secure).

Wall-clock (not monotonic) is necessary here because monotonic resets at
reboot. The user can change the system clock to bypass — but during an
active lockout the keyboard hook + fullscreen overlay block access to the
clock-change UI, so that bypass requires a reboot, deletion attempts on
this file (HMAC-protected), or both.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from brake import paths
from brake.state import crypto

_log = logging.getLogger(__name__)


@dataclass
class LockoutRecord:
    end_at: str           # ISO8601 UTC
    started_at: str       # ISO8601 UTC
    duration_seconds: int
    reason: str
    message: str = ""
    shutdown_on_done: bool = False

    def end_dt(self) -> datetime:
        return datetime.fromisoformat(self.end_at)

    def remaining_seconds(self) -> float:
        return max(0.0, (self.end_dt() - datetime.now(timezone.utc)).total_seconds())

    def is_expired(self) -> bool:
        return self.remaining_seconds() <= 0.0


def _canonical(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


class LockoutPersistence:
    def __init__(self, file_path: Optional[Path] = None) -> None:
        self.path = file_path or paths.lockout_file()

    def start(
        self,
        duration_seconds: int,
        reason: str,
        message: str = "",
        shutdown_on_done: bool = False,
    ) -> LockoutRecord:
        now = datetime.now(timezone.utc)
        record = LockoutRecord(
            end_at=(now.replace(microsecond=0) + _td(duration_seconds)).isoformat(),
            started_at=now.replace(microsecond=0).isoformat(),
            duration_seconds=int(duration_seconds),
            reason=reason,
            message=message,
            shutdown_on_done=bool(shutdown_on_done),
        )
        self._write(record)
        return record

    def resume(self) -> Optional[LockoutRecord]:
        """Return active record, or None if absent / expired / tampered.

        Tampering returns None too — but the caller (boot script / lockout
        process) should fail-secure by triggering a default lockout.
        """
        if not self.path.exists():
            return None
        try:
            return self._read()
        except _TamperedLockoutError as e:
            _log.critical("Lockout file tampered: %s — caller should fail-secure.", e)
            raise

    def clear(self) -> None:
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass

    # --- internals ---

    def _write(self, record: LockoutRecord) -> None:
        key = crypto.load_or_create_hmac_key(paths.key_file())
        payload = asdict(record)
        envelope = {"payload": payload, "hmac": crypto.sign(_canonical(payload), key)}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(envelope, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

    def _read(self) -> LockoutRecord:
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        try:
            payload = raw["payload"]
            signature = raw["hmac"]
        except (KeyError, TypeError) as e:
            raise _TamperedLockoutError(f"missing fields: {e}") from e
        key = crypto.load_or_create_hmac_key(paths.key_file())
        if not crypto.verify_signature(_canonical(payload), signature, key):
            raise _TamperedLockoutError("HMAC verification failed")
        payload.setdefault("message", "")
        payload.setdefault("shutdown_on_done", False)
        return LockoutRecord(**payload)


class _TamperedLockoutError(RuntimeError):
    pass


# tiny helper so we don't import timedelta everywhere
def _td(seconds: int):
    from datetime import timedelta
    return timedelta(seconds=seconds)
