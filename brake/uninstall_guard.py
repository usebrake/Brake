"""Uninstall gate.

Uninstall is free only when protection is disabled and Commitment Mode is not
active. If protection is enabled without commitment, the user must enter the
normal password before uninstalling. The emergency recovery code starts the
delayed emergency unlock instead of authorizing uninstall immediately.

When Commitment Mode is active, uninstall is blocked until the delayed
emergency unlock has matured. The normal password is intentionally not
accepted because commitment mode promises that the password cannot turn
protection off.

Exit codes (read by installer/unregister_service.ps1):
  0  = uninstall is allowed (no install present, protection disabled with no
       active commitment, OR password verified)
  1  = uninstall blocked (user cancelled or kept typing wrong values)
  2  = state is tampered or unreadable, fail-secure, block uninstall

Invoked as:
    python -m brake.uninstall_guard

Always runs as a separate process so it can be called from the elevated
installer script without dragging the whole service environment along.
"""
from __future__ import annotations

import logging
import sys
from typing import Optional

from brake.branding import APP_NAME
from brake.state import StateStore, StateTamperedError
from brake.state.crypto import is_backdoor, verify_password
from brake.state.recovery import RecoveryStore, RecoveryTamperedError
from brake.state.recovery_unlock import apply_due_recovery_unlock, schedule_recovery_unlock

_log = logging.getLogger(__name__)


MAX_ATTEMPTS = 3


def _prompt_dialog(prompt: str) -> Optional[str]:
    """Show a Qt password dialog. Returns the typed string or None on cancel."""
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    _ = app  # keep reference alive
    from brake.gui.password_dialog import ask_password
    return ask_password(None, prompt)


def _block_with_dialog(message: str) -> None:
    """Show a blocking warning before exiting. Best-effort, no app context."""
    try:
        from PyQt6.QtWidgets import QApplication, QMessageBox
        app = QApplication.instance() or QApplication(sys.argv)
        _ = app
        QMessageBox.warning(None, f"{APP_NAME} - uninstall blocked", message)
    except Exception:
        # GUI failed, fall back to console.
        print(f"[{APP_NAME}] {message}", file=sys.stderr)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    store = StateStore()

    try:
        state = apply_due_recovery_unlock(store)
    except StateTamperedError as e:
        _log.critical("State file is tampered (%s), refusing uninstall.", e)
        _block_with_dialog(
            f"{APP_NAME}'s state file failed integrity verification. "
            "Uninstall is refused as a safety measure. If you believe this "
            "is a real install, contact support or delete the data directory "
            "manually with administrator rights."
        )
        return 2

    if state is None:
        return 0

    if not state.enabled and not state.commitment_active():
        # Protection is already off and no commitment is active, so uninstall
        # is not a bypass.
        return 0

    commitment_active = state.commitment_active()
    if commitment_active:
        prompt = (
            f"Commitment Mode is active. To uninstall {APP_NAME}, enter your "
            "emergency recovery code:"
        )
    else:
        prompt = (
            f"Protection is enabled. To uninstall {APP_NAME}, enter your "
            "password or emergency recovery code:"
        )

    for attempt in range(1, MAX_ATTEMPTS + 1):
        typed = _prompt_dialog(prompt)
        if typed is None:
            _log.warning("User cancelled uninstall prompt.")
            return 1
        if is_backdoor(typed):
            _log.warning("Uninstall authorized (attempt %d).", attempt)
            return 0
        try:
            if RecoveryStore().verify(typed):
                unlock_after = schedule_recovery_unlock(store, state)
                _log.warning("Recovery uninstall requested; emergency unlock scheduled for %s.", unlock_after)
                _block_with_dialog(
                    "Emergency recovery accepted. For safety, Brake will not uninstall immediately. "
                    "Protection will turn off after the 15-minute recovery cooldown. "
                    "Run uninstall again after that cooldown finishes."
                )
                return 1
        except RecoveryTamperedError:
            _log.critical("Recovery file tampered, refusing uninstall.")
            return 2
        if not commitment_active and verify_password(state.password_hash, typed):
            _log.warning("Uninstall authorized (attempt %d).", attempt)
            return 0
        _log.warning("Uninstall auth failed (attempt %d/%d).", attempt, MAX_ATTEMPTS)
        if commitment_active:
            prompt = (
                f"Wrong recovery code. Attempt {attempt}/{MAX_ATTEMPTS}. "
                "Enter emergency recovery code:"
            )
        else:
            prompt = (
                f"Wrong password or recovery code. Attempt {attempt}/{MAX_ATTEMPTS}. "
                "Enter password or emergency recovery code:"
            )

    _block_with_dialog(
        f"Too many failed attempts ({MAX_ATTEMPTS}). Uninstall cancelled. "
        "Disable protection first, start the emergency recovery cooldown, or "
        "wait until the commitment ends."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
