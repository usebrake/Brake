"""Brand assets used by the GUI.

Single source of truth for icon paths + small helpers for runtime
recoloring (gray-from-teal for the disabled tray state). Keeps the
filenames in one place so PyInstaller bundling later is one path edit.
"""
from __future__ import annotations

from pathlib import Path

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFontDatabase, QIcon, QImage, QPainter, QPixmap


_ASSETS_DIR = Path(__file__).resolve().parent
_FONTS_DIR = _ASSETS_DIR / "fonts"

_log = logging.getLogger(__name__)

# Set by load_bundled_fonts() at app startup.
GEIST_FAMILY = "Geist"
GEIST_MONO_FAMILY = "Geist Mono"


def load_bundled_fonts() -> None:
    """Register Geist + Geist Mono with Qt at app startup.

    Must run before any widget styling so QSS font-family rules can resolve.
    Falls back silently to Segoe UI if a file is missing — the app still
    works, just looks like a default Windows utility.
    """
    global GEIST_FAMILY, GEIST_MONO_FAMILY
    files = [
        ("Geist-Regular.ttf",     "Geist"),
        ("Geist-Medium.ttf",      "Geist"),
        ("Geist-Bold.ttf",        "Geist"),
        ("GeistMono-Regular.ttf", "Geist Mono"),
    ]
    loaded_sans, loaded_mono = None, None
    for filename, kind in files:
        path = _FONTS_DIR / filename
        if not path.exists():
            _log.warning("Bundled font missing: %s", path)
            continue
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id < 0:
            _log.warning("Qt rejected font: %s", path)
            continue
        families = QFontDatabase.applicationFontFamilies(font_id)
        if not families:
            continue
        if kind == "Geist":
            loaded_sans = families[0]
        else:
            loaded_mono = families[0]
    if loaded_sans:
        GEIST_FAMILY = loaded_sans
    if loaded_mono:
        GEIST_MONO_FAMILY = loaded_mono
    _log.info("Fonts loaded: %s / %s", GEIST_FAMILY, GEIST_MONO_FAMILY)


def asset_path(filename: str) -> str:
    """Absolute path to an asset file inside this package."""
    return str(_ASSETS_DIR / filename)


# ---------- canonical paths ----------

def app_icon_path() -> str:
    """Windows .ico used by PyInstaller to embed into the app executable.

    For the *running* GUI process we don't use this — see build_app_qicon()
    which builds a multi-size QIcon directly from the high-res PNG with
    Qt's smooth scaler. That gives a noticeably crisper taskbar icon
    than the .ico renderer.
    """
    return asset_path("brake.ico")


