"""Multi-monitor screen capture via mss. Returns a single stitched PIL.Image.

Held in memory only — we never write screenshots to disk anywhere in the app.
"""
from __future__ import annotations

import mss
from PIL import Image


def capture_all_monitors() -> Image.Image:
    """Capture the full virtual desktop across all monitors as one PIL.Image (RGB)."""
    with mss.mss() as sct:
        shot = sct.grab(sct.monitors[0])  # monitors[0] is the full virtual screen
        # mss returns BGRA; PIL wants RGB
        img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        return img
