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
from PyQt6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from lockitup.gui.assets import lock_pixmap_teal_large
from lockitup.lockout.countdown import Countdown
from lockitup.lockout.input_block import KeyboardBlocker

_log = logging.getLogger(__name__)


class _LockoutWindow(QWidget):
    def __init__(self, geometry, reason: str, message: str, is_primary: bool, countdown: Countdown) -> None:
        super().__init__()
        self.countdown = countdown
        self.is_primary = is_primary

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
            # Pixel teal lock instead of the old red "LockItUp" text.
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

            if message:
                self.message_lbl = QLabel(message)
                self.message_lbl.setStyleSheet(
                    "color: #ffb454; font-size: 18px; font-weight: 500;"
                    "font-family: 'Geist', 'Segoe UI', sans-serif;"
                )
                self.message_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.message_lbl.setWordWrap(True)
                self.message_lbl.setMaximumWidth(900)
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
    def __init__(self, countdown: Countdown, reason: str, message: str = "", on_done=None) -> None:
        self.countdown = countdown
        self.reason = reason
        self.message = message
        self.on_done = on_done  # called once when countdown naturally expires
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
            )
            self.windows.append(win)
            win.showFullScreen()
            win.raise_()

        # belt-and-suspenders kbd hook (Win+Tab+F4 etc.)
        if os.environ.get("LOCKITUP_NO_KBD_HOOK", "0") != "1":
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
