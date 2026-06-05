"""First-run state bootstrap helpers."""
from __future__ import annotations

import secrets

from brake.state.crypto import hash_password
from brake.state.schema import State
from brake.state.store import StateStore


def ensure_first_run_state(store: StateStore | None = None) -> bool:
    """Create the initial disabled state for a true fresh install.

    This intentionally bootstraps only when both state.json and state.key are
    absent. If the key exists without state, StateStore still raises the
    deletion-bypass guard.
    """
    store = store or StateStore()
    if store.exists():
        return False
    store.check_no_deletion_bypass()
    placeholder_password = secrets.token_urlsafe(32)
    store.save(State(password_hash=hash_password(placeholder_password), enabled=False))
    return True
