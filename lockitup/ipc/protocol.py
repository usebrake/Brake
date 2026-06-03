"""IPC wire protocol — HMAC-signed JSON frames over a Windows named pipe.

Frame layout (each direction):
    [4-byte big-endian length N] [N bytes of body]
Body is JSON: {"payload": {...}, "hmac": "<hex sha256>"}
HMAC key is the same DPAPI-machine-scoped key used for state.json signing,
so spoofing requires both file access AND code execution as a local user.
"""
from __future__ import annotations

import json
import struct
from enum import Enum
from typing import Any, Callable, Dict, Optional

from lockitup import paths
from lockitup.state import crypto

PIPE_NAME = r"\\.\pipe\lockitup"

MAX_FRAME = 1 << 20  # 1 MiB cap


class Command(str, Enum):
    PING = "PING"
    STATUS = "STATUS"
    ENABLE = "ENABLE"
    DISABLE = "DISABLE"
    RESET_PASSWORD = "RESET_PASSWORD"
    SET_DURATION = "SET_DURATION"
    SET_COMMITMENT = "SET_COMMITMENT"
    SET_SENSITIVITY = "SET_SENSITIVITY"
    SET_ANIME_ENABLED = "SET_ANIME_ENABLED"
    SET_ANIME_MODE = "SET_ANIME_MODE"


def _canonical(d: Dict[str, Any]) -> bytes:
    return json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _key() -> bytes:
    return crypto.load_or_create_hmac_key(paths.key_file())


def encode(payload: Dict[str, Any]) -> bytes:
    """Serialize+sign a payload to wire bytes (length-prefixed)."""
    key = _key()
    envelope = {"payload": payload, "hmac": crypto.sign(_canonical(payload), key)}
    body = json.dumps(envelope).encode("utf-8")
    if len(body) > MAX_FRAME:
        raise ValueError(f"frame too large: {len(body)}")
    return struct.pack(">I", len(body)) + body


def decode(body: bytes) -> Dict[str, Any]:
    """Verify + unwrap a body (without the 4-byte length prefix)."""
    envelope = json.loads(body.decode("utf-8"))
    payload = envelope.get("payload")
    sig = envelope.get("hmac")
    if not isinstance(payload, dict) or not isinstance(sig, str):
        raise ValueError("malformed envelope")
    if not crypto.verify_signature(_canonical(payload), sig, _key()):
        raise PermissionError("HMAC verification failed")
    return payload


def read_frame(read_exact: Callable[[int], Optional[bytes]]) -> Optional[Dict[str, Any]]:
    """Read one frame using a caller-supplied read-exactly-N function.

    The function returns bytes of the requested length or None on EOF.
    Returns None on clean EOF, raises on protocol error.
    """
    header = read_exact(4)
    if header is None:
        return None
    if len(header) != 4:
        raise ValueError("short header")
    length = struct.unpack(">I", header)[0]
    if length > MAX_FRAME:
        raise ValueError(f"frame too large: {length}")
    body = read_exact(length)
    if body is None or len(body) != length:
        return None
    return decode(body)
