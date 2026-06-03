"""Read/write the signed state.json.

Format on disk:

    {
      "payload": { ...State.to_dict()... },
      "hmac":    "<hex sha256 of canonical(payload) keyed by machine HMAC key>"
    }

The payload is signed, not encrypted — we want the service to be able to read
`enabled` and `locked_until` without the user's password, but tampering must
be detected. If the HMAC doesn't match, we raise StateTamperedError and the
service treats the install as compromised (fail-secure: trigger a lockout).
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Optional

from lockitup import paths
from lockitup.state import crypto
from lockitup.state.schema import State


class StateTamperedError(RuntimeError):
    """Raised when state.json fails HMAC verification."""


class StateMissingError(RuntimeError):
    """Raised when state.json is gone but the key file still exists.

    This signature ("key without state") almost always means someone deleted
    state.json hoping the wizard would re-run and let them set a new password.
    We refuse to bootstrap in this situation — a real fresh install means both
    files are gone.
    """


def _canonical(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


class StateStore:
    def __init__(self, state_path: Optional[Path] = None, key_path: Optional[Path] = None) -> None:
        self.state_path = state_path or paths.state_file()
        self.key_path = key_path or paths.key_file()

    def exists(self) -> bool:
        return self.state_path.exists()

    def check_no_deletion_bypass(self) -> None:
        """Raise if state.json was deleted while state.key is still there."""
        if not self.state_path.exists() and self.key_path.exists():
            raise StateMissingError(
                "state.json is missing but state.key is present. "
                "This usually means state.json was deleted to bypass protection. "
                "Refusing to re-run first-run setup. To fully reset, delete BOTH "
                f"{self.state_path} and {self.key_path}."
            )

    def load(self) -> Optional[State]:
        self.check_no_deletion_bypass()
        if not self.exists():
            return None
        raw = json.loads(self.state_path.read_text(encoding="utf-8"))
        try:
            payload = raw["payload"]
            signature = raw["hmac"]
        except (KeyError, TypeError) as e:
            raise StateTamperedError(f"state.json missing required fields: {e}") from e

        key = crypto.load_or_create_hmac_key(self.key_path)
        if not crypto.verify_signature(_canonical(payload), signature, key):
            raise StateTamperedError("state.json HMAC verification failed")

        state = State.from_dict(payload)
        on_disk_version = int(payload.get("schema_version", 1))
        if on_disk_version != state.schema_version:
            # silent upgrade so old files don't keep failing future loads
            self.save(state)
        return state

    def save(self, state: State) -> None:
        key = crypto.load_or_create_hmac_key(self.key_path)
        payload = state.to_dict()
        envelope = {
            "payload": payload,
            "hmac": crypto.sign(_canonical(payload), key),
        }
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_name(
            f"{self.state_path.name}.{os.getpid()}.{time.time_ns()}.tmp"
        )
        try:
            tmp.write_text(json.dumps(envelope, indent=2), encoding="utf-8")
            for attempt in range(5):
                try:
                    os.replace(tmp, self.state_path)
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
