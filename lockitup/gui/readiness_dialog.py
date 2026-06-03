"""First-run readiness dialog. Lists missing dependencies with copy-paste
install commands. Doesn't block dismissal so a power user can proceed.
"""
from __future__ import annotations

from typing import List

from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from lockitup.branding import APP_NAME
from lockitup.readiness import ReadinessIssue


class ReadinessDialog(QDialog):
    def __init__(self, issues: List[ReadinessIssue], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} - setup check")
        self.setMinimumWidth(640)

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(14)

        blockers = [i for i in issues if i.severity == "blocker"]
        warnings = [i for i in issues if i.severity == "warning"]

        head = QLabel()
        head.setObjectName("ReadinessHead")
        head.setWordWrap(True)
        if blockers:
            head.setText(
                f"{len(blockers)} required component"
                f"{'s' if len(blockers) != 1 else ''} missing. "
                "The app won't work until these are installed."
            )
        else:
            head.setText(
                f"{len(warnings)} optional feature"
                f"{'s' if len(warnings) != 1 else ''} unavailable. "
                "Protection still runs, but some detection won't."
            )
        root.addWidget(head)

        for issue in blockers + warnings:
            root.addLayout(self._issue_row(issue))

        hint = QLabel(
            f"Run the install command in a Command Prompt, then relaunch {APP_NAME}."
        )
        hint.setWordWrap(True)
        hint.setObjectName("BodyText")
        root.addWidget(hint)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        ok = QPushButton("Continue anyway")
        ok.setObjectName("PrimaryButton" if not blockers else "SecondaryButton")
        ok.clicked.connect(self.accept)
        button_row.addWidget(ok)
        root.addLayout(button_row)

    def _issue_row(self, issue: ReadinessIssue) -> QVBoxLayout:
        v = QVBoxLayout()
        v.setSpacing(4)

        title = QLabel(f"<b>{issue.name}</b> - {issue.message}")
        title.setWordWrap(True)
        title.setObjectName(
            "ReadinessIssueBlocker" if issue.severity == "blocker"
            else "ReadinessIssueWarning"
        )
        v.addWidget(title)

        cmd_row = QHBoxLayout()
        cmd_row.setSpacing(8)
        cmd = QLineEdit(issue.fix_command)
        cmd.setReadOnly(True)
        cmd_row.addWidget(cmd, 1)
        copy = QPushButton("Copy")
        copy.setObjectName("SecondaryButton")
        copy.setMinimumWidth(60)

        def on_copy() -> None:
            QGuiApplication.clipboard().setText(cmd.text())
            copy.setText("Copied")
        copy.clicked.connect(on_copy)
        cmd_row.addWidget(copy)
        v.addLayout(cmd_row)

        return v
