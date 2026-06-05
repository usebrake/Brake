"""Small JSON bridge used by the Electron shell.

Electron should not know how state files, IPC, or lockout launching work.
This module exposes the existing Python controller as a tiny command-line API
that prints one JSON object to stdout.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from typing import Any

from brake.detectors.anime_nsfw import anime_model_status, download_model, model_dir
from brake.gui.controller import Controller
from brake.lockout.recovery import spawn_resume_lockout_if_needed
from brake.runtime import lockout_command
from brake.state import State
from brake.state.crypto import hash_password
from brake.state.first_run import ensure_first_run_state
from brake.state.recovery import RecoveryStore

DEV_PASSWORD = "brake-dev-password"


def _ensure_dev_state(controller: Controller) -> None:
    """Create a local dev state only when Electron explicitly asks for it."""
    if not bool(os.environ.get("BRAKE_DESKTOP_DEV")):
        return
    if controller.service_up():
        return
    if controller.store.load() is not None:
        return
    controller.store.save(State(password_hash=hash_password(DEV_PASSWORD), enabled=False))


def _status_payload(controller: Controller) -> dict[str, Any]:
    status = controller.status()
    return {
        "initialized": bool(status.get("initialized", False)),
        "enabled": bool(status.get("enabled", False)),
        "commitmentActive": bool(status.get("commitment_active", False)),
        "committedUntil": status.get("committed_until"),
        "lockoutDurationMinutes": int(status.get("lockout_duration_minutes", 3) or 3),
        "detectionSensitivity": str(status.get("detection_sensitivity", "balanced") or "balanced"),
        "animeDetectionEnabled": bool(status.get("anime_detection_enabled", False)),
        "animeDetectionMode": str(status.get("anime_detection_mode", "standard") or "standard"),
        "animeModelStatus": str(status.get("anime_model_status", anime_model_status()) or "not_installed"),
        "recoveryUnlockAfter": status.get("recovery_unlock_after"),
        "recoveryUnlockPending": bool(status.get("recovery_unlock_pending", False)),
    }


def _ok(data: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"ok": True, "data": data or {}}


def _error(error: str) -> dict[str, Any]:
    return {"ok": False, "error": error}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="brake.desktop_bridge")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status")

    sub.add_parser("ensure-recovery")
    sub.add_parser("resume-lockout")

    enable = sub.add_parser("enable")
    enable.add_argument("--password", required=True)

    disable = sub.add_parser("disable")
    disable.add_argument("--password", required=True)

    reset_password = sub.add_parser("reset-password")
    reset_password.add_argument("--recovery-code", required=True)
    reset_password.add_argument("--new-password", required=True)

    set_duration = sub.add_parser("set-duration")
    set_duration.add_argument("--minutes", type=int, required=True)

    set_sensitivity = sub.add_parser("set-sensitivity")
    set_sensitivity.add_argument("--value", choices=["light", "balanced", "strict"], required=True)
    set_sensitivity.add_argument("--password", default="")

    set_anime_enabled = sub.add_parser("set-anime-enabled")
    set_anime_enabled.add_argument("--enabled", choices=["true", "false"], required=True)
    set_anime_enabled.add_argument("--password", default="")

    set_anime_mode = sub.add_parser("set-anime-mode")
    set_anime_mode.add_argument("--value", choices=["standard", "strict"], required=True)
    set_anime_mode.add_argument("--password", default="")

    sub.add_parser("anime-status")
    sub.add_parser("anime-download")

    set_commitment = sub.add_parser("set-commitment")
    set_commitment.add_argument("--until", required=True)
    set_commitment.add_argument("--password", required=True)

    test_lockout = sub.add_parser("test-lockout")
    test_lockout.add_argument("--seconds", type=int, default=10)

    try:
        args = parser.parse_args(argv)
        dev_mode = bool(os.environ.get("BRAKE_DESKTOP_DEV"))
        controller = Controller(
            allow_direct_writes=dev_mode,
            ipc_timeout_ms=2000,
        )
        _ensure_dev_state(controller)

        if args.cmd == "status":
            payload = _ok(_status_payload(controller))
        elif args.cmd == "ensure-recovery":
            ensure_first_run_state(controller.store)
            store = RecoveryStore()
            if store.exists():
                payload = _ok({"hasRecovery": True, "token": None})
            else:
                payload = _ok({"hasRecovery": True, "token": store.generate()})
        elif args.cmd == "resume-lockout":
            payload = _ok({"activeLockout": spawn_resume_lockout_if_needed("desktop-bridge")})
        elif args.cmd == "enable":
            ok, err = controller.enable(str(args.password))
            payload = _ok(_status_payload(controller)) if ok else _error(err)
        elif args.cmd == "disable":
            ok, err = controller.disable(str(args.password))
            payload = _ok(_status_payload(controller)) if ok else _error(err)
        elif args.cmd == "reset-password":
            ok, err = controller.reset_password_with_recovery(
                str(args.recovery_code),
                str(args.new_password),
            )
            payload = _ok(_status_payload(controller)) if ok else _error(err)
        elif args.cmd == "set-duration":
            ok, err = controller.set_duration(max(1, min(60, int(args.minutes))))
            payload = _ok(_status_payload(controller)) if ok else _error(err)
        elif args.cmd == "set-sensitivity":
            ok, err = controller.set_sensitivity(str(args.value), str(args.password or ""))
            payload = _ok(_status_payload(controller)) if ok else _error(err)
        elif args.cmd == "set-anime-enabled":
            ok, err = controller.set_anime_enabled(
                str(args.enabled).lower() == "true",
                str(args.password or ""),
            )
            payload = _ok(_status_payload(controller)) if ok else _error(err)
        elif args.cmd == "set-anime-mode":
            ok, err = controller.set_anime_mode(str(args.value), str(args.password or ""))
            payload = _ok(_status_payload(controller)) if ok else _error(err)
        elif args.cmd == "anime-status":
            payload = _ok({
                "animeModelStatus": anime_model_status(),
                "modelDir": str(model_dir()),
            })
        elif args.cmd == "anime-download":
            download_model()
            payload = _ok({
                "animeModelStatus": anime_model_status(),
                "modelDir": str(model_dir()),
            })
        elif args.cmd == "set-commitment":
            ok, err = controller.set_commitment(str(args.until), str(args.password))
            payload = _ok(_status_payload(controller)) if ok else _error(err)
        elif args.cmd == "test-lockout":
            seconds = max(1, min(60, int(args.seconds)))
            subprocess.Popen(
                lockout_command(["--duration", str(seconds), "--reason", "TEST", "--no-persist"]),
            )
            payload = _ok(_status_payload(controller))
        else:
            payload = _error("unknown_command")
    except PermissionError:
        payload = _error("permission_denied")
    except Exception as exc:
        payload = _error(str(exc) or exc.__class__.__name__)

    print(json.dumps(payload, separators=(",", ":")))
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
