"""First-run setup. Pick a starter password and save the initial State.

After this dialog closes, the main window opens and the recovery dialog
appears so the user can save their emergency code.
"""
from __future__ import annotations

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
from brake.state import State, StateStore
from brake.state.crypto import hash_password

MIN_PASSWORD_LEN = 6


class SetupDialog(QDialog):
    def __init__(self, store: StateStore) -> None:
        super().__init__()
        self.store = store
        self.setWindowTitle(f"{APP_NAME} - first-run setup")
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
        title = QLabel("Set your starter password.")
        title.setObjectName("RecoveryTitle")
        head_row.addWidget(title, 1, Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(head_row)

        intro = QLabel(
            "Every time you turn on protection, you'll set a new password for "
            "that session. This first one is just to finish setup.\n\n"
            "After this, you'll see a one-time emergency recovery code. "
            "Write it down offline, take a photo on your phone, give it to "
            "someone you trust, or choose not to copy it if you want the "
            "strongest commitment."
        )
        intro.setWordWrap(True)
        intro.setObjectName("WizardIntro")
        layout.addWidget(intro)

        layout.addWidget(QLabel("Password"))
        self.pw = QLineEdit()
        self.pw.setEchoMode(QLineEdit.EchoMode.Normal)
        layout.addWidget(self.pw)

        layout.addWidget(QLabel("Confirm password"))
        self.pw2 = QLineEdit()
        self.pw2.setEchoMode(QLineEdit.EchoMode.Normal)
        layout.addWidget(self.pw2)

        self.error = QLabel("")
        self.error.setObjectName("WizardError")
        layout.addWidget(self.error)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok_btn = buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok_btn is not None:
            ok_btn.setObjectName("PrimaryButton")
            ok_btn.setText("Finish setup")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.pw.setFocus(Qt.FocusReason.OtherFocusReason)

    def _on_accept(self) -> None:
        pw = self.pw.text()
        pw2 = self.pw2.text()
        if len(pw) < MIN_PASSWORD_LEN:
            self.error.setText(f"Password must be at least {MIN_PASSWORD_LEN} characters.")
            return
        if pw != pw2:
            self.error.setText("Passwords do not match.")
            return

        state = State(password_hash=hash_password(pw), enabled=False)
        self.store.save(state)
        QMessageBox.information(
            self,
            "Setup complete",
            "Password saved. Protection is currently OFF. "
            "Turn it on from the main window when you're ready.",
        )
        self.accept()
