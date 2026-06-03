"""Modal password prompt used before any destructive action."""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from lockitup.branding import APP_NAME


class PasswordDialog(QDialog):
    def __init__(self, parent=None, prompt: str = "Enter your password.") -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} - password")
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        prompt_lbl = QLabel(prompt)
        prompt_lbl.setWordWrap(True)
        prompt_lbl.setObjectName("WizardIntro")
        layout.addWidget(prompt_lbl)

        self.pw = QLineEdit()
        self.pw.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.pw)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok_btn = buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok_btn is not None:
            ok_btn.setObjectName("PrimaryButton")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.pw.setFocus(Qt.FocusReason.OtherFocusReason)

    def value(self) -> str:
        return self.pw.text()


def ask_password(parent=None, prompt: str = "Enter your password.") -> Optional[str]:
    dlg = PasswordDialog(parent, prompt)
    if dlg.exec() == QDialog.DialogCode.Accepted:
        return dlg.value()
    return None
