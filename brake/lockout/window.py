"""Fullscreen lockout overlay: calm landscape, current clock, unlock time.

One window per connected monitor. Frameless, always-on-top, swallows
Alt+F4 / close attempts (we re-show ourselves). The primary monitor also
shows the remaining time, an info button with the incident message, and a
power menu (sleep, shut down, restart, and emergency release when recovery
is enabled).

Icons are drawn with QPainter and the background is a PNG on purpose: the
packaged build strips Qt's SVG and JPEG plugins (packaging/build_pyinstaller.ps1).
"""
from __future__ import annotations

import ctypes
import logging
import math
import os
import subprocess
import sys
from datetime import datetime, timedelta

from PyQt6.QtCore import QLineF, QPointF, QRectF, QSize, Qt, QTimer
from PyQt6.QtGui import (
    QColor,
    QFont,
    QGuiApplication,
    QIcon,
    QImage,
    QKeyEvent,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
)
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from brake.gui.assets import asset_path
from brake.lockout.countdown import Countdown
from brake.lockout.input_block import KeyboardBlocker

_log = logging.getLogger(__name__)

BACKGROUND_FILE = "lockout_background.png"
FALLBACK_SKY = QColor("#d5d9e2")
FALLBACK_MID = QColor("#8fa6c2")
FALLBACK_GROUND = QColor("#23344a")

# Text over the pale sky (top) is deep navy; text over the dark ridges
# (bottom) is soft white.
NAVY = "#1c2940"
NAVY_QCOLOR = QColor(28, 41, 64)
NAVY_SOFT_QCOLOR = QColor(28, 41, 64, 200)
WHITE_SOFT = "rgba(244, 246, 250, 0.9)"
UI_FONT = "'Segoe UI Variable Text', 'Segoe UI', sans-serif"
CLOCK_FAMILIES = ["Segoe UI Variable Display", "Segoe UI Light", "Segoe UI"]
TEXT_FAMILIES = ["Segoe UI Variable Text", "Segoe UI"]
PANEL_BG = "rgba(24, 33, 48, 0.92)"
PANEL_BORDER = "rgba(255, 255, 255, 0.09)"


def _draw_icon(painter: QPainter, name: str) -> None:
    """Draw a line icon on a 24x24 grid with the painter's current pen."""
    if name == "lock":
        painter.drawRoundedRect(QRectF(5, 10.5, 14, 10.5), 2.2, 2.2)
        shackle = QPainterPath(QPointF(8, 10.5))
        shackle.lineTo(8, 7.5)
        shackle.arcTo(QRectF(8, 3.5, 8, 8), 180, -180)
        shackle.lineTo(16, 10.5)
        painter.drawPath(shackle)
        painter.drawLine(QLineF(12, 14.6, 12, 17))
    elif name == "power":
        painter.drawLine(QLineF(12, 3, 12, 11))
        ring = QRectF(4, 5, 16, 16)
        arc = QPainterPath()
        arc.arcMoveTo(ring, 125)
        arc.arcTo(ring, 125, 290)
        painter.drawPath(arc)
    elif name == "sleep":
        moon = QPainterPath()
        moon.addEllipse(QPointF(11.5, 12.5), 8, 8)
        bite = QPainterPath()
        bite.addEllipse(QPointF(16.8, 7.2), 6.3, 6.3)
        painter.drawPath(moon.subtracted(bite))
    elif name == "restart":
        ring = QRectF(4, 4, 16, 16)
        arc = QPainterPath()
        arc.arcMoveTo(ring, 0)
        arc.arcTo(ring, 0, -315)
        painter.drawPath(arc)
        painter.drawPolyline(QPolygonF([QPointF(20, 4), QPointF(20, 8.4), QPointF(15.6, 8.4)]))
    elif name == "info":
        painter.drawEllipse(QPointF(12, 12), 8.5, 8.5)
        painter.drawLine(QLineF(12, 11, 12, 16.2))
        painter.drawLine(QLineF(12, 7.9, 12, 8.0))
    elif name == "emergency":
        painter.drawPolygon(QPolygonF([QPointF(12, 3.8), QPointF(21, 19.5), QPointF(3, 19.5)]))
        painter.drawLine(QLineF(12, 10, 12, 14.2))
        painter.drawLine(QLineF(12, 17.1, 12, 17.2))


