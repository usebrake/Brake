"""Main controller window: enable / disable + lockout duration setting.

State is read/written through gui.controller.Controller, which uses IPC to
the service when it is up, and falls back to direct StateStore for dev runs.

This file owns presentation only. Protection, detection, commitment, recovery,
and lockout behavior live outside the UI layer.
"""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from lockitup.branding import APP_NAME, APP_TAGLINE
from lockitup.gui.assets import _faded, brake_pixmap  # type: ignore[attr-defined]
from lockitup.gui.commitment_dialog import CommitmentDialog
from lockitup.gui.controller import Controller
from lockitup.gui.password_dialog import ask_password
from lockitup.gui.recovery_dialog import RecoveryDialog
from lockitup.gui.set_password_dialog import ask_new_password
from lockitup.state.recovery import RecoveryStore
from lockitup.state.schema import LOCKOUT_DURATION_MAX, LOCKOUT_DURATION_MIN, SENSITIVITY_RANK


_ERROR_MESSAGES = {
    "wrong_password": "That password didn't match.",
    "duration_out_of_range": "Lockout duration must be between 1 and 60 minutes.",
    "commitment_active": "Commitment is active. Protection cannot be turned off until it ends.",
    "commitment_blocks_loosening": "Commitment is active. You can only make protection stricter.",
    "commitment_blocks_shortening": "Commitment is active. You can extend it, but not shorten it.",
    "commitment_must_be_future": "Commitment must end in the future.",
    "invalid_commitment_until": "That commitment end time isn't valid.",
    "not_initialized": "Setup hasn't finished yet.",
    "password_too_short": "Password is too short.",
    "commitment_blocks_loosening_sensitivity":
        "Commitment is active. You can only make sensitivity stricter.",
    "invalid_sensitivity": "That sensitivity setting is not recognized.",
}


def _err_text(code: str) -> str:
    return _ERROR_MESSAGES.get(code, code or "Something went wrong.")


def _format_until(iso_value: str | None) -> str:
    if not iso_value:
        return ""
    try:
        dt = datetime.fromisoformat(iso_value)
        return dt.astimezone().strftime("%b %#d, %Y at %#I:%M %p")
    except Exception:
        return iso_value


STATUS_MARK_SIZE = 56