def build_app_qicon() -> "QIcon":
    """Build a multi-size QIcon from the high-res Brake mark PNG.

    Windows picks the closest size from a QIcon when rendering taskbar /
    Alt+Tab / title bar entries. Baking many sizes from the 1024x1024
    source ensures every render is a smooth downscale, not an ugly upscale
    from a small favicon.
    """
    icon = QIcon()
    src = QPixmap(asset_path("brake_large.png"))
    if src.isNull():
        return QIcon(app_icon_path())  # fall back to the .ico
    for size in (16, 20, 24, 32, 40, 48, 64, 96, 128, 256):
        scaled = src.scaled(
            size, size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        icon.addPixmap(scaled)
    return icon


def brake_path(tone: str = "base", size: int = 32) -> str:
    """Return the Brake mark PNG for a tone/size."""
    prefix = {
        "teal": "brake_teal",
        "amber": "brake_amber",
    }.get(tone, "brake")
    if tone in {"teal", "amber"} and size > 32:
        return asset_path(f"{prefix}_large.png")
    if size <= 16:
        return asset_path(f"{prefix}_16.png")
    if size <= 32:
        return asset_path(f"{prefix}_32.png")
    if size <= 192:
        return asset_path(f"{prefix}_192.png")
    return asset_path(f"{prefix}_large.png")


def brake_pixmap(tone: str, target_size: int) -> QPixmap:
    src = QPixmap(brake_path(tone, max(target_size, 192)))
    return src.scaled(
        target_size, target_size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


def brake_icon(tone: str = "base", size: int = 32) -> QIcon:
    return QIcon(brake_pixmap(tone, size))


def brake_icon_disabled(size: int = 32) -> QIcon:
    return QIcon(_faded(QPixmap(brake_path("base", size)), 0.45))


def lock_teal_path(size: int = 32) -> str:
    """Pick the smallest source that is still LARGER than the display size.

    Scaling DOWN from high-res looks dramatically sharper than scaling UP
    from a tiny source. The tray needs the 16/32 PNGs because Windows
    expects exact sizes there, but every in-window use should pull from
    the 192px or large source.
    """
    if size <= 16:
        return asset_path("lock_teal_16.png")
    if size <= 32:
        return asset_path("lock_teal_32.png")
    if size <= 192:
        return asset_path("lock_teal_192.png")
    return asset_path("lock_teal_large.png")


def lock_amber_path(size: int = 32) -> str:
    if size <= 16:
        return asset_path("lock_amber_16.png")
    # We only ship 16/32 for amber. For larger displays, the 32 will be
    # upscaled with smooth interpolation by the caller.
    return asset_path("lock_amber_32.png")


def hires_lock_pixmap(tone: str, target_size: int) -> QPixmap:
    """Best-quality lock at any display size.

    For teal we pull from the 192px or large source and scale DOWN.
    For amber (we don't have a 192 yet), we scale the 32 up smoothly.
    Either way the caller gets a pixmap exactly target_size px wide,
    rendered with smooth interpolation so pixel art reads sharp at
    arbitrary sizes instead of jagged.
    """
    if tone == "amber":
        src = QPixmap(asset_path("lock_amber_32.png"))
    else:
        # Always start from the large source for teal — best fidelity.
        src = QPixmap(asset_path("lock_teal_large.png"))
    return src.scaled(
        target_size, target_size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


# ---------- QIcon builders ----------

def lock_icon_teal(size: int = 32) -> QIcon:
    return QIcon(lock_teal_path(size))


def lock_icon_amber(size: int = 32) -> QIcon:
    return QIcon(lock_amber_path(size))


def lock_icon_gray(size: int = 32) -> QIcon:
    """Faded version of the teal lock — used for the 'disabled' state.

    We render the teal lock at reduced opacity rather than desaturating
    it. The PNG ships with a slight dark canvas baked into the art, and
    full grayscale conversion makes that canvas pop as a dark square.
    Reducing opacity dims everything uniformly, so both the lock and the
    canvas fade together against the surface.
    """
    pixmap = _faded(QPixmap(lock_teal_path(size)), 0.45)
    return QIcon(pixmap)


def lock_pixmap_teal_large(target_height: int) -> QPixmap:
    """Teal lock at a specific height (used by the lockout screen).

    Pulls from the large source PNG and scales smoothly. Smooth scaling
    of a high-res pixel-art PNG preserves the chunky look while keeping
    edges clean at arbitrary sizes.
    """
    src = QPixmap(asset_path("lock_teal_large.png"))
    return src.scaledToHeight(
        target_height,
        Qt.TransformationMode.SmoothTransformation,
    )


# ---------- internals ----------

def _desaturate(src: QPixmap) -> QPixmap:
    """Return a grayscale copy of the pixmap, preserving alpha.

    Kept for callers that want true grayscale. The default "off" state
    uses _faded() instead because the shipped lock PNG has a slight
    dark canvas that becomes a visible black square after desaturation.
    """
    if src.isNull():
        return src
    image = src.toImage().convertToFormat(QImage.Format.Format_ARGB32)
    width, height = image.width(), image.height()
    for y in range(height):
        for x in range(width):
            color = QColor(image.pixel(x, y))
            luma = int(0.299 * color.red() + 0.587 * color.green() + 0.114 * color.blue())
            image.setPixel(x, y, QColor(luma, luma, luma, color.alpha()).rgba())
    return QPixmap.fromImage(image)


def _faded(src: QPixmap, opacity: float = 0.45) -> QPixmap:
    """Render the source at reduced opacity onto a transparent canvas.

    Used for the 'protection off' state. Reduces opacity uniformly so
    both the lock and any dark canvas baked into the PNG fade together
    against whatever surface the lock sits on.
    """
    if src.isNull():
        return src
    result = QPixmap(src.size())
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    try:
        painter.setOpacity(max(0.0, min(1.0, opacity)))
        painter.drawPixmap(0, 0, src)
    finally:
        painter.end()
    return result
