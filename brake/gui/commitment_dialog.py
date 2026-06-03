"""Commitment mode dialog. Locks protection on for a fixed window."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
)

from brake.branding import APP_NAME
from brake.gui.assets import brake_path


class CommitmentDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} - commitment")
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        # Brand row: amber lock to match the commitment color.
        head_row = QHBoxLayout()
        head_row.setSpacing(14)
        logo = QLabel()
        pix = QPixmap(brake_path("amber", 32)).scaled(
            40, 40,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        logo.setPixmap(pix)
        logo.setFixedSize(40, 40)
        head_row.addWidget(logo, 0, Qt.AlignmentFlag.AlignVCenter)
        title = QLabel("Lock in a commitment.")
        title.setObjectName("RecoveryTitle")
        head_row.addWidget(title, 1, Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(head_row)

        intro = QLabel(
            "While a commitment is active, your password cannot turn off "
            "protection. You can still make settings stricter, but not "
            "looser. The emergency recovery code can start a 10-minute "
            "cooldown before protection turns off."
        )
        intro.setWordWrap(True)
        intro.setObjectName("WizardIntro")
        layout.addWidget(intro)

        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(QLabel("Lock in for"))
        self.amount = QSpinBox()
        self.amount.setRange(1, 365)
        self.amount.setValue(3)
        self.amount.setFixedWidth(80)
        row.addWidget(self.amount)
        self.unit = QComboBox()
        self.unit.addItems(["days", "hours"])
        row.addWidget(self.unit)
        row.addStretch(1)
        layout.addLayout(row)

        layout.addWidget(QLabel("Password"))
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.password)

        self.error = QLabel("")
        self.error.setObjectName("WizardError")
        layout.addWidget(self.error)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok_btn = buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok_btn is not None:
            ok_btn.setObjectName("PrimaryButton")
            ok_btn.setText("Lock it in")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.password.setFocus(Qt.FocusReason.OtherFocusReason)

    def _accept(self) -> None:
        if not self.password.text():
            self.error.setText("Enter your password.")
            return
        self.accept()

    def committed_until(self) -> datetime:
        amount = int(self.amount.value())
        if self.unit.currentText() == "hours":
            delta = timedelta(hours=amount)
        else:
            delta = timedelta(days=amount)
        return (datetime.now(timezone.utc) + delta).replace(microsecond=0)

    def password_value(self) -> str:
        return self.password.text()