def _icon_pixmap(name: str, size: int, color: str, stroke: float = 1.7) -> QPixmap:
    """Render one of the line icons above at `size` logical px."""
    screen = QGuiApplication.primaryScreen()
    dpr = screen.devicePixelRatio() if screen else 1.0
    px = max(1, int(round(size * dpr)))
    image = QImage(px, px, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(px / 24.0, px / 24.0)
    pen = QPen(QColor(color))
    pen.setWidthF(stroke)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    _draw_icon(painter, name)
    painter.end()
    pixmap = QPixmap.fromImage(image)
    pixmap.setDevicePixelRatio(dpr)
    return pixmap


def _format_clock(now: datetime) -> str:
    """Current time, always 24-hour, so no AM/PM suffix unbalances the clock."""
    return now.strftime("%H:%M")


def _format_short_time(moment: datetime) -> str:
    return moment.strftime("%H:%M")


def format_unlocks_at(now: datetime, end: datetime) -> str:
    # Round up so "Unlocks at" never shows a minute that has already passed.
    if end.second or end.microsecond:
        end = end.replace(second=0, microsecond=0) + timedelta(minutes=1)
    days = (end.date() - now.date()).days
    when = _format_short_time(end)
    if days <= 0:
        return f"Unlocks at {when}"
    if days == 1:
        return f"Unlocks tomorrow at {when}"
    return f"Unlocks {end.strftime('%A')} at {when}"


def format_remaining(seconds: float) -> str:
    total = max(0, int(math.ceil(seconds)))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours} h {minutes} min left"
    if minutes:
        return f"{minutes} min {secs} s left"
    return f"{secs} s left"


