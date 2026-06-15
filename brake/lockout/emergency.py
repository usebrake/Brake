"""Emergency recovery-code release for an active lockout."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional, Tuple

from brake.lockout.persistence import LockoutPersistence, _TamperedLockoutError
from brake.state import StateMissingError, StateStore, StateTamperedError
from brake.state.recovery import RecoveryStore, RecoveryTamperedError

_log = logging.getLogger(__name__)

LOCKOUT_RECOVERY_MESSAGE = (
    "Emergency release pending. Protection stays on, but Windows will not "
    "shut down when this timer ends."
)


def lockout_recovery_available(store: Optional[StateStore] = None) -> bool:
    try:
        state = (store or StateStore()).load()
    except (StateMissingError, StateTamperedError) as e:
        _log.warning("Lockout recovery unavailable because state could not be trusted: %s", e)
        return False
    except Exception as e:
        _log.warning("Lockout recovery unavailable because state could not be read: %s", e)
        return False
    return bool(state and state.lockout_recovery_enabled)


def apply_lockout_recovery(
    recovery_code: str,
    *,
    store: Optional[StateStore] = None,
    recovery_store: Optional[RecoveryStore] = None,
    persistence: Optional[LockoutPersistence] = None,
) -> Tuple[bool, str, Optional[datetime]]:
    """Verify recovery code and replace the active lockout timer.

    Returns (ok, message_or_error, new_end_at).
    """
    try:
        state = (store or StateStore()).load()
    except (StateMissingError, StateTamperedError) as e:
        _log.warning("Lockout recovery rejected because state could not be trusted: %s", e)
        return False, "state_unavailable", None
    except Exception as e:
        _log.warning("Lockout recovery rejected because state could not be read: %s", e)
        return False, "state_unavailable", None

    if state is None:
        return False, "not_initialized", None
    if not state.lockout_recovery_enabled:
        return False, "lockout_recovery_disabled", None

    try:
        if not (recovery_store or RecoveryStore()).verify(recovery_code):
            return False, "wrong_recovery_code", None
    except RecoveryTamperedError:
        return False, "recovery_unavailable", None

    try:
        record = (persistence or LockoutPersistence()).replace_active(
            state.lockout_recovery_delay_seconds(),
            message=LOCKOUT_RECOVERY_MESSAGE,
            shutdown_on_done=False,
        )
    except _TamperedLockoutError:
        return False, "lockout_unavailable", None
    if record is None:
        return False, "no_active_lockout", None
    return True, LOCKOUT_RECOVERY_MESSAGE, record.end_dt()
