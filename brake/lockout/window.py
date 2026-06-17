"""Fullscreen black lockout overlay with a centered countdown.

One window per connected monitor. Frameless, always-on-top, swallows
Alt+F4 / close attempts (we re-show ourselves). Countdown is monotonic.
"""
from __future__ import annotations

import logging
import os
import sys

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QGuiApplication, QKeyEvent
from PyQt6.QtWidgets import QApplication, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from brake.gui.assets import lock_pixmap_teal_large
from brake.lockout.countdown import Countdown
from brake.lockout.input_block import KeyboardBlocker

_log = logging.getLogger(__name__)


class _LockoutWindow(QWidget):
    def __init__(
        self,
        geometry,
        reason: str,
        message: str,
        is_primary: bool,
        countdown: Countdown,
        recovery_enabled: bool = False,
        on_recovery_submit=None,
    ) -> None:
        super().__init__()
        self.countdown = countdown
        self.is_primary = is_primary
        self.on_recovery_submit = on_recovery_submit

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool  # no taskbar entry
        )
        # Bypass Aero peek / animations
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        # Warm-tinted charcoal background instead of pure black — matches
        # the rest of the app's palette so the lockout feels like the same
        # product, not a separate panic screen.
        self.setStyleSheet("background-color: #0b0e14;")
        self.setGeometry(geometry)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(28)

        if is_primary:
            # Pixel teal lock instead of the old red "Brake" text.
            # The visual is the brand — calm and unmistakable, not alarming.
            self.logo = QLabel()
            self.logo.setPixmap(lock_pixmap_teal_large(160))
            self.logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(self.logo)

            # Note: we intentionally do NOT display the trigger reason on
            # the lockout screen — naming the specific label (e.g.
            # "FEMALE_GENITALIA_EXPOSED") would surface explicit text in
            # a public/embarrassing context. The reason is still passed
            # in for logging.
            _log.info("Lockout window built (reason=%s, hidden from UI).", reason)

            self.message_lbl = QLabel(message)
            self.message_lbl.setStyleSheet(
                "color: #ffb454; font-size: 18px; font-weight: 500;"
                "font-family: 'Geist', 'Segoe UI', sans-serif;"
            )
            self.message_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.message_lbl.setWordWrap(True)
            self.message_lbl.setMaximumWidth(900)
            self.message_lbl.setVisible(bool(message))
            layout.addWidget(self.message_lbl)

            self.timer_lbl = QLabel("--:--")
            self.timer_lbl.setStyleSheet(
                "color: #f3f0e6; font-size: 120px; font-weight: 400;"
                "font-family: 'Geist Mono', 'Cascadia Mono', 'Consolas', monospace;"
                "letter-spacing: 2px;"
            )
            self.timer_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(self.timer_lbl)

            self.footer = QLabel("This window closes automatically.")
            self.footer.setStyleSheet(
                "color: #8f96a3; font-size: 12px;"
                "font-family: 'Geist', 'Segoe UI', sans-serif;"
            )
            self.footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(self.footer)

            if recovery_enabled and on_recovery_submit:
                self.recovery_btn = QPushButton("Emergency")
                self.recovery_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                self.recovery_btn.setStyleSheet(
                    "QPushButton { color: #5b626f; background: transparent; "
                    "border: 1px solid rgba(243, 240, 230, 0.08); "
                    "border-radius: 6px; padding: 5px 10px; font-size: 11px; "
                    "font-family: 'Geist', 'Segoe UI', sans-serif; }"
                    "QPushButton:hover { color: #8f96a3; border-color: rgba(243, 240, 230, 0.16); }"
                )
                self.recovery_btn.clicked.connect(self._show_recovery_form)
                layout.addWidget(self.recovery_btn, alignment=Qt.AlignmentFlag.AlignCenter)

                self.recovery_panel = QWidget()
                panel_layout = QVBoxLayout(self.recovery_panel)
                panel_layout.setContentsMargins(0, 0, 0, 0)
                panel_layout.setSpacing(8)

                self.recovery_status = QLabel("")
                self.recovery_status.setStyleSheet(
                    "color: #8f96a3; font-size: 12px; "
                    "font-family: 'Geist', 'Segoe UI', sans-serif;"
                )
                self.recovery_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.recovery_status.setWordWrap(True)
                self.recovery_status.setMaximumWidth(520)
                panel_layout.addWidget(self.recovery_status)

                self.recovery_code = QLineEdit()
                self.recovery_code.setEchoMode(QLineEdit.EchoMode.Normal)
                self.recovery_code.setPlaceholderText("Recovery code")
                self.recovery_code.setFixedWidth(320)
                self.recovery_code.setStyleSheet(
                    "QLineEdit { color: #f3f0e6; background: #12161f; "
                    "border: 1px solid rgba(243, 240, 230, 0.16); "
                    "border-radius: 6px; padding: 8px 10px; font-size: 13px; }"
                    "QLineEdit:focus { border-color: rgba(230, 205, 155, 0.42); }"
                )
                self.recovery_code.returnPressed.connect(self._submit_recovery)
                panel_layout.addWidget(self.recovery_code, alignment=Qt.AlignmentFlag.AlignCenter)

                actions = QHBoxLayout()
                actions.setSpacing(8)
                self.recovery_cancel = QPushButton("Cancel")
                self.recovery_submit = QPushButton("Submit")
                for btn in (self.recovery_cancel, self.recovery_submit):
                    btn.setCursor(Qt.CursorShape.PointingHandCursor)
                    btn.setStyleSheet(
                        "QPushButton { color: #c2c6cf; background: #181d28; "
                        "border: 1px solid rgba(243, 240, 230, 0.16); "
                        "border-radius: 6px; padding: 7px 12px; font-size: 12px; }"
                        "QPushButton:hover { color: #f3f0e6; background: #212736; }"
                    )
                self.recovery_cancel.clicked.connect(self._hide_recovery_form)
                self.recovery_submit.clicked.connect(self._submit_recovery)
                actions.addWidget(self.recovery_cancel)
                actions.addWidget(self.recovery_submit)
                panel_layout.addLayout(actions)

                self.recovery_panel.hide()
                layout.addWidget(self.recovery_panel, alignment=Qt.AlignmentFlag.AlignCenter)

    def _show_recovery_form(self) -> None:
        self.recovery_btn.hide()
        self.recovery_panel.show()
        self.recovery_status.setText("Enter your recovery code to start emergency release.")
        self.recovery_code.setFocus()

    def _hide_recovery_form(self) -> None:
        self.recovery_code.clear()
        self.recovery_panel.hide()
        self.recovery_btn.show()

    def _submit_recovery(self) -> None:
        code = self.recovery_code.text().strip()
        if not code:
            self.recovery_status.setText("Enter your recovery code.")
            return
        if not self.on_recovery_submit:
            self.recovery_status.setText("Emergency release is unavailable.")
            return
        ok, message, new_end_at = self.on_recovery_submit(code)
        if not ok:
            self.recovery_status.setText(_human_recovery_error(message))
            self.recovery_code.selectAll()
            self.recovery_code.setFocus()
            return
        if new_end_at is not None:
            self.countdown.set_end_at(new_end_at)
        self.message_lbl.setText(message)
        self.message_lbl.setVisible(True)
        self.recovery_code.clear()
        self.recovery_code.setEnabled(False)
        self.recovery_submit.setEnabled(False)
        self.recovery_cancel.hide()
        self.recovery_status.setText("Emergency release pending.")

    # Swallow Alt+F4 / Esc / anything that asks us to close early.
    def closeEvent(self, event):
        if not self.countdown.is_done():
            event.ignore()
            self.showFullScreen()
            self.raise_()
            self.activateWindow()
        else:
            event.accept()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        # belt-and-suspenders: Qt-level swallow even if kbd hook missed
        event.ignore()


