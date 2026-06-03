"""Roundtrip + tamper tests for the IPC wire protocol.

These exercise encode/decode without opening a real named pipe.
"""
from __future__ import annotations

import json
import os
import struct
import sys
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _fresh_env(tmp: Path):
    os.environ["BRAKE_DATA_DIR"] = str(tmp)
    for mod in [k for k in list(sys.modules) if k.startswith("brake.")]:
        del sys.modules[mod]
    from brake.ipc import protocol
    return protocol


def test_encode_decode_roundtrip(tmp: Path) -> None:
    protocol = _fresh_env(tmp)
    wire = protocol.encode({"cmd": "PING"})
    # First 4 bytes are length
    length = struct.unpack(">I", wire[:4])[0]
    assert length == len(wire) - 4
    decoded = protocol.decode(wire[4:])
    assert decoded == {"cmd": "PING"}
    print("  [ok] encode/decode roundtrip")


def test_tampered_payload_rejected(tmp: Path) -> None:
    protocol = _fresh_env(tmp)
    wire = protocol.encode({"cmd": "DISABLE", "password": "secret"})
    body = wire[4:]
    env = json.loads(body.decode())
    # Attacker flips the cmd without recomputing the HMAC
    env["payload"]["cmd"] = "ENABLE"
    bad = json.dumps(env).encode()
    try:
        protocol.decode(bad)
    except PermissionError:
        print("  [ok] tampered envelope rejected by HMAC")
        return
    raise AssertionError("Tampered payload was accepted!")


def test_read_frame_with_callable(tmp: Path) -> None:
    """read_frame should support any read-exactly-N callable, not just sockets."""
    protocol = _fresh_env(tmp)
    wire = protocol.encode({"cmd": "STATUS"})
    pos = [0]

    def reader(n: int):
        chunk = wire[pos[0]:pos[0] + n]
        pos[0] += len(chunk)
        return chunk if chunk else None

    frame = protocol.read_frame(reader)
    assert frame == {"cmd": "STATUS"}
    # second call: EOF
    assert protocol.read_frame(reader) is None
    print("  [ok] read_frame works with arbitrary reader callable")


def test_max_frame_enforced(tmp: Path) -> None:
    protocol = _fresh_env(tmp)
    big_payload = {"cmd": "PING", "blob": "x" * (protocol.MAX_FRAME + 1)}
    try:
        protocol.encode(big_payload)
    except ValueError:
        print("  [ok] oversized frame rejected at encode")
        return
    raise AssertionError("Oversized frame was accepted!")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="brake-ipc-") as td:
        tmp = Path(td)
        print(f"Using temp dir: {tmp}")
        for fn in (
            test_encode_decode_roundtrip,
            test_tampered_payload_rejected,
            test_read_frame_with_callable,
            test_max_frame_enforced,
        ):
            sub = tmp / fn.__name__
            sub.mkdir()
            print(f"\n{fn.__name__}")
            fn(sub)
    print("\nAll tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
