"""PyQt6 entrypoint. Routes first-run -> setup wizard, otherwise -> main window."""
from __future__ import annotations

import ctypes
import logging
import sys

from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import QApplication, QMessageBox

from brake.branding import APP_NAME, APP_USER_MODEL_ID, SINGLE_INSTANCE_SERVER
from brake.gui.assets import build_app_qicon, load_bundled_fonts
from brake.gui.theme import qss_path


# Windows groups taskbar entries by AppUserModelID. Without an explicit one,
# our process inherits python.exe's identity and the taskbar shows the
# Python snake icon. Setting our own AUMID makes Windows treat Brake as
# a distinct app and pick up our window icon for the taskbar entry.
# After PyInstaller packaging this is redundant (the .exe has its own
# embedded icon), but it costs nothing and fixes dev-mode.


def _set_windows_app_id() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except Exception as e:  # pragma: no cover � non-fatal cosmetic fix
        logging.getLogger(__name__).warning(
            "Could not set AppUserModelID (taskbar may show python icon): %s", e,
        )


def _notify_existing_instance() -> bool:
    """Return True if another GUI is already running and was asked to show."""
    socket = QLocalSocket()
    socket.connectToServer(SINGLE_INSTANCE_SERVER)
    if not socket.waitForConnected(250):
        socket.abort()
        return False
    socket.write(b"show\n")
    socket.flush()
    socket.waitForBytesWritten(250)
    socket.disconnectFromServer()
    return True


class _SingleInstanceServer:
    """Listens for second launches and asks this GUI to show itself."""

    def __init__(self) -> None:
        self._server = QLocalServer()
        self._show_callback = None
        self._pending_show = False
        self._server.newConnection.connect(self._on_new_connection)

    def listen(self) -> bool:
        if self._server.listen(SINGLE_INSTANCE_SERVER):
            return True

        # Stale socket/name from a crash. Removing is safe here because we
        # already tried to connect to a live instance before starting this.
        QLocalServer.removeServer(SINGLE_INSTANCE_SERVER)
        return self._server.listen(SINGLE_INSTANCE_SERVER)

    def set_show_callback(self, callback) -> None:
        self._show_callback = callback
        if self._pending_show:
            self._pending_show = False
            callback()

    def _on_new_connection(self) -> None:
        while self._server.hasPendingConnections():
            socket = self._server.nextPendingConnection()
            socket.disconnectFromServer()
        if self._show_callback is None:
            self._pending_show = True
        else:
            self._show_callback()


from brake.readiness import check_all, has_blockers
from brake.state import StateMissingError, StateStore, StateTamperedError
from brake.gui.controller import Controller
from brake.gui.main_window import MainWindow
from brake.gui.readiness_dialog import ReadinessDialog
from brake.gui.setup_wizard import SetupDialog
from brake.gui.tray import install_tray


def _load_stylesheet(app: QApplication) -> None:
    path = qss_path()
    if path.exists():
        app.setStyleSheet(path.read_text(encoding="utf-8"))


def run() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # Must run BEFORE QApplication is created.
    _set_windows_app_id()
    app = QApplication(sys.argv)
    if _notify_existing_instance():
        return 0
    single_instance = _SingleInstanceServer()
    if not single_instance.listen():
        logging.getLogger(__name__).warning(
            "Could not start GUI single-instance listener; duplicate windows may be possible."
        )
    app.setApplicationName(APP_NAME)
    # Sets the icon Windows shows in the taskbar, Alt+Tab list, Start Menu,
    # and the title bar of every window we create. We build a multi-size
    # QIcon from the high-res PNG instead of loading the .ico � Qt's smooth
    # scaler produces a sharper result than Windows' .ico renderer.
    app.setWindowIcon(build_app_qicon())
    # Must run BEFORE _load_stylesheet so QSS font-family rules can resolve.
    load_bundled_fonts()
    # Don't auto-quit when the main window closes - the tray icon should
    # keep the GUI process alive so users can pop it back open.
    app.setQuitOnLastWindowClosed(False)
    _load_stylesheet(app)

    # Readiness check FIRST - if Pillow / NudeNet / pywin32 are missing, we
    # can't even load the setup wizard's downstream code reliably. Show the
    # missing-deps dialog so the user knows what to install.
    issues = check_all()
    if issues:
        dlg = ReadinessDialog(issues)
        dlg.exec()
        if has_blockers(issues):
            # Blockers mean detection won't work. Let the user dismiss and
            # still open the GUI (to see status / regenerate recovery /
            # etc.), but log loudly.
            logging.critical(
                "Starting GUI with %d unresolved blocker(s); detection will not work until they're installed.",
                sum(1 for i in issues if i.severity == "blocker"),
            )

    store = StateStore()

    # bootstrap: setup wizard writes the initial state DIRECTLY to the file
    # because there's nothing for the service to manage yet.
    try:
        state = store.load()
    except StateTamperedError as e:
        QMessageBox.critical(
            None,
            f"{APP_NAME} - state corrupted",
            f"The state file failed integrity verification:\n\n{e}\n\n"
            "In production the service would trigger a lockout. For dev, "
            "delete state.json + state.key in your data dir to start fresh.",
        )
        return 2
    except StateMissingError as e:
        QMessageBox.critical(
            None,
            f"{APP_NAME} - bypass attempt detected",
            str(e),
        )
        return 3

    if state is None:
        wizard = SetupDialog(store)
        if wizard.exec() != SetupDialog.DialogCode.Accepted:
            return 0  # user cancelled
        state = store.load()
        assert state is not None

    # After bootstrap, all reads/writes go through Controller (IPC w/ fallback).
    controller = Controller()
    window = MainWindow(controller)

    def show_window() -> None:
        window.showNormal()
        window.raise_()
        window.activateWindow()

    single_instance.set_show_callback(show_window)
    window.show()

    # Tray icon. Keeps process alive when the main window is hidden; only
    # the tray's "Quit" action actually exits.
    install_tray(window, controller)

    return app.exec()
