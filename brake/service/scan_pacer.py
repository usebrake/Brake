"""Decides when the watcher should run detection.

The watcher captures a frame on a fast, cheap tick. This module diffs each
frame against the previous one and tells the watcher whether the screen
changed enough to be worth a detection pass, where the change happened, and
how long to wait before the next tick.

Inference is the expensive step; capture plus a thumbnail diff costs a few
milliseconds. So Brake looks often and thinks only when something moved:

- static screen: no inference at all, just a slow safety sweep
- a change after calm (page load, scroll stop, window switch): scan at once
- continuous change (video playing): scan on a steady budgeted cadence
- change stops: scan the settled frame immediately, because that is what
  the user is now looking at
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np
from PIL import Image

from brake.test_mode import is_test_mode

Rect = Tuple[int, int, int, int]

# Diff grid: the frame is reduced to a 160x90 grayscale thumbnail and split
# into 16x9 blocks, so one block covers roughly a 160px square of a 1440p
# screen. A block counts as changed when its mean gray level moves by more
# than BLOCK_DELTA.
GRID_COLS = 16
GRID_ROWS = 9
_BLOCK_PX = 10
THUMB_SIZE = (GRID_COLS * _BLOCK_PX, GRID_ROWS * _BLOCK_PX)
BLOCK_DELTA = 10.0
MIN_CHANGED_BLOCKS = 2

ACTIVE_TICK_SECONDS = 0.4
SUSTAINED_TICK_SECONDS = 0.8
IDLE_TICK_SECONDS = 1.0
IDLE_AFTER_SECONDS = 30.0

# Continuous change for longer than this is treated as video-like playback
# and scanned on a steady budget instead of every burst.
SUSTAINED_AFTER_SECONDS = 3.0
BURST_MIN_SPACING_SECONDS = 0.45
BURST_SCAN_SPACING_SECONDS = 0.9
SUSTAINED_SCAN_SECONDS = 2.0
SUSTAINED_FULL_SWEEP_SECONDS = 6.0
SETTLE_MIN_SPACING_SECONDS = 0.3
SAFETY_SWEEP_SECONDS = 15.0


@dataclass
class TickDecision:
    scan: bool
    reason: str                 # startup|burst|sustained|settle|periodic|window|confirm|none
    sweep: str                  # "full" | "targeted"
    changed_box: Optional[Rect]  # full-resolution coords of the changed area
    tick_seconds: float


class FramePacer:
    def __init__(self, sustained_scan_seconds: float = SUSTAINED_SCAN_SECONDS) -> None:
        self.sustained_scan_seconds = max(0.5, float(sustained_scan_seconds))
        self._prev: Optional[np.ndarray] = None
        self._size: Optional[Tuple[int, int]] = None
        self._last_change_at = 0.0
        self._change_started_at: Optional[float] = None
        self._last_scan_at = 0.0
        self._last_full_sweep_at = 0.0

    def observe(
        self,
        image: Image.Image,
        now: float,
        force_scan: bool = False,
        force_reason: str = "window",
    ) -> TickDecision:
        gray = np.asarray(
            image.convert("L").resize(THUMB_SIZE, Image.BOX), dtype=np.int16
        )
        first_frame = self._prev is None or self._size != image.size

        changing = False
        changed_box: Optional[Rect] = None
        if not first_frame:
            diff = np.abs(gray - self._prev)
            blocks = diff.reshape(GRID_ROWS, _BLOCK_PX, GRID_COLS, _BLOCK_PX).mean(axis=(1, 3))
            mask = blocks > BLOCK_DELTA
            if int(mask.sum()) >= MIN_CHANGED_BLOCKS:
                changing = True
                changed_box = self._mask_to_box(mask, image.size)
        self._prev = gray
        self._size = image.size

        scan = False
        reason = "none"
        sweep = "full"

        if force_scan:
            scan = True
            reason = force_reason
            sweep = "targeted" if force_reason == "confirm" else "full"
            if changing:
                if self._change_started_at is None:
                    self._change_started_at = now
                self._last_change_at = now
        elif first_frame:
            scan = True
            reason = "startup"
            # Keep ticks fast initially, but do not mark a change as started:
            # a static frame right after startup is not a "settle".
            self._last_change_at = now
        elif changing:
            if self._change_started_at is None:
                self._change_started_at = now
                # First change after calm: look right away.
                if now - self._last_scan_at >= BURST_MIN_SPACING_SECONDS:
                    scan = True
                    reason = "burst"
            elif (now - self._change_started_at) >= SUSTAINED_AFTER_SECONDS:
                if now - self._last_scan_at >= self.sustained_scan_seconds:
                    scan = True
                    reason = "sustained"
                    if now - self._last_full_sweep_at < SUSTAINED_FULL_SWEEP_SECONDS:
                        sweep = "targeted"
            else:
                if now - self._last_scan_at >= BURST_SCAN_SPACING_SECONDS:
                    scan = True
                    reason = "burst"
            self._last_change_at = now
        else:
            if self._change_started_at is not None:
                # Change just stopped: the settled frame is what the user is
                # actually looking at, so scan it now.
                self._change_started_at = None
                if now - self._last_scan_at >= SETTLE_MIN_SPACING_SECONDS:
                    scan = True
                    reason = "settle"
            elif now - self._last_scan_at >= SAFETY_SWEEP_SECONDS:
                scan = True
                reason = "periodic"

        if scan:
            self._last_scan_at = now
            if sweep == "full":
                self._last_full_sweep_at = now

        if changing and self._change_started_at is not None and (
            now - self._change_started_at
        ) >= SUSTAINED_AFTER_SECONDS:
            tick = SUSTAINED_TICK_SECONDS
        elif (now - self._last_change_at) >= IDLE_AFTER_SECONDS:
            tick = IDLE_TICK_SECONDS
        else:
            tick = ACTIVE_TICK_SECONDS
        if is_test_mode():
            tick = min(tick, 0.4)

        return TickDecision(
            scan=scan,
            reason=reason,
            sweep=sweep,
            changed_box=changed_box,
            tick_seconds=tick,
        )

    @staticmethod
    def _mask_to_box(mask: np.ndarray, size: Tuple[int, int]) -> Rect:
        ys, xs = np.nonzero(mask)
        width, height = size
        # Expand by one block of margin so partially-covered content is kept.
        left = max(0, int(xs.min()) - 1)
        top = max(0, int(ys.min()) - 1)
        right = min(GRID_COLS, int(xs.max()) + 2)
        bottom = min(GRID_ROWS, int(ys.max()) + 2)
        return (
            left * width // GRID_COLS,
            top * height // GRID_ROWS,
            right * width // GRID_COLS,
            bottom * height // GRID_ROWS,
        )
