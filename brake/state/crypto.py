"""Crypto primitives for state integrity and password storage.

Three things live here:

1. Argon2id password hashing — for the user's disable password.
2. HMAC-SHA256 signing — guarantees the state.json file hasn't been edited
   to flip `enabled` to false. The key is machine-scoped, not derived from
   the password (so the service can verify state even before the user types
   their password).
3. Machine-scoped key storage — on Windows, the HMAC key is wrapped with
   DPAPI using CRYPTPROTECT_LOCAL_MACHINE so any account on this machine
   (including the LocalSystem service) can decrypt, but the blob is useless
   on another machine. Off-Windows (dev), we fall back to a plain file with
   a loud warning.
"""
from __future__ import annotations

import hmac
import logging
import os
import secrets
import sys
from hashlib import sha256
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

_log = logging.getLogger(__name__)

_HMAC_KEY_BYTES = 32
_PH = PasswordHasher()  # argon2-cffi defaults are sensible (t=3, m=64MiB, p=4)

MIN_PASSWORD_LENGTH = 4

# Recovery and development override helpers.
#
# There is NO plaintext backdoor token in the source. Two ways to recover:
#
# 1. (Production) A per-install random recovery token, generated once at
#    setup, shown to the user a single time, with only its argon2 hash on
#    disk in recovery.json. See brake.state.recovery.
#
# 2. (Dev only) Set env var BRAKE_DEV_BACKDOOR=<plaintext> on the
#    machine that runs the service/agent. Any password equal to that
#    value is accepted as a backdoor. Never set this in production
#    installs. Constant-time compared.
#
# Recovery-token use is handled explicitly by the recovery flows. It is not a
# normal password, so it does not silently unlock every password gate.


def backdoor_enabled() -> bool:
    return os.environ.get("BRAKE_NO_BACKDOOR", "0") != "1"


def _dev_backdoor_value() -> str:
    return os.environ.get("BRAKE_DEV_BACKDOOR", "")


def is_backdoor(password: str) -> bool:
    if not password or not backdoor_enabled():
        return False
    dev = _dev_backdoor_value()
    if dev and hmac.compare_digest(password, dev):
        _log.critical("DEV BACKDOOR (env BRAKE_DEV_BACKDOOR) used.")
        return True
    return False


# ---------- password hashing ----------

def hash_password(password: str) -> str:
    if not password:
        raise ValueError("password must not be empty")
    return _PH.hash(password)


def verify_password(stored_hash: str, password: str) -> bool:
    if is_backdoor(password):
        _log.critical("DEV BACKDOOR PASSWORD USED.")
        return True
    try:
        return _PH.verify(stored_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


# ---------- HMAC signing ----------

def sign(payload: bytes, key: bytes) -> str:
    return hmac.new(key, payload, sha256).hexdigest()


def verify_signature(payload: bytes, signature: str, key: bytes) -> bool:
    expected = sign(payload, key)
    return hmac.compare_digest(expected, signature)


# ---------- machine-scoped key storage ----------

class _DPAPIBackend:
    """Wrap/unwrap with Windows DPAPI, machine scope."""

    CRYPTPROTECT_LOCAL_MACHINE = 0x4

    def __init__(self) -> None:
        import win32crypt  # type: ignore[import-not-found]
        self._crypt = win32crypt

    def wrap(self, plaintext: bytes) -> bytes:
        # CryptProtectData(data, description, entropy, reserved, prompt_struct, flags)
        return self._crypt.CryptProtectData(
            plaintext, "Brake HMAC key", None, None, None,
            self.CRYPTPROTECT_LOCAL_MACHINE,
        )

    def unwrap(self, ciphertext: bytes) -> bytes:
        # CryptUnprotectData returns (description, data)
        _desc, data = self._crypt.CryptUnprotectData(
            ciphertext, None, None, None, self.CRYPTPROTECT_LOCAL_MACHINE,
        )
        return bytes(data)


class _PlainBackend:
    """Insecure fallback for non-Windows dev. Stores the key verbatim."""

    def wrap(self, plaintext: bytes) -> bytes:
        _log.warning("DPAPI unavailable; HMAC key stored in plaintext (DEV ONLY).")
        return plaintext

    def unwrap(self, ciphertext: bytes) -> bytes:
        return ciphertext


def _select_backend():
    if sys.platform == "win32":
        try:
            return _DPAPIBackend()
        except ImportError:
            _log.warning("pywin32 not installed; falling back to plaintext key storage.")
    return _PlainBackend()


def load_or_create_hmac_key(key_path: Path) -> bytes:
    """Return the machine-scoped HMAC key, creating it on first call."""
    backend = _select_backend()

    if key_path.exists():
        try:
            return backend.unwrap(key_path.read_bytes())
        except Exception as e:
            # Corrupt or wrong machine — refuse rather than silently regenerate
            # (regenerating would let an attacker who deleted state.key bypass
            # signature verification on a forged state.json).
            raise RuntimeError(
                f"Failed to unwrap HMAC key at {key_path}: {e}. "
                "Refusing to regenerate; manual intervention required."
            ) from e

    key = secrets.token_bytes(_HMAC_KEY_BYTES)
    key_path.parent.mkdir(parents=True, exist_ok=True)
    # Write atomically: tmp + replace, so a crash mid-write can't corrupt it.
    tmp = key_path.with_suffix(key_path.suffix + ".tmp")
    tmp.write_bytes(backend.wrap(key))
    os.replace(tmp, key_path)
    return key