class MainWindow(QMainWindow):
    def __init__(self, controller: Controller) -> None:
        super().__init__()
        self.controller = controller
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(880, 620)
        self.resize(920, 640)
        self._suppress_spin_signal = False
        self._suppress_sensitivity_signal = False

        central = QWidget()
        central.setObjectName("AppRoot")
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(24, 20, 24, 0)
        root.setSpacing(14)
        root.addWidget(self._build_header())

        self.tabs = QTabWidget()
        self.tabs.setObjectName("MainTabs")
        self.tabs.addTab(self._build_overview(), "Overview")
        self.tabs.addTab(self._build_advanced(), "Detection")
        root.addWidget(self.tabs, 1)

        root.addWidget(self._build_divider())
        root.addWidget(self._build_button_bar())

        for btn in self.findChildren(QPushButton):
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._refresh()
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._refresh)
        self._timer.start()

        QTimer.singleShot(0, self._ensure_recovery_token_shown)

    # ---------- shared builders ----------

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("HeaderBar")
        row = QHBoxLayout(header)
        row.setContentsMargins(0, 0, 0, 4)
        row.setSpacing(12)

        mark = QLabel()
        mark.setObjectName("HeaderMark")
        mark.setFixedSize(32, 32)
        mark.setPixmap(brake_pixmap("base", 32))
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(mark, 0, Qt.AlignmentFlag.AlignTop)

        text = QVBoxLayout()
        text.setContentsMargins(0, 0, 0, 0)
        text.setSpacing(1)
        title = QLabel(APP_NAME)
        title.setObjectName("AppTitle")
        text.addWidget(title)
        subtitle = QLabel(APP_TAGLINE)
        subtitle.setObjectName("AppSubtitle")
        text.addWidget(subtitle)
        row.addLayout(text, 1)
        return header

    def _build_page_head(self, title_text: str, subtitle_text: str) -> QWidget:
        wrap = QWidget()
        layout = QVBoxLayout(wrap)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        title = QLabel(title_text)
        title.setObjectName("PageTitle")
        layout.addWidget(title)
        subtitle = QLabel(subtitle_text)
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
        return wrap

    def _card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("Card")
        return card

    def _card_head(self, title_text: str, subtitle_text: str = "", icon_text: str = "") -> QFrame:
        head = QFrame()
        head.setObjectName("CardHeader")
        row = QHBoxLayout(head)
        row.setContentsMargins(18, 14, 18, 14)
        row.setSpacing(12)

        if icon_text:
            lead = QFrame()
            lead.setObjectName("LeadIcon")
            lead.setFixedSize(30, 30)
            lead_layout = QHBoxLayout(lead)
            lead_layout.setContentsMargins(0, 0, 0, 0)
            icon = QLabel(icon_text)
            icon.setObjectName("LeadIconText")
            icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lead_layout.addWidget(icon)
            row.addWidget(lead, 0, Qt.AlignmentFlag.AlignVCenter)

        text = QVBoxLayout()
        text.setContentsMargins(0, 0, 0, 0)
        text.setSpacing(2)
        title = QLabel(title_text)
        title.setObjectName("CardTitle")
        text.addWidget(title)
        if subtitle_text:
            subtitle = QLabel(subtitle_text)
            subtitle.setObjectName("CardSubtitle")
            subtitle.setWordWrap(True)
            text.addWidget(subtitle)
        row.addLayout(text, 1)
        return head

    def _settings_row(self, title_text: str, description: str, value_widget: QWidget | QHBoxLayout) -> QFrame:
        row_frame = QFrame()
        row_frame.setObjectName("SettingsRow")
        row = QHBoxLayout(row_frame)
        row.setContentsMargins(18, 14, 18, 14)
        row.setSpacing(16)

        text = QVBoxLayout()
        text.setContentsMargins(0, 0, 0, 0)
        text.setSpacing(3)
        title = QLabel(title_text)
        title.setObjectName("RowTitle")
        text.addWidget(title)
        if description:
            desc = QLabel(description)
            desc.setObjectName("RowDescription")
            desc.setWordWrap(True)
            text.addWidget(desc)
        row.addLayout(text, 1)

        if isinstance(value_widget, QWidget):
            row.addWidget(value_widget, 0, Qt.AlignmentFlag.AlignVCenter)
        else:
            row.addLayout(value_widget)
        return row_frame

    def _build_divider(self) -> QFrame:
        line = QFrame()
        line.setObjectName("Divider")
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFixedHeight(1)
        return line

    # ---------- overview ----------

    def _build_overview(self) -> QWidget:
        page = QWidget()
        page.setObjectName("TabPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 18, 0, 0)
        layout.setSpacing(14)

        layout.addWidget(self._build_page_head(
            "Overview",
            "Brake runs quietly on your computer and steps in only when it needs to.",
        ))
        layout.addWidget(self._build_status_module())

        cards = QHBoxLayout()
        cards.setContentsMargins(0, 0, 0, 0)
        cards.setSpacing(14)
        cards.addWidget(self._build_controls_card(), 1)
        cards.addWidget(self._build_how_it_helps_card(), 1)
        layout.addLayout(cards)
        layout.addStretch(1)
        return page

    def _build_status_module(self) -> QFrame:
        module = QFrame()
        module.setObjectName("StatusModule")
        self.status_module = module
        outer = QHBoxLayout(module)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        rail = QFrame()
        rail.setObjectName("StatusRail")
        rail.setFixedWidth(3)
        self.status_rail = rail
        outer.addWidget(rail)

        inner = QWidget()
        outer.addWidget(inner, 1)
        row = QHBoxLayout(inner)
        row.setContentsMargins(20, 20, 20, 20)
        row.setSpacing(18)

        self.status_logo = QLabel()
        self.status_logo.setFixedSize(STATUS_MARK_SIZE, STATUS_MARK_SIZE)
        self.status_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._set_status_logo("teal")
        row.addWidget(self.status_logo, 0, Qt.AlignmentFlag.AlignVCenter)

        text_col = QVBoxLayout()
        text_col.setSpacing(4)
        text_col.setContentsMargins(0, 0, 0, 0)

        self.status_big = QLabel("")
        self.status_big.setObjectName("StatusStateLabel")
        text_col.addWidget(self.status_big)

        self.status_headline = QLabel("")
        self.status_headline.setObjectName("StatusHeadline")
        text_col.addWidget(self.status_headline)

        self.status_sub = QLabel("")
        self.status_sub.setObjectName("StatusSubLine")
        self.status_sub.setWordWrap(True)
        text_col.addWidget(self.status_sub)

        row.addLayout(text_col, 1)

        self.status_badge = QLabel("")
        self.status_badge.setObjectName("StatusBadge")
        self.status_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(self.status_badge, 0, Qt.AlignmentFlag.AlignTop)
        return module

    def _build_controls_card(self) -> QFrame:
        card = self._card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._card_head(
            "Session controls",
            "Set the friction Brake uses when protection is running.",
            "II",
        ))
        layout.addWidget(self._settings_row(
            "Commitment",
            "Lock protection in so your password cannot turn it off early.",
            self._make_commitment_value(),
        ))
        layout.addWidget(self._settings_row(
            "Lockout length",
            "How long Brake keeps the screen locked after explicit content is detected.",
            self._make_duration_control(),
        ))
        return card

    def _build_how_it_helps_card(self) -> QFrame:
        card = self._card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._card_head(
            "How Brake helps",
            "A quiet pause between impulse and action.",
            "?",
        ))

        local = QLabel(
            "It works entirely on your computer. Nothing is uploaded, recorded, or sent anywhere."
        )
        local.setObjectName("BodyText")
        local.setWordWrap(True)
        layout.addWidget(self._settings_row("Private by default", "", local))

        action = QLabel(
            "Clear explicit content triggers a lockout. Incidental nudity is handled more gently."
        )
        action.setObjectName("BodyText")
        action.setWordWrap(True)
        layout.addWidget(self._settings_row("Calm but serious", "", action))
        return card

    def _set_status_logo(self, tone: str) -> None:
        if tone == "gray":
            pix = _faded(brake_pixmap("base", STATUS_MARK_SIZE), 0.45)
        else:
            pix = brake_pixmap(tone, STATUS_MARK_SIZE)
        self.status_logo.setPixmap(pix)

    def _make_commitment_value(self) -> QLabel:
        self.commitment_status = QLabel("")
        self.commitment_status.setObjectName("CommitmentInline")
        self.commitment_status.setWordWrap(True)
        return self.commitment_status

    def _make_duration_control(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        self.dur_spin = QSpinBox()
        self.dur_spin.setRange(LOCKOUT_DURATION_MIN, LOCKOUT_DURATION_MAX)
        self.dur_spin.setSuffix(" min")
        self.dur_spin.setFixedWidth(118)
        self.dur_spin.valueChanged.connect(self._on_duration_changed)
        row.addWidget(self.dur_spin, 0, Qt.AlignmentFlag.AlignRight)
        return row

    # ---------- detection ----------

    def _build_advanced(self) -> QWidget:
        page = QWidget()
        page.setObjectName("TabPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 18, 0, 0)
        layout.setSpacing(14)

        layout.addWidget(self._build_page_head(
            "Detection",
            "Tune how sensitive Brake is and test the lockout without changing the protection logic.",
        ))
        layout.addWidget(self._build_sensitivity_card())
        layout.addWidget(self._build_tools_card())
        layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setObjectName("TabPage")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(page)
        return scroll

    def _build_sensitivity_card(self) -> QFrame:
        card = self._card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._card_head(
            "Sensitivity",
            "How readily Brake treats screen content as explicit.",
            "S",
        ))

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(18, 14, 18, 18)
        body_layout.setSpacing(12)

        self.sensitivity_group = QButtonGroup(self)
        self.sensitivity_group.setExclusive(True)
        self.sensitivity_radios: dict[str, QRadioButton] = {}

        options = [
            (
                "light",
                "Light",
                "Only clear explicit content triggers a lockout. Lowest false-positive rate.",
            ),
            (
                "balanced",
                "Balanced",
                "Best for most people. Gives incidental nudity a short warning pause first.",
            ),
            (
                "strict",
                "Strict",
                "Requires two matching scans, then uses warning pauses that grow if it keeps happening.",
            ),
        ]

        for idx, (value, label, description) in enumerate(options):
            option = QWidget()
            option_layout = QVBoxLayout(option)
            option_layout.setContentsMargins(0, 0, 0, 0)
            option_layout.setSpacing(4)

            radio = QRadioButton(label)
            radio.setProperty("sensitivity", value)
            radio.toggled.connect(self._on_sensitivity_toggled)
            self.sensitivity_group.addButton(radio, idx)
            self.sensitivity_radios[value] = radio
            option_layout.addWidget(radio)

            desc = QLabel(description)
            desc.setObjectName("BodyText")
            desc.setWordWrap(True)
            option_layout.addWidget(desc)
            body_layout.addWidget(option)

        layout.addWidget(body)
        return card

    def _build_tools_card(self) -> QFrame:
        card = self._card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._card_head(
            "Tools",
            "Run a short local test to verify the lockout screen.",
            "T",
        ))

        row = QHBoxLayout()
        row.setContentsMargins(18, 16, 18, 18)
        row.setSpacing(10)
        self.test_btn = QPushButton("Test lockout (10s)")
        self.test_btn.setObjectName("SecondaryButton")
        self.test_btn.clicked.connect(self._on_test_lockout)
        row.addWidget(self.test_btn)
        row.addStretch(1)
        layout.addLayout(row)
        return card

    # ---------- bottom button bar ----------

    def _build_button_bar(self) -> QWidget:
        wrap = QWidget()
        wrap.setObjectName("BottomBar")
        row = QHBoxLayout(wrap)
        row.setContentsMargins(0, 16, 0, 20)
        row.setSpacing(12)

        self.toggle_btn = QPushButton()
        self.toggle_btn.setObjectName("PrimaryButton")
        self.toggle_btn.setMinimumHeight(38)
        self.toggle_btn.clicked.connect(self._on_toggle)
        row.addWidget(self.toggle_btn)

        self.commit_btn = QPushButton("Lock in commitment")
        self.commit_btn.setObjectName("AccentButton")
        self.commit_btn.setMinimumHeight(38)
        self.commit_btn.clicked.connect(self._on_commit)
        row.addWidget(self.commit_btn)

        row.addStretch(1)

        self.info_btn = QPushButton("How this works")
        self.info_btn.setObjectName("SubtleButton")
        self.info_btn.clicked.connect(self._on_more_info)
        row.addWidget(self.info_btn)
        return wrap

    # ---------- refresh ----------

    def _refresh(self) -> None:
        st = self.controller.status()
        if not st.get("initialized"):
            self.status_big.setText("NOT INITIALIZED")
            self.status_headline.setText("Setup has not finished")
            self.status_sub.setText("")
            self.status_badge.setText("Needs setup")
            return

        enabled = bool(st.get("enabled"))
        duration = int(st.get("lockout_duration_minutes", 3))
        commitment_active = bool(st.get("commitment_active", False))
        committed_until = st.get("committed_until")
        sensitivity = str(st.get("detection_sensitivity", "balanced"))

        if commitment_active:
            visual_state = "committed"
            self._set_status_logo("amber")
            self.status_big.setText("COMMITTED")
            self.status_headline.setText("Commitment active")
            self.status_sub.setText(
                f"Locked in until {_format_until(committed_until)}. "
                "Password cannot turn this off."
            )
            self.status_badge.setText("Locked in")
        elif enabled:
            visual_state = "enabled"
            self._set_status_logo("teal")
            self.status_big.setText("PROTECTED")
            self.status_headline.setText("You're covered")
            self.status_sub.setText("Brake is watching your screen. Local only.")
            self.status_badge.setText("Active")
        else:
            visual_state = "disabled"
            self._set_status_logo("gray")
            self.status_big.setText("OFF")
            self.status_headline.setText("Protection is off")
            self.status_sub.setText("Brake is not watching right now.")
            self.status_badge.setText("Idle")

        for widget in (self.status_module, self.status_rail, self.status_big, self.status_badge):
            widget.setProperty("state", visual_state)
            widget.style().unpolish(widget)
            widget.style().polish(widget)

        self.toggle_btn.setText("Turn off protection" if enabled else "Turn on protection")
        if commitment_active:
            self.toggle_btn.setToolTip("Commitment is active. Password cannot disable protection.")
        else:
            self.toggle_btn.setToolTip("")

        if commitment_active:
            self.commitment_status.setObjectName("CommitmentInlineActive")
            self.commitment_status.setText(f"Locked in until {_format_until(committed_until)}")
        else:
            self.commitment_status.setObjectName("CommitmentInline")
            self.commitment_status.setText("No commitment set")
        self.commitment_status.style().unpolish(self.commitment_status)
        self.commitment_status.style().polish(self.commitment_status)

        self._suppress_spin_signal = True
        self.dur_spin.setValue(duration)
        self._suppress_spin_signal = False

        self._refresh_sensitivity_radios(sensitivity, commitment_active)

    def _refresh_sensitivity_radios(self, sensitivity: str, commitment_active: bool) -> None:
        if sensitivity not in self.sensitivity_radios:
            sensitivity = "balanced"
        self._suppress_sensitivity_signal = True
        for value, radio in self.sensitivity_radios.items():
            radio.setChecked(value == sensitivity)
            if commitment_active and SENSITIVITY_RANK[value] < SENSITIVITY_RANK[sensitivity]:
                radio.setEnabled(False)
                radio.setToolTip("Commitment is active. Sensitivity can only be stiffened.")
            else:
                radio.setEnabled(True)
                radio.setToolTip("")
        self._suppress_sensitivity_signal = False

    # ---------- actions ----------

    def _on_duration_changed(self, value: int) -> None:
        if self._suppress_spin_signal:
            return
        ok, err = self.controller.set_duration(int(value))
        if not ok:
            QMessageBox.warning(self, APP_NAME, _err_text(err))
            self._refresh()

    def _on_sensitivity_toggled(self, checked: bool) -> None:
        if self._suppress_sensitivity_signal or not checked:
            return
        radio = self.sender()
        if not isinstance(radio, QRadioButton):
            return
        value = str(radio.property("sensitivity") or "")
        ok, err = self.controller.set_sensitivity(value)
        if not ok:
            QMessageBox.warning(self, APP_NAME, _err_text(err))
            self._refresh()
            return
        self._refresh()

    def _on_toggle(self) -> None:
        st = self.controller.status()
        enabled = bool(st.get("enabled"))
        duration = int(st.get("lockout_duration_minutes", 3))

        if not enabled:
            confirm = QMessageBox.question(
                self,
                "Turn on protection",
                f"Turn on {APP_NAME} now?<br><br>"
                f"You'll set a <b>new password</b> for this session. Past passwords "
                f"no longer work.<br><br>"
                f"Explicit content triggers a <b>{duration}-minute</b> lockout, "
                "then Windows shuts down. After restart, a five-minute strict watch "
                "kicks in. Incidental nudity gets a short warning first.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return
            new_pw = ask_new_password(self)
            if new_pw is None:
                return
            ok, err = self.controller.enable(new_pw)
            if not ok:
                QMessageBox.warning(self, APP_NAME, _err_text(err))
            self._refresh()
            return

        pw = ask_password(self, "Enter your password to turn off protection.")
        if pw is None:
            return
        ok, err = self.controller.disable(pw)
        if not ok:
            QMessageBox.warning(self, APP_NAME, _err_text(err))
        elif err == "recovery_unlock_scheduled":
            QMessageBox.information(
                self,
                APP_NAME,
                "Recovery code accepted. For safety, protection will turn off "
                "after a 10-minute emergency cooldown.",
            )
        self._refresh()

    def _on_commit(self) -> None:
        dlg = CommitmentDialog(self)
        if dlg.exec() != CommitmentDialog.DialogCode.Accepted:
            return
        until = dlg.committed_until().isoformat()
        ok, err = self.controller.set_commitment(until, dlg.password_value())
        if not ok:
            QMessageBox.warning(self, APP_NAME, _err_text(err))
            self._refresh()
            return
        QMessageBox.information(
            self,
            "Commitment locked in",
            f"Protection is locked in until {_format_until(until)}. "
            "Until then, your password cannot turn it off.",
        )
        self._refresh()

    def _on_more_info(self) -> None:
        QMessageBox.information(
            self,
            f"How {APP_NAME} responds",
            "Detection runs locally on your screen. Nothing leaves your machine.\n\n"
            "Hard explicit content triggers your full lockout. When the lockout "
            "ends, Windows shuts down. After restart, a five-minute strict watch "
            "starts. Reopening explicit content during that window triggers a "
            "longer lockout.\n\n"
            "Partial nudity uses your sensitivity setting:\n\n"
            "Light ignores partial nudity.\n"
            "Balanced gives one short warning pause, then cools down for 60 seconds.\n"
            "Strict requires two matching scans, then uses warning pauses that grow "
            "from 30 seconds to 60 seconds to 2 minutes.\n\n"
            "Partial nudity never causes shutdown. Illustrated explicit content is "
            "checked by a second local detector."
        )

    def _on_test_lockout(self) -> None:
        subprocess.Popen(
            [sys.executable, "-m", "lockitup.lockout",
             "--duration", "10", "--reason", "TEST", "--no-persist"],
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
        )

    # ---------- recovery token ----------

    def _ensure_recovery_token_shown(self) -> None:
        store = RecoveryStore()
        if store.exists():
            return
        try:
            token = store.generate()
        except Exception as e:
            QMessageBox.warning(
                self, APP_NAME,
                f"Could not generate a recovery code: {e}\n\n"
                "Restart the app to try again.",
            )
            return
        RecoveryDialog(token, self).exec()