class _PowerMenu(QFrame):
    """Compact panel above the power button, styled like the Windows menu."""

    def __init__(self, parent: QWidget, show_emergency: bool, on_action) -> None:
        super().__init__(parent)
        self.setObjectName("powerMenu")
        self.setStyleSheet(
            f"#powerMenu {{ background: {PANEL_BG}; "
            f"border: 1px solid {PANEL_BORDER}; border-radius: 12px; }}"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(2)

        for key, label in (("sleep", "Sleep"), ("shutdown", "Shut down"), ("restart", "Restart")):
            icon = "power" if key == "shutdown" else key
            layout.addWidget(
                self._item(icon, label, True, lambda _=False, k=key: on_action(k))
            )

        if show_emergency:
            divider = QFrame()
            divider.setObjectName("menuDivider")
            divider.setFixedHeight(1)
            divider.setStyleSheet("#menuDivider { background: rgba(255, 255, 255, 0.1); }")
            wrap = QHBoxLayout()
            wrap.setContentsMargins(10, 4, 10, 4)
            wrap.addWidget(divider)
            layout.addLayout(wrap)
            layout.addWidget(
                self._item("emergency", "Emergency", False, lambda _=False: on_action("emergency"))
            )
        self.setFixedWidth(max(self.sizeHint().width(), 200))
        self.adjustSize()
        self.hide()

    @staticmethod
    def _item(icon: str, label: str, bright: bool, handler) -> QPushButton:
        btn = QPushButton(f"  {label}")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        color = WHITE_SOFT if bright else "rgba(244, 246, 250, 0.5)"
        btn.setIcon(QIcon(_icon_pixmap(icon, 18, "#f4f6fa" if bright else "#8e97a6")))
        btn.setIconSize(QSize(18, 18))
        btn.setStyleSheet(
            f"QPushButton {{ color: {color}; background: transparent; border: none; "
            f"border-radius: 8px; padding: 9px 14px; font-size: 14px; font-family: {UI_FONT}; "
            "text-align: left; }"
            "QPushButton:hover { background: rgba(255, 255, 255, 0.08); }"
            "QPushButton:pressed { background: rgba(255, 255, 255, 0.12); }"
        )
        btn.clicked.connect(handler)
        return btn


class _LockoutWindow(QWidget):
    def __init__(
        self,
        geometry,
        reason: str,
        message: str,
        is_primary: bool,
        countdown: Countdown,
        background: QPixmap | None = None,
        recovery_enabled: bool = False,
        on_recovery_submit=None,
    ) -> None:
        super().__init__()
        self.countdown = countdown
        self.is_primary = is_primary
        self.on_recovery_submit = on_recovery_submit
        self._background = background
        self._scaled_bg: QPixmap | None = None
        self._clock_px = 120

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool  # no taskbar entry
        )
        # Bypass Aero peek / animations
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setGeometry(geometry)

        # Note: we intentionally do NOT display the trigger reason on the
        # lockout screen. Naming the specific label (e.g.
        # "FEMALE_GENITALIA_EXPOSED") would surface explicit text in a
        # public/embarrassing context. The reason is still passed in for
        # logging. The incident message (count, duration, shutdown) lives
        # behind the info button.
        _log.info("Lockout window built (reason=%s, hidden from UI).", reason)
        self.message = message or ""

        # --- center column: lock, clock, unlock time -------------------
        # Painted directly in paintEvent and centred on the visible ink of
        # each element, so the lock, the digits and the unlock line share
        # one optical centre line regardless of glyph widths.
        self.clock_text = ""
        self.unlock_text = ""
        self._lock_pix: QPixmap | None = None
        self._clock_font = QFont()
        self._unlock_font = QFont()

        # --- primary-only controls -------------------------------------
        self.remaining_icon: QLabel | None = None
        self.remaining_lbl: QLabel | None = None
        self.power_btn: QPushButton | None = None
        self.power_menu: _PowerMenu | None = None
        self.info_btn: QPushButton | None = None
        self.info_panel: QFrame | None = None
        self.recovery_panel: QFrame | None = None
        self.toast: QLabel | None = None
        self.recovery_available = bool(recovery_enabled and on_recovery_submit)

        if is_primary:
            self.remaining_icon = QLabel(self)
            self.remaining_icon.setStyleSheet("background: transparent;")
            self.remaining_lbl = QLabel(self)

            self.power_btn = QPushButton(self)
            self.power_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.power_btn.setToolTip("Power")
            self.power_btn.clicked.connect(self._toggle_power_menu)

            self.power_menu = _PowerMenu(self, self.recovery_available, self._on_power_action)

            if self.message:
                self.info_btn = QPushButton(self)
                self.info_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                self.info_btn.setToolTip("About this lockout")
                self.info_btn.clicked.connect(self._toggle_info_panel)
                self._build_info_panel()

            self.toast = QLabel(self)
            self.toast.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.toast.setStyleSheet(
                f"color: #f4f6fa; background: {PANEL_BG}; "
                f"border: 1px solid {PANEL_BORDER}; border-radius: 10px; "
                f"padding: 10px 16px; font-size: 13px; font-family: {UI_FONT};"
            )
            self.toast.hide()
            self._toast_timer = QTimer(self)
            self._toast_timer.setSingleShot(True)
            self._toast_timer.timeout.connect(self.toast.hide)

            if self.recovery_available:
                self._build_recovery_panel()

        self._apply_scale()
        self.update_labels()

    # ----- info panel -----------------------------------------------------

    def _build_info_panel(self) -> None:
        panel = QFrame(self)
        panel.setObjectName("infoPanel")
        panel.setStyleSheet(
            f"#infoPanel {{ background: {PANEL_BG}; "
            f"border: 1px solid {PANEL_BORDER}; border-radius: 12px; }}"
        )
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 16, 20, 18)
        layout.setSpacing(0)

        title = QLabel("About this lockout")
        title.setStyleSheet(
            "color: #f4f6fa; background: transparent; font-size: 14px; "
            f"font-weight: 600; font-family: {UI_FONT};"
        )
        layout.addWidget(title)
        layout.addSpacing(10)

        # One row per sentence, each its own label, so spacing is even and
        # nothing depends on word-wrap height guesses.
        sentences = [
            part.strip() for part in self.message.replace(". ", ".\n").split("\n") if part.strip()
        ]
        for index, sentence in enumerate(sentences):
            row = QLabel(sentence)
            row.setStyleSheet(
                "color: rgba(244, 246, 250, 0.8); background: transparent; font-size: 14px; "
                f"font-family: {UI_FONT};"
            )
            if index:
                layout.addSpacing(6)
            layout.addWidget(row)

        panel.adjustSize()
        panel.hide()
        self.info_panel = panel

    def _toggle_info_panel(self) -> None:
        if not self.info_panel:
            return
        if self.info_panel.isVisible():
            self.info_panel.hide()
        else:
            if self.power_menu:
                self.power_menu.hide()
            self._layout_children()
            self.info_panel.show()
            self.info_panel.raise_()

    # ----- recovery -------------------------------------------------------

    def _build_recovery_panel(self) -> None:
        panel = QFrame(self)
        panel.setObjectName("recoveryPanel")
        panel.setStyleSheet(
            f"#recoveryPanel {{ background: {PANEL_BG}; "
            f"border: 1px solid {PANEL_BORDER}; border-radius: 14px; }}"
        )
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        self.recovery_status = QLabel("")
        self.recovery_status.setWordWrap(True)
        self.recovery_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.recovery_status.setStyleSheet(
            f"color: {WHITE_SOFT}; background: transparent; font-size: 13px; font-family: {UI_FONT};"
        )
        layout.addWidget(self.recovery_status)

        self.recovery_code = QLineEdit()
        self.recovery_code.setEchoMode(QLineEdit.EchoMode.Normal)
        self.recovery_code.setPlaceholderText("Recovery code")
        self.recovery_code.setStyleSheet(
            "QLineEdit { color: #f4f6fa; background: rgba(255, 255, 255, 0.06); "
            "border: 1px solid rgba(255, 255, 255, 0.16); border-radius: 8px; "
            f"padding: 9px 12px; font-size: 14px; font-family: {UI_FONT}; }}"
            "QLineEdit:focus { border-color: rgba(255, 255, 255, 0.4); }"
        )
        self.recovery_code.returnPressed.connect(self._submit_recovery)
        layout.addWidget(self.recovery_code)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.recovery_cancel = QPushButton("Cancel")
        self.recovery_submit = QPushButton("Submit")
        for btn, primary in ((self.recovery_cancel, False), (self.recovery_submit, True)):
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            bg = "rgba(255, 255, 255, 0.14)" if primary else "transparent"
            btn.setStyleSheet(
                f"QPushButton {{ color: #f4f6fa; background: {bg}; "
                "border: 1px solid rgba(255, 255, 255, 0.14); border-radius: 8px; "
                f"padding: 8px 14px; font-size: 13px; font-family: {UI_FONT}; }}"
                "QPushButton:hover { background: rgba(255, 255, 255, 0.2); }"
                "QPushButton:disabled { color: rgba(244, 246, 250, 0.4); }"
            )
            actions.addWidget(btn)
        self.recovery_cancel.clicked.connect(self._hide_recovery_form)
        self.recovery_submit.clicked.connect(self._submit_recovery)
        layout.addLayout(actions)

        panel.setFixedWidth(380)
        panel.adjustSize()
        panel.hide()
        self.recovery_panel = panel

    def _show_recovery_form(self) -> None:
        if not self.recovery_panel:
            return
        self.recovery_status.setText("Enter your recovery code to start emergency release.")
        self.recovery_panel.adjustSize()
        self._layout_children()
        self.recovery_panel.show()
        self.recovery_panel.raise_()
        self.recovery_code.setFocus()

    def _hide_recovery_form(self) -> None:
        if not self.recovery_panel:
            return
        self.recovery_code.clear()
        self.recovery_panel.hide()

    def _submit_recovery(self) -> None:
        code = self.recovery_code.text().strip()
        if not code:
            self.recovery_status.setText("Enter your recovery code.")
            return
        if not self.on_recovery_submit:
            self.recovery_status.setText("Emergency release is unavailable.")
            return
        try:
            ok, message, new_end_at = self.on_recovery_submit(code)
        except Exception as e:
            _log.exception("Emergency release callback failed: %s", e)
            self.recovery_status.setText("Emergency release is unavailable.")
            self.recovery_code.selectAll()
            self.recovery_code.setFocus()
            return
        if not ok:
            self.recovery_status.setText(_human_recovery_error(message))
            self.recovery_code.selectAll()
            self.recovery_code.setFocus()
            return
        if new_end_at is not None:
            self.countdown.set_end_at(new_end_at)
        self.recovery_code.clear()
        self.recovery_code.setEnabled(False)
        self.recovery_submit.setEnabled(False)
        self.recovery_cancel.hide()
        # The service message already starts with "Emergency release pending."
        self.recovery_status.setText(message or "Emergency release pending.")
        self.recovery_panel.adjustSize()
        self.update_labels()

    # ----- power menu -----------------------------------------------------

    def _toggle_power_menu(self) -> None:
        if not self.power_menu:
            return
        if self.power_menu.isVisible():
            self.power_menu.hide()
        else:
            if self.info_panel:
                self.info_panel.hide()
            self._layout_children()
            self.power_menu.show()
            self.power_menu.raise_()

    def _on_power_action(self, action: str) -> None:
        if self.power_menu:
            self.power_menu.hide()
        if action == "emergency":
            self._show_recovery_form()
            return
        label = {"sleep": "Sleep", "shutdown": "Shut down", "restart": "Restart"}[action]
        try:
            _run_power_action(action)
        except Exception as e:
            _log.exception("Power action %s failed: %s", action, e)
            self._show_toast(f"{label} could not be started.")

    def _show_toast(self, text: str) -> None:
        if not self.toast:
            return
        self.toast.setText(text)
        self._layout_children()
        self.toast.show()
        self.toast.raise_()
        self._toast_timer.start(2800)

    def mousePressEvent(self, event) -> None:
        # Click anywhere outside a popup closes it.
        point = event.position().toPoint()
        for popup in (self.power_menu, self.info_panel):
            if popup and popup.isVisible() and not popup.geometry().contains(point):
                popup.hide()
        super().mousePressEvent(event)

    # ----- layout and painting -------------------------------------------

    def _apply_scale(self) -> None:
        h = max(600, self.height())
        self._clock_px = int(h * 0.135)

        self._clock_font = QFont()
        self._clock_font.setFamilies(CLOCK_FAMILIES)
        self._clock_font.setPixelSize(self._clock_px)
        self._clock_font.setWeight(QFont.Weight.Light)

        self._unlock_font = QFont()
        self._unlock_font.setFamilies(TEXT_FAMILIES)
        self._unlock_font.setPixelSize(max(16, int(h * 0.024)))
        self._unlock_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.5)

        self._lock_pix = _icon_pixmap("lock", max(28, int(h * 0.042)), NAVY, 1.5)

        if self.is_primary:
            # Corner controls grow gently on tall screens (1.0 at 1080 px).
            k = min(1.35, max(1.0, h / 1080))
            btn_px = int(48 * k)
            icon_px = int(22 * k)
            round_style = (
                f"QPushButton {{ background: rgba(24, 33, 48, 0.72); "
                f"border: 1px solid rgba(255, 255, 255, 0.1); border-radius: {btn_px // 2}px; }}"
                "QPushButton:hover { background: rgba(24, 33, 48, 0.9); "
                "border-color: rgba(255, 255, 255, 0.2); }"
            )
            self.power_btn.setFixedSize(btn_px, btn_px)
            self.power_btn.setIconSize(QSize(icon_px, icon_px))
            self.power_btn.setIcon(QIcon(_icon_pixmap("power", icon_px, "#f4f6fa", 1.8)))
            self.power_btn.setStyleSheet(round_style)
            if self.info_btn:
                # Same size and style as the power button.
                self.info_btn.setFixedSize(btn_px, btn_px)
                self.info_btn.setIconSize(QSize(icon_px, icon_px))
                self.info_btn.setIcon(QIcon(_icon_pixmap("info", icon_px, "#f4f6fa", 1.8)))
                self.info_btn.setStyleSheet(round_style)
            self.remaining_icon.setPixmap(_icon_pixmap("lock", int(18 * k), "#f4f6fa"))
            self.remaining_lbl.setStyleSheet(
                f"color: {WHITE_SOFT}; background: transparent; font-size: {int(15 * k)}px; "
                f"font-family: {UI_FONT};"
            )

    def _layout_children(self) -> None:
        if not self.is_primary:
            return
        w, h = self.width(), self.height()
        margin = max(28, int(h * 0.04))

        btn = self.power_btn
        btn.move(w - margin - btn.width(), h - margin - btn.height())
        center_y = btn.y() + btn.height() // 2

        icon = self.remaining_icon
        icon.adjustSize()
        icon.move(margin, center_y - icon.height() // 2)
        self.remaining_lbl.adjustSize()
        self.remaining_lbl.move(
            icon.x() + icon.width() + 10, center_y - self.remaining_lbl.height() // 2
        )

        if self.info_btn:
            self.info_btn.move(w - margin - self.info_btn.width(), margin)
            panel = self.info_panel
            panel.adjustSize()
            panel.move(
                self.info_btn.x() + self.info_btn.width() - panel.width(),
                self.info_btn.y() + self.info_btn.height() + 10,
            )

        menu = self.power_menu
        menu.adjustSize()
        menu.move(btn.x() + btn.width() - menu.width(), btn.y() - 10 - menu.height())

        if self.recovery_panel:
            panel = self.recovery_panel
            panel.adjustSize()
            panel.move((w - panel.width()) // 2, int(h * 0.56))

        if self.toast:
            self.toast.adjustSize()
            self.toast.move((w - self.toast.width()) // 2, h - margin - self.toast.height())

    def resizeEvent(self, event) -> None:
        self._scaled_bg = None
        self._apply_scale()
        self._layout_children()
        super().resizeEvent(event)

    def _scaled_background(self) -> QPixmap | None:
        if self._background is None or self._background.isNull():
            return None
        if self._scaled_bg is None:
            dpr = self.devicePixelRatioF()
            tw = max(1, int(round(self.width() * dpr)))
            th = max(1, int(round(self.height() * dpr)))
            scaled = self._background.scaled(
                tw, th,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            # Center crop so the ridges fill the screen at any aspect ratio.
            x = max(0, (scaled.width() - tw) // 2)
            y = max(0, (scaled.height() - th) // 2)
            cropped = scaled.copy(x, y, tw, th)
            cropped.setDevicePixelRatio(dpr)
            self._scaled_bg = cropped
        return self._scaled_bg

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        bg = self._scaled_background()
        if bg is not None:
            painter.drawPixmap(0, 0, bg)
        else:
            # Same light-sky-to-dark-ridge tones as the photo, so the navy
            # clock and the white controls both stay readable.
            fallback = QLinearGradient(QPointF(0, 0), QPointF(0, self.height()))
            fallback.setColorAt(0.0, FALLBACK_SKY)
            fallback.setColorAt(0.45, FALLBACK_MID)
            fallback.setColorAt(1.0, FALLBACK_GROUND)
            painter.fillRect(self.rect(), fallback)
        # Soft darkening toward the bottom keeps the white controls legible.
        grad = QLinearGradient(QPointF(0, self.height() * 0.55), QPointF(0, self.height()))
        grad.setColorAt(0.0, QColor(10, 16, 26, 0))
        grad.setColorAt(1.0, QColor(10, 16, 26, 110))
        painter.fillRect(self.rect(), grad)
        self._paint_center_column(painter)
        painter.end()

    def _center_column_geometry(self) -> dict:
        """Positions for the lock, clock and unlock line, from real ink bounds."""
        w, h = self.width(), self.height()
        cx = w / 2

        lock_size = self._lock_pix.width() / self._lock_pix.devicePixelRatio()
        lock_top = h * 0.085
        lock_rect = QRectF(cx - lock_size / 2, lock_top, lock_size, lock_size)

        clock_path = QPainterPath()
        clock_path.addText(0, 0, self._clock_font, self.clock_text)
        clock_ink = clock_path.boundingRect()
        clock_top = lock_rect.bottom() + h * 0.045
        clock_offset = QPointF(
            cx - (clock_ink.left() + clock_ink.width() / 2), clock_top - clock_ink.top()
        )

        unlock_path = QPainterPath()
        unlock_path.addText(0, 0, self._unlock_font, self.unlock_text)
        unlock_ink = unlock_path.boundingRect()
        unlock_top = clock_top + clock_ink.height() + h * 0.04
        unlock_origin = QPointF(
            cx - (unlock_ink.left() + unlock_ink.width() / 2), unlock_top - unlock_ink.top()
        )
        return {
            "lock_rect": lock_rect,
            "clock_path": clock_path.translated(clock_offset),
            "unlock_origin": unlock_origin,
        }

    def _paint_center_column(self, painter: QPainter) -> None:
        if self._lock_pix is None or not self.clock_text:
            return
        geo = self._center_column_geometry()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.drawPixmap(geo["lock_rect"].topLeft(), self._lock_pix)
        # The large clock is filled as an outline path so what is centred is
        # exactly what is drawn.
        painter.fillPath(geo["clock_path"], NAVY_QCOLOR)
        painter.setFont(self._unlock_font)
        painter.setPen(NAVY_SOFT_QCOLOR)
        painter.drawText(geo["unlock_origin"], self.unlock_text)

    def update_labels(self) -> None:
        now = datetime.now()
        remaining = self.countdown.remaining()
        clock_text = _format_clock(now)
        unlock_text = format_unlocks_at(now, now + timedelta(seconds=remaining))
        if clock_text != self.clock_text or unlock_text != self.unlock_text:
            self.clock_text = clock_text
            self.unlock_text = unlock_text
            self.update()
        if self.remaining_lbl is not None:
            self.remaining_lbl.setText(format_remaining(remaining))
        self._layout_children()

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

        background = QPixmap(asset_path(BACKGROUND_FILE))
        if background.isNull():
            # The lockout still works on a plain background.
            _log.warning("Lockout background %s could not be loaded.", BACKGROUND_FILE)

        screens = QGuiApplication.screens()
        primary_screen = QGuiApplication.primaryScreen()
        for screen in screens:
            geom = screen.geometry()
            win = _LockoutWindow(
                geom, self.reason, self.message, is_primary=(screen is primary_screen),
                countdown=self.countdown,
                background=background,
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
        for w in self.windows:
            w.update_labels()

        timer = QTimer()
        timer.setInterval(250)

        def tick() -> None:
            for w in self.windows:
                w.update_labels()
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


def _run_power_action(action: str) -> None:
    """Start a normal (not forced) Windows power action so apps can save."""
    if action == "sleep":
        # SetSuspendState(hibernate=False, force=False, wakeupEventsDisabled=False)
        ctypes.WinDLL("PowrProf").SetSuspendState(False, False, False)
    elif action == "shutdown":
        subprocess.Popen(["shutdown", "/s", "/t", "0"], creationflags=subprocess.CREATE_NO_WINDOW)
    elif action == "restart":
        subprocess.Popen(["shutdown", "/r", "/t", "0"], creationflags=subprocess.CREATE_NO_WINDOW)


def _human_recovery_error(error: str) -> str:
    return {
        "wrong_recovery_code": "That recovery code is not correct.",
        "recovery_unavailable": "Recovery code verification is unavailable.",
        "lockout_recovery_disabled": "Emergency release is not enabled for lockouts.",
        "lockout_recovery_limit_reached": "Your lockout recovery limit has been reached for the last 24 hours.",
        "no_active_lockout": "This lockout is no longer active.",
        "lockout_unavailable": "The lockout record could not be updated.",
        "state_unavailable": "Brake settings could not be verified.",
        "service_unavailable": "Brake could not reach the background service. The lockout remains active.",
        "not_initialized": "Brake has not been set up yet.",
    }.get(error, "Emergency release failed.")
