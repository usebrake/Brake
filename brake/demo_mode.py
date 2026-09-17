"""Explicit local demo mode that cannot perform protection actions."""
from __future__ import annotations

import os

_TRUTHY = {"1", "true", "yes", "on"}


def is_demo_mode() -> bool:
    return os.environ.get("BRAKE_DEMO_MODE", "").strip().lower() in _TRUTHY
