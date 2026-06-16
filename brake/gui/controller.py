"""Controller  -  single facade the GUI uses for read/write of protection state.

Behavior:
  - If BrakeService is running and responding on the IPC pipe, all writes
    go through IPC. The service is the only writer to state.json  -  this closes
    the "any local Python can flip enabled" bypass.
  - If the service is down (dev mode), falls back to direct StateStore access.
    Useful for `python -m brake.gui` without an install.

Reads (.status()) are cheap and try IPC first, fall back to StateStore.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from brake.detectors.anime_nsfw import anime_model_status
from brake.ipc.client import IPCClient, IPCError
from brake.state import State, StateMissingError, StateStore, StateTamperedError
from brake.state.crypto import MIN_PASSWORD_LENGTH, hash_password, is_backdoor, verify_password
from brake.state.recovery import RecoveryStore, RecoveryTamperedError
from brake.state.recovery_unlock import apply_due_recovery_unlock, schedule_recovery_unlock
from brake.state.schema import (
    RECOVERY_COOLDOWN_MAX,
    RECOVERY_COOLDOWN_MIN,
)

_log = logging.getLogger(__name__)

_PROBE_CACHE_SECONDS = 2.0  # how long to trust a previous ping() result


class Controller:
    def __init__(self, *, allow_direct_writes: bool = True, ipc_timeout_ms: int = 400) -> None:
        self.store = StateStore()
        self.ipc = IPCClient(timeout_ms=ipc_timeout_ms)
        self.allow_direct_writes = bool(allow_direct_writes)
        self._ipc_up: Optional[bool] = None
        self._ipc_checked_at: float = 0.0

    # ---- liveness ----

    def service_up(self) -> bool:
        now = time.monotonic()
        if self._ipc_up is None or (now - self._ipc_checked_at) > _PROBE_CACHE_SECONDS:
            self._ipc_up = self.ipc.ping()
            self._ipc_checked_at = now
        return bool(self._ipc_up)

    def _invalidate(self) -> None:
        self._ipc_up = None

    def _direct_write_unavailable(self) -> Tuple[bool, str]:
        if self.allow_direct_writes:
            return True, ""
        return False, "service_unavailable"

    # ---- reads ----

    def status(self) -> Dict[str, Any]:
        """Return the current protection, commitment, duration, and sensitivity state."""
        if self.service_up():
            try:
                resp = self.ipc.status()
                if resp.get("ok"):
                    data = resp.get("data") or {}
                    # service responded  -  use its view
                    return data
                if resp.get("error") == "state_untrusted":
                    return self._fail_secure_status(str(resp.get("detail", "") or "state_untrusted"))
                self._invalidate()
            except IPCError:
                self._invalidate()
        # fallback: read state.json directly
        try:
            s = self._load_state()
        except (StateTamperedError, StateMissingError) as e:
            return self._fail_secure_status(str(e))
        if s is None:
            return {"initialized": False}
        return self._status_from_state(s)

    def _load_state(self):
        s = self.store.load()
        if s is not None:
            s = apply_due_recovery_unlock(self.store, s)
        return s

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

    @staticmethod
    def _status_from_state(s) -> Dict[str, Any]:
        return {
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
        }

    @staticmethod
    def _recovery_code_matches(candidate: str) -> Tuple[bool, str]:
        try:
            if RecoveryStore().verify(candidate):
                return True, ""
            return False, "wrong_recovery_code"
        except RecoveryTamperedError:
            return False, "recovery_unavailable"

    # ---- writes ----

    def enable(self, new_password: str) -> Tuple[bool, str]:
        if self.service_up():
            try:
                r = self.ipc.enable(new_password)
                return bool(r.get("ok")), r.get("error", "")
            except IPCError:
                self._invalidate()
        ok, err = self._direct_write_unavailable()
        if not ok:
            return False, err
        s = self._load_state()
        if s is None: return False, "not_initialized"
        if len(new_password) < MIN_PASSWORD_LENGTH:
            return False, "password_too_short"
        s.password_hash = hash_password(new_password)
        s.enabled = True
        self.store.save(s)
        return True, ""

    def disable(self, password: str) -> Tuple[bool, str]:
        if self.service_up():
            try:
                r = self.ipc.disable(password)
                err = "recovery_unlock_scheduled" if r.get("recovery_unlock_scheduled") else r.get("error", "")
                return bool(r.get("ok")), err
            except IPCError:
                self._invalidate()
        ok, err = self._direct_write_unavailable()
        if not ok:
            return False, err
        s = self._load_state()
        if s is None: return False, "not_initialized"
        # Backdoor bypasses commitment too (current dev preference).
        if is_backdoor(password):
            verify_password(s.password_hash, password)  # logs CRITICAL banner
            s.enabled = False
            s.committed_until = None
            s.recovery_unlock_after = None
            self.store.save(s)
            return True, ""
        recovery_ok, recovery_err = self._recovery_code_matches(password)
        if recovery_ok:
            schedule_recovery_unlock(self.store, s)
            return True, "recovery_unlock_scheduled"
        if recovery_err != "wrong_recovery_code":
            return False, recovery_err
        if s.commitment_active():
            return False, "commitment_active"
        if not verify_password(s.password_hash, password):
            return False, "wrong_password"
        s.enabled = False
        self.store.save(s)
        return True, ""

    def reset_password_with_recovery(self, recovery_code: str, new_password: str) -> Tuple[bool, str]:
        if self.service_up():
            try:
                r = self.ipc.reset_password(recovery_code, new_password)
                return bool(r.get("ok")), r.get("error", "")
            except IPCError:
                self._invalidate()
        ok, err = self._direct_write_unavailable()
        if not ok:
            return False, err
        repair_untrusted = False
        try:
            s = self._load_state()
        except (StateTamperedError, StateMissingError):
            repair_untrusted = True
            s = None
        if s is None:
            if not repair_untrusted:
                return False, "not_initialized"
            if len(new_password) < MIN_PASSWORD_LENGTH:
                return False, "password_too_short"
            try:
                if not RecoveryStore().verify(recovery_code):
                    return False, "wrong_recovery_code"
            except RecoveryTamperedError:
                return False, "recovery_unavailable"
            self.store.save(State(password_hash=hash_password(new_password), enabled=True))
            return True, ""
        if len(new_password) < MIN_PASSWORD_LENGTH:
            return False, "password_too_short"
        try:
            if not RecoveryStore().verify(recovery_code):
                return False, "wrong_recovery_code"
        except RecoveryTamperedError:
            return False, "recovery_unavailable"
        s.password_hash = hash_password(new_password)
        self.store.save(s)
        return True, ""

    def set_duration(self, minutes: int) -> Tuple[bool, str]:
        if self.service_up():
            try:
                r = self.ipc.set_duration(minutes)
                return bool(r.get("ok")), r.get("error", "")
            except IPCError:
                self._invalidate()
        ok, err = self._direct_write_unavailable()
        if not ok:
            return False, err
        s = self._load_state()
        if s is None: return False, "not_initialized"
        if s.commitment_active() and int(minutes) < s.lockout_duration_minutes:
            return False, "commitment_blocks_loosening"
        s.lockout_duration_minutes = int(minutes)
        self.store.save(s)
        return True, ""

    def set_commitment(self, until: str, password: str) -> Tuple[bool, str]:
        if self.service_up():
            try:
                r = self.ipc.set_commitment(until, password)
                return bool(r.get("ok")), r.get("error", "")
            except IPCError:
                self._invalidate()
        ok, err = self._direct_write_unavailable()
        if not ok:
            return False, err
        s = self._load_state()
        if s is None: return False, "not_initialized"
        if not verify_password(s.password_hash, password):
            return False, "wrong_password"
        try:
            dt = datetime.fromisoformat(until)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            dt = dt.astimezone(timezone.utc).replace(microsecond=0)
        except Exception:
            return False, "invalid_commitment_until"
        now = datetime.now(timezone.utc)
        if dt <= now:
            return False, "commitment_must_be_future"
        current = s.committed_until_dt()
        if current and current > now and dt < current:
            return False, "commitment_blocks_shortening"
        s.enabled = True
        s.committed_until = dt.isoformat()
        self.store.save(s)
        return True, ""

    def _password_allows_loosen(self, s, password: str) -> Tuple[bool, str]:
        if not password:
            return False, "password_required"
        if not verify_password(s.password_hash, password):
            return False, "wrong_password"
        return True, ""

    def set_sensitivity(self, value: str, password: str = "") -> Tuple[bool, str]:
        if self.service_up():
            try:
                r = self.ipc.set_sensitivity(value, password=password)
                return bool(r.get("ok")), r.get("error", "")
            except IPCError:
                self._invalidate()
        ok, err = self._direct_write_unavailable()
        if not ok:
            return False, err
        s = self._load_state()
        if s is None:
            return False, "not_initialized"
        s.detection_sensitivity = "balanced"
        self.store.save(s)
        return True, ""

    def set_anime_enabled(self, enabled: bool, password: str = "") -> Tuple[bool, str]:
        if self.service_up():
            try:
                r = self.ipc.set_anime_enabled(enabled, password=password)
                return bool(r.get("ok")), r.get("error", "")
            except IPCError:
                self._invalidate()
        ok, err = self._direct_write_unavailable()
        if not ok:
            return False, err
        s = self._load_state()
        if s is None:
            return False, "not_initialized"
        if enabled and anime_model_status() != "ready":
            return False, "anime_model_not_ready"
        if s.commitment_active() and s.anime_detection_enabled and not enabled:
            return False, "commitment_blocks_unlocking_anime"
        if s.enabled and s.anime_detection_enabled and not enabled:
            ok, err = self._password_allows_loosen(s, password)
            if not ok:
                return False, err
        s.anime_detection_enabled = bool(enabled)
        self.store.save(s)
        return True, ""

    def set_anime_mode(self, value: str, password: str = "") -> Tuple[bool, str]:
        if self.service_up():
            try:
                r = self.ipc.set_anime_mode(value, password=password)
                return bool(r.get("ok")), r.get("error", "")
            except IPCError:
                self._invalidate()
        ok, err = self._direct_write_unavailable()
        if not ok:
            return False, err
        s = self._load_state()
        if s is None:
            return False, "not_initialized"
        s.anime_detection_mode = "standard"
        self.store.save(s)
        return True, ""

    def set_shutdown_after_lockout(self, enabled: bool, password: str = "") -> Tuple[bool, str]:
        if self.service_up():
            try:
                r = self.ipc.set_shutdown_after_lockout(enabled, password=password)
                return bool(r.get("ok")), r.get("error", "")
            except IPCError:
                self._invalidate()
        ok, err = self._direct_write_unavailable()
        if not ok:
            return False, err
        s = self._load_state()
        if s is None:
            return False, "not_initialized"
        enabled = bool(enabled)
        looser = s.shutdown_after_lockout and not enabled
        if s.commitment_active() and looser:
            return False, "commitment_blocks_loosening_shutdown"
        if s.enabled and looser:
            ok, err = self._password_allows_loosen(s, password)
            if not ok:
                return False, err
        s.shutdown_after_lockout = enabled
        self.store.save(s)
        return True, ""

    def set_recovery_settings(
        self,
        recovery_unlock_delay_minutes: int,
        lockout_recovery_enabled: bool,
        lockout_recovery_delay_minutes: int,
        password: str = "",
    ) -> Tuple[bool, str]:
        if self.service_up():
            try:
                r = self.ipc.set_recovery_settings(
                    recovery_unlock_delay_minutes,
                    lockout_recovery_enabled,
                    lockout_recovery_delay_minutes,
                    password=password,
                )
                return bool(r.get("ok")), r.get("error", "")
            except IPCError:
                self._invalidate()
        ok, err = self._direct_write_unavailable()
        if not ok:
            return False, err
        s = self._load_state()
        if s is None:
            return False, "not_initialized"
        recovery_unlock_delay_minutes = int(recovery_unlock_delay_minutes)
        lockout_recovery_delay_minutes = int(lockout_recovery_delay_minutes)
        if not (
            RECOVERY_COOLDOWN_MIN <= recovery_unlock_delay_minutes <= RECOVERY_COOLDOWN_MAX
            and RECOVERY_COOLDOWN_MIN <= lockout_recovery_delay_minutes <= RECOVERY_COOLDOWN_MAX
        ):
            return False, "recovery_cooldown_out_of_range"

        lockout_recovery_enabled = bool(lockout_recovery_enabled)
        looser = (
            recovery_unlock_delay_minutes < s.recovery_unlock_delay_minutes
            or (lockout_recovery_enabled and not s.lockout_recovery_enabled)
            or lockout_recovery_delay_minutes < s.lockout_recovery_delay_minutes
        )
        if s.commitment_active() and looser:
            return False, "commitment_blocks_loosening_recovery"
        if s.enabled and looser:
            ok, err = self._password_allows_loosen(s, password)
            if not ok:
                return False, err

        s.recovery_unlock_delay_minutes = recovery_unlock_delay_minutes
        s.lockout_recovery_enabled = lockout_recovery_enabled
        s.lockout_recovery_delay_minutes = lockout_recovery_delay_minutes
        self.store.save(s)
        return True, ""
