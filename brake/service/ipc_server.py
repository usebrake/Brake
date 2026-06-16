"""Named-pipe IPC server hosted by BrakeService.

Single-instance loop: create pipe -> wait for client -> handle one request ->
disconnect -> repeat. Clients are short-lived (one RPC per connection).
"""
from __future__ import annotations

import logging
import struct
import threading
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from brake.detectors.anime_nsfw import anime_model_status
from brake.ipc.protocol import Command, PIPE_NAME, decode, encode
from brake.state import State, StateMissingError, StateStore, StateTamperedError
from brake.state.crypto import MIN_PASSWORD_LENGTH, hash_password, is_backdoor, verify_password
from brake.state.recovery import RecoveryStore, RecoveryTamperedError
from brake.state.recovery_unlock import apply_due_recovery_unlock, schedule_recovery_unlock
from brake.state.schema import (
    LOCKOUT_DURATION_MAX,
    LOCKOUT_DURATION_MIN,
    RECOVERY_COOLDOWN_MAX,
    RECOVERY_COOLDOWN_MIN,
)

_log = logging.getLogger(__name__)


class StateUnavailableError(RuntimeError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class IPCServer(threading.Thread):
    daemon = True

    def __init__(self, store: StateStore, stop_event: threading.Event) -> None:
        super().__init__(name="IPCServer")
        self.store = store
        self.stop_event = stop_event

    def run(self) -> None:
        _log.info("IPC server starting on %s", PIPE_NAME)
        while not self.stop_event.is_set():
            try:
                self._serve_one()
            except Exception as e:
                if not self.stop_event.is_set():
                    _log.exception("IPC server loop error: %s", e)
        _log.info("IPC server stopped.")

    # ---- low-level pipe handling ----

    def _pipe_security_attributes(self):
        """Allow the desktop user to open the service pipe.

        The pipe still uses the HMAC-signed protocol key, so this ACL only
        makes the transport reachable from the interactive desktop app. The
        service runs as LocalSystem; without an explicit ACL, Windows can
        create a pipe that exists but rejects normal desktop users.
        """
        import pywintypes      # type: ignore[import-not-found]
        import win32security   # type: ignore[import-not-found]

        sddl = "D:(A;;GA;;;SY)(A;;GA;;;BA)(A;;GRGW;;;AU)"
        sd = win32security.ConvertStringSecurityDescriptorToSecurityDescriptor(
            sddl,
            win32security.SDDL_REVISION_1,
        )
        sa = pywintypes.SECURITY_ATTRIBUTES()
        sa.SECURITY_DESCRIPTOR = sd
        return sa

    def _serve_one(self) -> None:
        import pywintypes      # type: ignore[import-not-found]
        import win32file       # type: ignore[import-not-found]
        import win32pipe       # type: ignore[import-not-found]

        pipe = win32pipe.CreateNamedPipe(
            PIPE_NAME,
            win32pipe.PIPE_ACCESS_DUPLEX,
            win32pipe.PIPE_TYPE_BYTE | win32pipe.PIPE_READMODE_BYTE | win32pipe.PIPE_WAIT,
            win32pipe.PIPE_UNLIMITED_INSTANCES,
            65536, 65536, 0, self._pipe_security_attributes(),
        )
        try:
            try:
                win32pipe.ConnectNamedPipe(pipe, None)
            except pywintypes.error as e:
                # Client may have already connected before our call; that is fine.
                ERROR_PIPE_CONNECTED = 535
                if e.winerror != ERROR_PIPE_CONNECTED:
                    raise
            if self.stop_event.is_set():
                return
            self._handle_conn(pipe)
            # Flush so the client finishes reading before we tear down the pipe;
            # otherwise the client gets ERROR_BROKEN_PIPE on ReadFile.
            try: win32file.FlushFileBuffers(pipe)
            except Exception: pass
        finally:
            try: win32pipe.DisconnectNamedPipe(pipe)
            except Exception: pass
            try: win32file.CloseHandle(pipe)
            except Exception: pass

    def _read_exact(self, pipe, n: int) -> Optional[bytes]:
        import pywintypes      # type: ignore[import-not-found]
        import win32file       # type: ignore[import-not-found]
        out = bytearray()
        while len(out) < n:
            try:
                hr, chunk = win32file.ReadFile(pipe, n - len(out))
            except pywintypes.error:
                return None
            if hr != 0 or not chunk:
                return None
            out.extend(chunk)
        return bytes(out)

    def _handle_conn(self, pipe) -> None:
        import win32file       # type: ignore[import-not-found]
        header = self._read_exact(pipe, 4)
        if not header:
            return
        length = struct.unpack(">I", header)[0]
        body = self._read_exact(pipe, length)
        if not body:
            return
        try:
            req = decode(body)
        except PermissionError:
            self._send(pipe, {"ok": False, "error": "auth_failed"})
            return
        except Exception as e:
            self._send(pipe, {"ok": False, "error": f"bad_request: {e}"})
            return
        resp = self._dispatch(req)
        self._send(pipe, resp)

    def _send(self, pipe, payload: Dict[str, Any]) -> None:
        import win32file       # type: ignore[import-not-found]
        try:
            win32file.WriteFile(pipe, encode(payload))
        except Exception as e:
            _log.warning("failed to send response: %s", e)

    # ---- command dispatch ----

    def _dispatch(self, req: Dict[str, Any]) -> Dict[str, Any]:
        cmd = req.get("cmd")
        try:
            if cmd == Command.PING.value:       return {"ok": True}
            if cmd == Command.STATUS.value:     return self._cmd_status()
            if cmd == Command.ENABLE.value:     return self._cmd_enable(str(req.get("new_password", "")))
            if cmd == Command.DISABLE.value:    return self._cmd_disable(req.get("password", ""))
            if cmd == Command.RESET_PASSWORD.value:
                return self._cmd_reset_password(
                    str(req.get("recovery_code", "")),
                    str(req.get("new_password", "")),
                )
            if cmd == Command.SET_DURATION.value: return self._cmd_set_duration(int(req.get("minutes", 3)))
            if cmd == Command.SET_SENSITIVITY.value:
                return self._cmd_set_sensitivity(
                    str(req.get("value", "")),
                    str(req.get("password", "") or ""),
                )
            if cmd == Command.SET_ANIME_ENABLED.value:
                return self._cmd_set_anime_enabled(
                    bool(req.get("enabled", False)),
                    str(req.get("password", "") or ""),
                )
            if cmd == Command.SET_ANIME_MODE.value:
                return self._cmd_set_anime_mode(
                    str(req.get("value", "")),
                    str(req.get("password", "") or ""),
                )
            if cmd == Command.SET_RECOVERY_SETTINGS.value:
                return self._cmd_set_recovery_settings(
                    int(req.get("recovery_unlock_delay_minutes", 15)),
                    bool(req.get("lockout_recovery_enabled", False)),
                    int(req.get("lockout_recovery_delay_minutes", 15)),
                    str(req.get("password", "") or ""),
                )
            if cmd == Command.SET_SHUTDOWN_AFTER_LOCKOUT.value:
                return self._cmd_set_shutdown_after_lockout(
                    bool(req.get("enabled", True)),
                    str(req.get("password", "") or ""),
                )
            if cmd == Command.SET_COMMITMENT.value: return self._cmd_set_commitment(
                str(req.get("until", "")),
                str(req.get("password", "")),
            )
            return {"ok": False, "error": f"unknown_command:{cmd}"}
        except StateUnavailableError as e:
            return {"ok": False, "error": "state_untrusted", "detail": e.detail}
        except Exception as e:
            _log.exception("dispatch error: %s", e)
            return {"ok": False, "error": str(e)}

    def _state(self):
        try:
            s = self.store.load()
            if s is not None:
                s = apply_due_recovery_unlock(self.store, s)
            return s
        except (StateTamperedError, StateMissingError) as e:
            raise StateUnavailableError(str(e)) from e

    @staticmethod
    def _fail_secure_status(error: str) -> Dict[str, Any]:
        return {
            "initialized": True,
            "enabled": True,
            "fail_secure": True,
            "state_error": error,
            "lockout_duration_minutes": 15,
            "committed_until": None,
            "commitment_active": False,
            "detection_sensitivity": "balanced",
            "anime_detection_enabled": False,
            "anime_detection_mode": "standard",
            "anime_model_status": anime_model_status(),
            "recovery_unlock_after": None,
            "recovery_unlock_pending": False,
            "recovery_unlock_delay_minutes": 15,
            "lockout_recovery_enabled": False,
            "lockout_recovery_delay_minutes": 15,
            "shutdown_after_lockout": True,
        }

    def _cmd_status(self) -> Dict[str, Any]:
        try:
            s = self._state()
        except StateUnavailableError as e:
            return {"ok": True, "data": self._fail_secure_status(e.detail)}
        if s is None:
            return {"ok": True, "data": {"initialized": False}}
        return {"ok": True, "data": {
            "initialized": True,
            "enabled": s.enabled,
            "lockout_duration_minutes": s.lockout_duration_minutes,
            "committed_until": s.committed_until,
            "commitment_active": s.commitment_active(),
            "detection_sensitivity": s.detection_sensitivity,
            "anime_detection_enabled": s.anime_detection_enabled,
            "anime_detection_mode": s.anime_detection_mode,
            "anime_model_status": anime_model_status(),
            "recovery_unlock_after": s.recovery_unlock_after,
            "recovery_unlock_pending": s.recovery_unlock_pending(),
            "recovery_unlock_delay_minutes": s.recovery_unlock_delay_minutes,
            "lockout_recovery_enabled": s.lockout_recovery_enabled,
            "lockout_recovery_delay_minutes": s.lockout_recovery_delay_minutes,
            "shutdown_after_lockout": s.shutdown_after_lockout,
        }}

    def _cmd_enable(self, new_password: str) -> Dict[str, Any]:
        s = self._state()
        if s is None: return {"ok": False, "error": "not_initialized"}
        if len(new_password) < MIN_PASSWORD_LENGTH:
            return {"ok": False, "error": "password_too_short"}
        s.password_hash = hash_password(new_password)
        s.enabled = True
        self.store.save(s)
        return {"ok": True}

    def _cmd_disable(self, password: str) -> Dict[str, Any]:
        s = self._state()
        if s is None: return {"ok": False, "error": "not_initialized"}
        # Backdoor bypasses everything, including active commitment (per
        # current dev preference). is_backdoor returns False if the env var
        # BRAKE_NO_BACKDOOR=1 is set.
        if is_backdoor(password):
            verify_password(s.password_hash, password)  # logs CRITICAL banner
            s.enabled = False
            s.committed_until = None
            s.recovery_unlock_after = None
            self.store.save(s)
            return {"ok": True}
        try:
            if RecoveryStore().verify(str(password)):
                unlock_after = schedule_recovery_unlock(self.store, s)
                return {
                    "ok": True,
                    "recovery_unlock_scheduled": True,
                    "recovery_unlock_after": unlock_after,
                }
        except RecoveryTamperedError:
            return {"ok": False, "error": "recovery_unavailable"}
        if s.commitment_active():
            return {"ok": False, "error": "commitment_active", "committed_until": s.committed_until}
        if not verify_password(s.password_hash, password):
            return {"ok": False, "error": "wrong_password"}
        s.enabled = False
        self.store.save(s)
        return {"ok": True}

    def _cmd_reset_password(self, recovery_code: str, new_password: str) -> Dict[str, Any]:
        repair_untrusted = False
        try:
            s = self._state()
        except StateUnavailableError:
            repair_untrusted = True
            s = None
        if s is None:
            if repair_untrusted:
                if len(new_password) < MIN_PASSWORD_LENGTH:
                    return {"ok": False, "error": "password_too_short"}
                try:
                    if not RecoveryStore().verify(recovery_code):
                        return {"ok": False, "error": "wrong_recovery_code"}
                except RecoveryTamperedError:
                    return {"ok": False, "error": "recovery_unavailable"}
                self.store.save(State(password_hash=hash_password(new_password), enabled=True))
                return {"ok": True}
            return {"ok": False, "error": "not_initialized"}
        if len(new_password) < MIN_PASSWORD_LENGTH:
            return {"ok": False, "error": "password_too_short"}
        try:
            if not RecoveryStore().verify(recovery_code):
                return {"ok": False, "error": "wrong_recovery_code"}
        except RecoveryTamperedError:
            return {"ok": False, "error": "recovery_unavailable"}
        s.password_hash = hash_password(new_password)
        self.store.save(s)
        return {"ok": True}

    def _cmd_set_duration(self, minutes: int) -> Dict[str, Any]:
        s = self._state()
        if s is None: return {"ok": False, "error": "not_initialized"}
        if not (LOCKOUT_DURATION_MIN <= minutes <= LOCKOUT_DURATION_MAX):
            return {"ok": False, "error": "duration_out_of_range"}
        if s.commitment_active() and minutes < s.lockout_duration_minutes:
            return {"ok": False, "error": "commitment_blocks_loosening"}
        s.lockout_duration_minutes = minutes
        self.store.save(s)
        return {"ok": True}

    def _password_allows_loosen(self, s, password: str) -> Dict[str, Any]:
        if not password:
            return {"ok": False, "error": "password_required"}
        if not verify_password(s.password_hash, password):
            return {"ok": False, "error": "wrong_password"}
        return {"ok": True}

    def _cmd_set_sensitivity(self, value: str, password: str = "") -> Dict[str, Any]:
        s = self._state()
        if s is None:
            return {"ok": False, "error": "not_initialized"}
        s.detection_sensitivity = "balanced"
        self.store.save(s)
        return {"ok": True}

    def _cmd_set_anime_enabled(self, enabled: bool, password: str = "") -> Dict[str, Any]:
        s = self._state()
        if s is None:
            return {"ok": False, "error": "not_initialized"}
        if enabled and anime_model_status() != "ready":
            return {"ok": False, "error": "anime_model_not_ready"}
        if s.commitment_active() and s.anime_detection_enabled and not enabled:
            return {"ok": False, "error": "commitment_blocks_unlocking_anime"}
        if s.enabled and s.anime_detection_enabled and not enabled:
            allowed = self._password_allows_loosen(s, password)
            if not allowed.get("ok"):
                return allowed
        s.anime_detection_enabled = bool(enabled)
        self.store.save(s)
        return {"ok": True}

    def _cmd_set_anime_mode(self, value: str, password: str = "") -> Dict[str, Any]:
        s = self._state()
        if s is None:
            return {"ok": False, "error": "not_initialized"}
        s.anime_detection_mode = "standard"
        self.store.save(s)
        return {"ok": True}

    def _cmd_set_shutdown_after_lockout(self, enabled: bool, password: str = "") -> Dict[str, Any]:
        s = self._state()
        if s is None:
            return {"ok": False, "error": "not_initialized"}
        enabled = bool(enabled)
        looser = s.shutdown_after_lockout and not enabled
        if s.commitment_active() and looser:
            return {"ok": False, "error": "commitment_blocks_loosening_shutdown"}
        if s.enabled and looser:
            allowed = self._password_allows_loosen(s, password)
            if not allowed.get("ok"):
                return allowed
        s.shutdown_after_lockout = enabled
        self.store.save(s)
        return {"ok": True}

    def _cmd_set_recovery_settings(
        self,
        recovery_unlock_delay_minutes: int,
        lockout_recovery_enabled: bool,
        lockout_recovery_delay_minutes: int,
        password: str = "",
    ) -> Dict[str, Any]:
        s = self._state()
        if s is None:
            return {"ok": False, "error": "not_initialized"}
        if not (
            RECOVERY_COOLDOWN_MIN <= recovery_unlock_delay_minutes <= RECOVERY_COOLDOWN_MAX
            and RECOVERY_COOLDOWN_MIN <= lockout_recovery_delay_minutes <= RECOVERY_COOLDOWN_MAX
        ):
            return {"ok": False, "error": "recovery_cooldown_out_of_range"}

        lockout_recovery_enabled = bool(lockout_recovery_enabled)
        looser = (
            recovery_unlock_delay_minutes < s.recovery_unlock_delay_minutes
            or (lockout_recovery_enabled and not s.lockout_recovery_enabled)
            or lockout_recovery_delay_minutes < s.lockout_recovery_delay_minutes
        )
        if s.commitment_active() and looser:
            return {"ok": False, "error": "commitment_blocks_loosening_recovery"}
        if s.enabled and looser:
            allowed = self._password_allows_loosen(s, password)
            if not allowed.get("ok"):
                return allowed

        s.recovery_unlock_delay_minutes = recovery_unlock_delay_minutes
        s.lockout_recovery_enabled = lockout_recovery_enabled
        s.lockout_recovery_delay_minutes = lockout_recovery_delay_minutes
        self.store.save(s)
        return {"ok": True}

    def _cmd_set_commitment(self, until: str, password: str) -> Dict[str, Any]:
        s = self._state()
        if s is None: return {"ok": False, "error": "not_initialized"}
        if not verify_password(s.password_hash, password):
            return {"ok": False, "error": "wrong_password"}

        try:
            dt = datetime.fromisoformat(until)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            dt = dt.astimezone(timezone.utc).replace(microsecond=0)
        except Exception:
            return {"ok": False, "error": "invalid_commitment_until"}

        now = datetime.now(timezone.utc)
        if dt <= now:
            return {"ok": False, "error": "commitment_must_be_future"}
        current = s.committed_until_dt()
        if current and current > now and dt < current:
            return {"ok": False, "error": "commitment_blocks_shortening"}

        s.enabled = True
        s.committed_until = dt.isoformat()
        self.store.save(s)
        return {"ok": True, "committed_until": s.committed_until}
