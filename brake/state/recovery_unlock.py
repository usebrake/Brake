"""Delayed emergency unlock flow for recovery-code use.

The recovery code is powerful enough to end protection and commitment, but not
instantly. When it is used for emergency disable, we store a signed wall-clock
timestamp. Once that timestamp is due, the service/agent clears protection.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from brake.state.schema import State
from brake.state.store import StateStore

RECOVERY_UNLOCK_DELAY_SECONDS = 15 * 60


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def schedule_recovery_unlock(
    store: StateStore,
    state: State,
    delay_seconds: Optional[int] = None,
) -> str:
    """Schedule emergency disable and return the unlock timestamp."""
    now = datetime.now(timezone.utc)
    current = state.recovery_unlock_after_dt()
    if current and current > now:
        return _iso(current)

    if delay_seconds is None:
        delay_seconds = state.recovery_unlock_delay_seconds()
    unlock_after = now + timedelta(seconds=max(1, int(delay_seconds)))
    state.recovery_unlock_after = _iso(unlock_after)
    store.save(state)
    return state.recovery_unlock_after


def apply_due_recovery_unlock(store: StateStore, state: Optional[State] = None) -> Optional[State]:
    """Apply a matured emergency unlock, if one exists."""
    s = state if state is not None else store.load()
    if s is None:
        return None

    if s.recovery_unlock_due():
        s.enabled = False
        s.committed_until = None
        s.recovery_unlock_after = None
        store.save(s)
    return s