class LockoutApp:
    def __init__(
        self,
        countdown: Countdown,
        reason: str,
        message: str = "",
        on_done=None,
        recovery_enabled: bool = False,
        on_recovery_submit=None,
    ) -> None:
        self.countdown = countdown
        self.reason = reason
        self.message = message
        self.on_done = on_done  # called once when countdown naturally expires
        self.recovery_enabled = bool(recovery_enabled)
        self.on_recovery_submit = on_recovery_submit
        self.windows: list[_LockoutWindow] = []
        self._blocker: KeyboardBlocker | None = None

    def run(self) -> int:
        app = QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(False)

        screens = QGuiApplication.screens()
        primary_screen = QGuiApplication.primaryScreen()
        for screen in screens:
            geom = screen.geometry()
            win = _LockoutWindow(
                geom, self.reason, self.message, is_primary=(screen is primary_screen),
                countdown=self.countdown,
                recovery_enabled=self.recovery_enabled,
                on_recovery_submit=self.on_recovery_submit,
            )
            self.windows.append(win)
            win.showFullScreen()
            win.raise_()

        # belt-and-suspenders kbd hook (Win+Tab+F4 etc.)
        if os.environ.get("BRAKE_NO_KBD_HOOK", "0") != "1":
            try:
                self._blocker = KeyboardBlocker()
                self._blocker.install()
            except Exception as e:
                _log.warning("Keyboard hook failed (lockout still active): %s", e)

        self.countdown.start()

        timer = QTimer()
        timer.setInterval(250)

        def tick() -> None:
            remaining = self.countdown.remaining()
            for w in self.windows:
                if w.is_primary:
                    w.timer_lbl.setText(Countdown.format_mmss(remaining))
            if self.countdown.is_done():
                if self._blocker:
                    self._blocker.uninstall()
                for w in self.windows:
                    w.close()
                if self.on_done:
                    try:
                        self.on_done()
                    except Exception as e:
                        _log.exception("on_done callback raised: %s", e)
                QApplication.quit()

        timer.timeout.connect(tick)
        timer.start()

        return app.exec()


def _human_recovery_error(error: str) -> str:
    return {
        "wrong_recovery_code": "That recovery code is not correct.",
        "recovery_unavailable": "Recovery code verification is unavailable.",
        "lockout_recovery_disabled": "Emergency release is not enabled for lockouts.",
        "no_active_lockout": "This lockout is no longer active.",
        "lockout_unavailable": "The lockout record could not be updated.",
        "state_unavailable": "Brake settings could not be verified.",
        "not_initialized": "Brake has not been set up yet.",
    }.get(error, "Emergency release failed.")
