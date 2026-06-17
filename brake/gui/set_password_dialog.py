"""Modal 'set a new password' prompt used every time the user turns on
protection. The point is to make password reuse impossible: each session
picks a fresh password the user has to look at and type, which kills
the "I'll just type the one I memorized" relapse path.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)

from brake.branding import APP_NAME
from brake.gui.assets import brake_path
from brake.state.crypto import MIN_PASSWORD_LENGTH


class SetPasswordDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} - new password")
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        # Brand row.
        head_row = QHBoxLayout()
        head_row.setSpacing(14)
        logo = QLabel()
        pix = QPixmap(brake_path("base", 32)).scaled(
            40, 40,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        logo.setPixmap(pix)
        logo.setFixedSize(40, 40)
        head_row.addWidget(logo, 0, Qt.AlignmentFlag.AlignVCenter)
        title = QLabel("Pick a new password for this session.")
        title.setObjectName("RecoveryTitle")
        head_row.addWidget(title, 1, Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(head_row)

        explainer = QLabel(
            "Every time you turn on protection, you pick a new password. "
            "Past passwords no longer work. Pick something you'll remember "
            "for this session. You'll need it if you want to turn protection "
            "back off."
        )
        explainer.setWordWrap(True)
        explainer.setObjectName("WizardIntro")
        layout.addWidget(explainer)

        layout.addWidget(QLabel("New password"))
        self.pw = QLineEdit()
        self.pw.setEchoMode(QLineEdit.EchoMode.Normal)
        layout.addWidget(self.pw)

        layout.addWidget(QLabel("Confirm password"))
        self.pw_confirm = QLineEdit()
        self.pw_confirm.setEchoMode(QLineEdit.EchoMode.Normal)
        layout.addWidget(self.pw_confirm)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok_btn = buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok_btn is not None:
            ok_btn.setObjectName("PrimaryButton")
            ok_btn.setText("Set password")
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.pw.setFocus(Qt.FocusReason.OtherFocusReason)

    def _on_ok(self) -> None:
        a = self.pw.text()
        b = self.pw_confirm.text()
        if len(a) < MIN_PASSWORD_LENGTH:
            QMessageBox.warning(
                self, APP_NAME,
                f"Password must be at least {MIN_PASSWORD_LENGTH} characters.",
            )
            return
        if a != b:
            QMessageBox.warning(self, APP_NAME, "Passwords do not match.")
            return
        self.accept()

    def value(self) -> str:
        return self.pw.text()


def ask_new_password(parent=None) -> Optional[str]:
    dlg = SetPasswordDialog(parent)
    if dlg.exec() == QDialog.DialogCode.Accepted:
        return dlg.value()
    return None
