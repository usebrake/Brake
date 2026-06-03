"""Per-install emergency recovery token.

Replaces the old hardcoded `BACKDOOR_PASSWORD` constant. A unique random
token is generated once per install, shown to the user a single time,
and discarded — only an argon2 hash lives on disk (HMAC-signed alongside
state.json). Anyone disassembling the shipped binary will find no
plaintext token; verification is the same brute-force resistance as the
user's normal password.

The file is HMAC-signed with the same machine-scoped DPAPI key as
state.json. Tampering raises RecoveryTamperedError, which the caller can
treat as fail-secure (no backdoor at all).
"""
from __future__ import annotations

import json
import logging
import os
import secrets
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from argon2.exceptions import InvalidHashError, VerifyMismatchError

from brake import paths
from brake.state import crypto

_log = logging.getLogger(__name__)


# 24 url-safe bytes ≈ 32 characters. Random enough that brute force is
# impractical given argon2 verify cost. Long enough that a user has to
# write it down (which is the point — a memorized backdoor is no backdoor).
TOKEN_BYTES = 24


class RecoveryTamperedError(RuntimeError):
    """Raised when recovery.json fails HMAC verification."""


def _canonical(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


@dataclass
class _RecoveryRecord:
    token_hash: str   # argon2id hash of the plaintext token


class RecoveryStore:
    def __init__(self, file_path: Optional[Path] = None) -> None:
        self.path = file_path or paths.recovery_file()

    def exists(self) -> bool:
        return self.path.exists()

    def generate(self) -> str:
        """Create a new random token, save its argon2 hash, return plaintext.

        The plaintext is returned exactly once; the caller is responsible
        for showing it to the user and then discarding it. Calling this
        again rotates the token and invalidates the previous one.
        """
        token = secrets.token_urlsafe(TOKEN_BYTES)
        self._save(_RecoveryRecord(token_hash=crypto.hash_password(token)))
        _log.warning(
            "Recovery token generated. Plaintext shown to user once; only "
            "argon2 hash persisted to %s.", self.path,
        )
        return token

    def verify(self, candidate: str) -> bool:
        if not candidate:
            return False
        record = self._load()
        if record is None:
            return False
        try:
            from brake.state.crypto import _PH  # type: ignore[attr-defined]
            return bool(_PH.verify(record.token_hash, candidate))
        except (VerifyMismatchError, InvalidHashError):
            return False

    def _save(self, record: _RecoveryRecord) -> None:
        key = crypto.load_or_create_hmac_key(paths.key_file())
        payload = asdict(record)
        envelope = {"payload": payload, "hmac": crypto.sign(_canonical(payload), key)}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(f"{self.path.name}.{os.getpid()}.{time.time_ns()}.tmp")
        try:
            tmp.write_text(json.dumps(envelope, indent=2), encoding="utf-8")
            for attempt in range(5):
                try:
                    os.replace(tmp, self.path)
                    break
                except PermissionError:
                    if attempt == 4:
                        raise
                    time.sleep(0.05)
        finally:
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass

    def _load(self) -> Optional[_RecoveryRecord]:
        if not self.path.exists():
            return None
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            payload = raw["payload"]
            signature = raw["hmac"]
        except (KeyError, TypeError, json.JSONDecodeError) as e:
            raise RecoveryTamperedError(f"malformed recovery file: {e}") from e
        key = crypto.load_or_create_hmac_key(paths.key_file())
        if not crypto.verify_signature(_canonical(payload), signature, key):
            raise RecoveryTamperedError("HMAC verification failed")
        return _RecoveryRecord(**payload)
