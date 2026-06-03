"""Fast-track test mode.

Set the environment variable BRAKE_TEST_MODE=1 (in the same process that
launches the service / agent / lockout) to:

- shrink every timer in the detection/lockout/probation pipeline to a few
  seconds, so you can run the full first-hit -> shutdown -> reboot ->
  probation -> penalty flow in under two minutes instead of twenty.
- skip the real Windows shutdown call. The lockout still finishes its
  countdown and logs "would shut down now", but your session survives.

Anything that should change behavior under test mode reads from here. Do not
sprinkle os.getenv("BRAKE_TEST_MODE") checks elsewhere — keep the switch
in one place so it's easy to audit and easy to remove for a release build.

Production behavior is the default: if BRAKE_TEST_MODE is unset/0/false,
every helper here returns the real production value.
"""
from __future__ import annotations

import logging
import os

_log = logging.getLogger(__name__)

_TRUTHY = {"1", "true", "yes", "on"}


def is_test_mode() -> bool:
    return os.environ.get("BRAKE_TEST_MODE", "").strip().lower() in _TRUTHY


def t(real_seconds: int, test_seconds: int) -> int:
    """Return test_seconds when BRAKE_TEST_MODE is on, else real_seconds."""
    return test_seconds if is_test_mode() else real_seconds


def should_actually_shutdown() -> bool:
    """Real shutdown only happens in production mode."""
    return not is_test_mode()


def log_banner_once() -> None:
    """Call this from each long-lived entrypoint so logs make the mode obvious."""
    if is_test_mode():
        _log.warning(
            "BRAKE_TEST_MODE=1 — timers compressed and shutdown disabled. "
            "Do NOT use this mode for real protection."
        )
