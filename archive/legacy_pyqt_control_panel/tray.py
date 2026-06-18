"""System tray indicator + hide-to-tray window behavior.

Lives in the GUI process. Owns nothing - just reflects what the Controller
reports and lets the user pop the main window back open or quit.

Three icon states:
  - teal-accent Brake mark = protection enabled
  - dimmed Brake mark = disabled
  - amber-accent Brake mark = commitment locked

Closing the main window via the X HIDES it to the tray instead of quitting.
Quit goes through the tray menu so the user has to make a deliberate choice.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QObject, QTimer
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QApplication, QMainWindow, QMenu, QSystemTrayIcon

from brake.branding import APP_NAME
from brake.gui.assets import brake_icon, brake_icon_disabled
from brake.gui.controller import Controller


class BrakeTray(QObject):
    """Tray indicator + hide-on-close manager."""

    def __init__(self, window: QMainWindow, controller: Controller) -> None:
        super().__init__(window)
        self.window = window
        self.controller = controller

        # Cache icons; tray uses 16-32px so we ask for 32 and let Windows scale.
        self._icon_enabled = brake_icon("teal", 32)
        self._icon_disabled = brake_icon_disabled(32)
        self._icon_committed = brake_icon("amber", 32)

        self.tray = QSystemTrayIcon(self._icon_disabled, self)
        self.tray.setToolTip(APP_NAME)

        menu = QMenu()
        menu.setObjectName("TrayMenu")
        self._show_action = QAction(f"Show {APP_NAME}", self)
        self._show_action.triggered.connect(self._show_window)
        menu.addAction(self._show_action)
        menu.addSeparator()
        self._quit_action = QAction("Quit", self)
        self._quit_action.triggered.connect(self._quit_app)
        menu.addAction(self._quit_action)
        self.tray.setContextMenu(menu)

        self.tray.activated.connect(self._on_activated)
        self.tray.show()

        # Repaint icon based on live controller status.
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(2000)
        self._refresh_timer.timeout.connect(self.refresh)
        self._refresh_timer.start()
        self.refresh()

        # Intercept window close so X hides to tray instead of quitting.
        self._install_close_hook()

    # ---- public ----

    def refresh(self) -> None:
        try:
            st = self.controller.status()
        except Exception:
            return
        if not st.get("initialized"):
            self._set_state("disabled", f"{APP_NAME} - not initialized")
            return
        if bool(st.get("commitment_active")):
            self._set_state("committed", f"{APP_NAME} - committed (cannot disable)")
        elif bool(st.get("enabled")):
            self._set_state("enabled", f"{APP_NAME} - protection enabled")
        else:
            self._set_state("disabled", f"{APP_NAME} - protection disabled")

    # ---- internals ----

    def _set_state(self, name: str, tooltip: str) -> None:
        if name == "enabled":
            self.tray.setIcon(self._icon_enabled)
        elif name == "committed":
            self.tray.setIcon(self._icon_committed)
        else:
            self.tray.setIcon(self._icon_disabled)
        self.tray.setToolTip(tooltip)

    def _show_window(self) -> None:
        self.window.showNormal()
        self.window.raise_()
        self.window.activateWindow()

    def _quit_app(self) -> None:
        # Mark so the close hook lets the window close for real.
        self._allow_quit = True
        QApplication.instance().quit()

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:  # single left-click
            if self.window.isVisible():
                self.window.hide()
            else:
                self._show_window()

    def _install_close_hook(self) -> None:
        self._allow_quit = False
        original_close = self.window.closeEvent

        def hooked_close(event):
            if self._allow_quit:
                original_close(event)
                return
            event.ignore()
            self.window.hide()
            # First-time hint: many users will think closing the X quits.
            if not getattr(self, "_close_hint_shown", False):
                self._close_hint_shown = True
                self.tray.showMessage(
                    f"{APP_NAME} is still running",
                    "Protection keeps running in the background. "
                    "Use the tray icon to reopen or quit.",
                    QSystemTrayIcon.MessageIcon.Information,
                    4000,
                )
        self.window.closeEvent = hooked_close  # type: ignore[assignment]


def install_tray(window: QMainWindow, controller: Controller) -> Optional[BrakeTray]:
    """Convenience wrapper: only install if the system actually has a tray."""
    if not QSystemTrayIcon.isSystemTrayAvailable():
        return None
    return BrakeTray(window, controller)
