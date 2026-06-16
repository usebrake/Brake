"""Entry point for the lockout subprocess.

Three modes:

  python -m brake.lockout --duration 600 --reason NUDITY
      Persistent lockout. Writes lockout.json, installs autostart, runs.

  python -m brake.lockout --duration 10 --reason TEST --no-persist
      Transient (test) lockout. Doesn't touch disk; doesn't survive reboot.

  python -m brake.lockout
      Resume mode. Reads lockout.json; if active, shows the remaining time.
      If file is missing or expired, exits 0 silently.
      If file is tampered, triggers a fail-secure default lockout.
"""
from __future__ import annotations

import argparse
import logging
import subprocess
import sys

from brake import autostart
from brake.config import load_settings
from brake.lockout.countdown import Countdown
from brake.lockout.emergency import apply_lockout_recovery, lockout_recovery_available
from brake.lockout.persistence import LockoutPersistence, _TamperedLockoutError
from brake.lockout.recovery import clear_lockout_pid, write_lockout_pid
from brake.lockout.window import LockoutApp
from brake.test_mode import should_actually_shutdown


def _shutdown_windows() -> None:
    if sys.platform != "win32":
        logging.warning("shutdown_on_done requested on non-Windows; ignoring.")
        return
    if not should_actually_shutdown():
        logging.warning("BRAKE_TEST_MODE: would shut down Windows now (skipped).")
        return
    try:
        # /f forces running applications to close instead of letting an
        # unsaved document cancel or indefinitely delay the shutdown.
        subprocess.Popen(["shutdown.exe", "/s", "/f", "/t", "0"])
    except Exception as e:
        logging.exception("Failed to request Windows shutdown: %s", e)


def _on_done(persist: LockoutPersistence, shutdown_on_done: bool):
    def done() -> None:
        should_shutdown = shutdown_on_done
        if shutdown_on_done:
            try:
                record = persist.resume()
                if record is not None:
                    should_shutdown = record.shutdown_on_done
            except _TamperedLockoutError:
                should_shutdown = True
        try:
            persist.clear()
        except Exception as e:
            logging.exception("Failed to clear expired lockout record before shutdown: %s", e)
        if should_shutdown:
            _shutdown_windows()
    return done


def _run_persistent(duration: int, reason: str, message: str = "", shutdown_on_done: bool = False) -> int:
    persist = LockoutPersistence()
    record = persist.start(duration, reason, message=message, shutdown_on_done=shutdown_on_done)
    autostart.ensure_boot_entry()  # so a reboot mid-lockout still recovers
    cd = Countdown(end_at=record.end_dt())
    write_lockout_pid()
    try:
        return LockoutApp(
            cd,
            reason=reason,
            message=message,
            on_done=_on_done(persist, shutdown_on_done),
            recovery_enabled=shutdown_on_done and lockout_recovery_available(),
            on_recovery_submit=lambda code: apply_lockout_recovery(code, persistence=persist),
        ).run()
    finally:
        clear_lockout_pid()


def _run_transient(duration: int, reason: str, message: str = "", shutdown_on_done: bool = False) -> int:
    cd = Countdown(duration_seconds=duration)
    return LockoutApp(cd, reason=reason, message=message, on_done=(_shutdown_windows if shutdown_on_done else None)).run()


def _run_resume() -> int:
    persist = LockoutPersistence()
    try:
        record = persist.resume()
    except _TamperedLockoutError:
        # fail-secure: tampered file → re-issue a full default lockout
        settings = load_settings()
        return _run_persistent(settings.lockout_duration_seconds, "TAMPER")

    if record is None or record.is_expired():
        persist.clear()
        return 0

    cd = Countdown(end_at=record.end_dt())
    write_lockout_pid()
    try:
        return LockoutApp(
            cd,
            reason=record.reason,
            message=record.message,
            on_done=_on_done(persist, record.shutdown_on_done),
            recovery_enabled=record.shutdown_on_done and lockout_recovery_available(),
            on_recovery_submit=lambda code: apply_lockout_recovery(code, persistence=persist),
        ).run()
    finally:
        clear_lockout_pid()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="brake.lockout")
    parser.add_argument("--duration", type=int, help="Lockout duration in seconds.")
    parser.add_argument("--reason", type=str, default="UNKNOWN")
    parser.add_argument("--message", type=str, default="")
    parser.add_argument("--shutdown-on-done", action="store_true",
                        help="Request Windows shutdown after the lockout naturally expires.")
    parser.add_argument("--no-persist", action="store_true",
                        help="Transient lockout; don't write lockout.json or autostart hook.")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if args.duration is None:
        return _run_resume()
    if args.no_persist:
        return _run_transient(args.duration, args.reason, args.message, args.shutdown_on_done)
    return _run_persistent(args.duration, args.reason, args.message, args.shutdown_on_done)


if __name__ == "__main__":
    sys.exit(main())
