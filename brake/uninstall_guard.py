"""Uninstall gate.

Windows uninstall is allowed only when protection is already disabled and
Commitment Mode is not active. The uninstaller must never be a shortcut around
Brake's own controls: if protection is on, the user has to open Brake and turn
it off first; if commitment is active, they have to wait or use the recovery
cooldown inside Brake.

Exit codes (read by the Inno uninstaller):
  0  = uninstall is allowed
  1  = uninstall blocked because protection or commitment is active
  2  = state is tampered or unreadable, fail-secure, block uninstall

Invoked as:
    BrakeUninstallGuard.exe
    python -m brake.uninstall_guard
"""
from __future__ import annotations

import logging
import sys

from brake.branding import APP_NAME
from brake.state import StateStore, StateTamperedError
from brake.state.recovery_unlock import apply_due_recovery_unlock

_log = logging.getLogger(__name__)


def _block_with_dialog(message: str) -> None:
    """Show a blocking warning before exiting. Best-effort, no app context."""
    try:
        from PyQt6.QtWidgets import QApplication, QMessageBox

        app = QApplication.instance() or QApplication(sys.argv)
        _ = app
        QMessageBox.warning(None, f"{APP_NAME} - uninstall blocked", message)
    except Exception:
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
            "Uninstall is refused as a safety measure."
        )
        return 2

    if state is None:
        return 0

    if not state.enabled and not state.commitment_active():
        return 0

    if state.commitment_active():
        _log.warning("Uninstall blocked because commitment is active.")
        _block_with_dialog(
            f"{APP_NAME} cannot be uninstalled while a commitment is active. "
            "Wait until the commitment ends, or use your recovery code inside "
            f"{APP_NAME} and run uninstall again after the cooldown finishes."
        )
    else:
        _log.warning("Uninstall blocked because protection is enabled.")
        _block_with_dialog(
            f"{APP_NAME} cannot be uninstalled while protection is on. "
            f"Open {APP_NAME}, turn protection off, then run uninstall again."
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
