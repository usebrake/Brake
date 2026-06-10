"""Multi-monitor screen capture via mss. Returns a single stitched PIL.Image.

Held in memory only — we never write screenshots to disk anywhere in the app.
"""
from __future__ import annotations

import sys

import mss
from PIL import Image

if sys.platform == "win32":
    # mss blits with SRCCOPY | CAPTUREBLT by default. CAPTUREBLT forces GDI to
    # re-composite layered windows on every grab, which shows up as a brief
    # grey flash/stutter, worst around fullscreen video transitions. On a
    # DWM-composited desktop (Windows 8+) a plain SRCCOPY blit still captures
    # the composited screen, so we drop the flag.
    try:
        from mss.windows import gdi as _mss_gdi  # mss >= 10.2

        _mss_gdi.CAPTUREBLT = 0
    except ImportError:
        try:
            import mss.windows as _mss_windows  # mss < 10.2

            if hasattr(_mss_windows, "CAPTUREBLT"):
                _mss_windows.CAPTUREBLT = 0
        except ImportError:
            pass


# One capture handle reused across grabs. Creating/destroying device contexts
# per grab is measurable overhead at the watcher's tick rate. Only the watcher
# thread captures, so no locking is needed.
_sct: mss.base.MSSBase | None = None


def reset_capture_handle() -> None:
    """Drop the cached mss handle, e.g. after display geometry changes."""
    global _sct
    if _sct is not None:
        try:
            _sct.close()
        except Exception:
            pass
    _sct = None


def capture_all_monitors() -> Image.Image:
    """Capture the full virtual desktop across all monitors as one PIL.Image (RGB)."""
    global _sct
    last_error: Exception | None = None
    for _attempt in range(2):
        try:
            if _sct is None:
                _sct = mss.mss()
            shot = _sct.grab(_sct.monitors[0])  # monitors[0] is the full virtual screen
            # mss returns BGRA; PIL wants RGB
            return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        except Exception as e:
            last_error = e
            reset_capture_handle()
    raise last_error if last_error else RuntimeError("capture failed")
