r"""IPC client: GUI / agent → BrakeService.

Opens \\.\pipe\\brake, writes one request frame, reads one response frame,
closes. One round-trip per call — keeps the model simple.
"""
from __future__ import annotations

import logging
import struct
from typing import Any, Dict

from brake.ipc.protocol import Command, PIPE_NAME, decode, encode

_log = logging.getLogger(__name__)


class IPCError(RuntimeError):
    pass


class IPCClient:
    def __init__(self, timeout_ms: int = 2000) -> None:
        self.timeout_ms = timeout_ms

    # ---- low-level transport ----

    def _send_recv(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            import pywintypes  # type: ignore[import-not-found]
            import win32file   # type: ignore[import-not-found]
            import win32pipe   # type: ignore[import-not-found]
        except ImportError as e:
            raise IPCError(f"pywin32 not available: {e}") from e

        try:
            win32pipe.WaitNamedPipe(PIPE_NAME, self.timeout_ms)
        except pywintypes.error as e:
            raise IPCError(f"service pipe not available: {e}") from e

        try:
            handle = win32file.CreateFile(
                PIPE_NAME,
                win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                0, None, win32file.OPEN_EXISTING, 0, None,
            )
        except pywintypes.error as e:
            raise IPCError(f"cannot open pipe: {e}") from e

        try:
            win32file.WriteFile(handle, encode(payload))

            def _read_exact(n: int) -> bytes:
                out = bytearray()
                while len(out) < n:
                    hr, chunk = win32file.ReadFile(handle, n - len(out))
                    if hr != 0 or not chunk:
                        raise IPCError("short read from server")
                    out.extend(chunk)
                return bytes(out)

            header = _read_exact(4)
            length = struct.unpack(">I", header)[0]
            body = _read_exact(length)
            try:
                return decode(body)
            except PermissionError as e:
                raise IPCError(f"server response failed auth: {e}") from e
        finally:
            try:
                win32file.CloseHandle(handle)
            except Exception:
                pass

    # ---- typed commands ----

    def call(self, command: Command, **params) -> Dict[str, Any]:
        params["cmd"] = command.value
        return self._send_recv(params)

    def ping(self) -> bool:
        try:
            return bool(self.call(Command.PING).get("ok"))
        except IPCError:
            return False

    def status(self) -> Dict[str, Any]:
        return self.call(Command.STATUS)

    def enable(self, new_password: str) -> Dict[str, Any]:
        return self.call(Command.ENABLE, new_password=new_password)

    def disable(self, password: str) -> Dict[str, Any]:
        return self.call(Command.DISABLE, password=password)

    def reset_password(self, recovery_code: str, new_password: str) -> Dict[str, Any]:
        return self.call(
            Command.RESET_PASSWORD,
            recovery_code=recovery_code,
            new_password=new_password,
        )

    def set_duration(self, minutes: int) -> Dict[str, Any]:
        return self.call(Command.SET_DURATION, minutes=int(minutes))

    def set_commitment(self, until: str, password: str) -> Dict[str, Any]:
        return self.call(Command.SET_COMMITMENT, until=until, password=password)

    def set_sensitivity(self, value: str, password: str = "") -> Dict[str, Any]:
        return self.call(Command.SET_SENSITIVITY, value=value, password=password)

    def set_anime_enabled(self, enabled: bool, password: str = "") -> Dict[str, Any]:
        return self.call(Command.SET_ANIME_ENABLED, enabled=bool(enabled), password=password)

    def set_anime_mode(self, value: str, password: str = "") -> Dict[str, Any]:
        return self.call(Command.SET_ANIME_MODE, value=value, password=password)

    def set_shutdown_after_lockout(self, enabled: bool, password: str = "") -> Dict[str, Any]:
        return self.call(
            Command.SET_SHUTDOWN_AFTER_LOCKOUT,
            enabled=bool(enabled),
            password=password,
        )

    def cancel_recovery_unlock(self) -> Dict[str, Any]:
        return self.call(Command.CANCEL_RECOVERY_UNLOCK)

    def set_recovery_settings(
        self,
        recovery_unlock_delay_minutes: int,
        lockout_recovery_enabled: bool,
        lockout_recovery_delay_minutes: int,
        password: str = "",
    ) -> Dict[str, Any]:
        return self.call(
            Command.SET_RECOVERY_SETTINGS,
            recovery_unlock_delay_minutes=int(recovery_unlock_delay_minutes),
            lockout_recovery_enabled=bool(lockout_recovery_enabled),
            lockout_recovery_delay_minutes=int(lockout_recovery_delay_minutes),
            password=password,
        )
