"""Safe, transient lockout overlay used only by Brake Demo."""
from __future__ import annotations

import argparse
import os
import sys

from brake.demo_mode import is_demo_mode
from brake.lockout.countdown import Countdown
from brake.lockout.window import LockoutApp


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="brake.lockout.demo")
    parser.add_argument("--duration", type=int, default=10)
    args = parser.parse_args(argv)

    if not is_demo_mode():
        print("The demo lockout requires BRAKE_DEMO_MODE=1.", file=sys.stderr)
        return 2

    duration = max(1, min(int(args.duration), 300))
    os.environ["BRAKE_NO_KBD_HOOK"] = "1"
    countdown = Countdown(duration_seconds=duration)
    return LockoutApp(countdown, reason="DEMO").run()


if __name__ == "__main__":
    sys.exit(main())
