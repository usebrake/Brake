"""Countdown supporting two modes:

- monotonic: `Countdown(duration_seconds=N)` — used for transient/test lockouts
  that should not survive process death. Immune to wall-clock manipulation.

- wall-clock: `Countdown(end_at=datetime_utc)` — used for persisted lockouts.
  Continues across reboot/hibernate/sleep because end_at is an absolute UTC
  timestamp read from disk. Vulnerable to clock manipulation, but during an
  active lockout the keyboard hook + fullscreen overlay block the Settings
  app, so changing the clock requires reboot + file tampering (which the
  HMAC catches).
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Optional


class Countdown:
    def __init__(
        self,
        duration_seconds: Optional[float] = None,
        end_at: Optional[datetime] = None,
    ) -> None:
        if (duration_seconds is None) == (end_at is None):
            raise ValueError("Provide exactly one of duration_seconds or end_at.")
        self.duration_seconds = duration_seconds
        self.end_at = end_at
        self._started_monotonic = 0.0

    def start(self) -> None:
        if self.duration_seconds is not None:
            self._started_monotonic = time.monotonic()

    def set_end_at(self, end_at: datetime) -> None:
        self.duration_seconds = None
        self.end_at = end_at.astimezone(timezone.utc)

    def remaining(self) -> float:
        if self.end_at is not None:
            return max(0.0, (self.end_at - datetime.now(timezone.utc)).total_seconds())
        elapsed = time.monotonic() - self._started_monotonic
        return max(0.0, (self.duration_seconds or 0.0) - elapsed)

    def is_done(self) -> bool:
        return self.remaining() <= 0.0

    @staticmethod
    def format_mmss(seconds: float) -> str:
        s = int(seconds)
        return f"{s // 60:02d}:{s % 60:02d}"
