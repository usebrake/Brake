"""Runtime helpers for source and frozen executable launches."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    if frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def pythonw_path() -> str:
    exe = Path(sys.executable)
    if exe.name.lower() in {"python.exe", "pythonservice.exe"}:
        candidate = exe.with_name("pythonw.exe")
        return str(candidate) if candidate.exists() else str(exe)
    raw = str(exe)
    candidate = raw.replace("pythonservice.exe", "pythonw.exe").replace("python.exe", "pythonw.exe")
    return candidate if os.path.exists(candidate) else raw


def module_env() -> dict[str, str] | None:
    if frozen():
        return None
    return {"PYTHONPATH": str(app_dir())}


def module_command(module: str, *, windowless: bool = False) -> list[str]:
    exe = pythonw_path() if windowless else sys.executable
    return [exe, "-m", module]


def exe_command(
    exe_name: str,
    module: str,
    args: list[str] | None = None,
    *,
    windowless: bool = False,
) -> list[str]:
    args = args or []
    if frozen():
        candidate = app_dir() / exe_name
        if candidate.exists():
            return [str(candidate), *args]
    return [*module_command(module, windowless=windowless), *args]


def agent_command() -> list[str]:
    return exe_command("BrakeAgent.exe", "brake.agent", windowless=True)


def lockout_command(args: list[str] | None = None) -> list[str]:
    return exe_command("BrakeLockout.exe", "brake.lockout", args=args, windowless=True)


def service_command(args: list[str] | None = None) -> list[str]:
    return exe_command("BrakeService.exe", "brake.service", args=args)


def watchdog_command(args: list[str] | None = None) -> list[str]:
    return exe_command("BrakeWatchdog.exe", "brake.watchdog", args=args)


def boot_command(args: list[str] | None = None) -> list[str]:
    return exe_command("BrakeBoot.exe", "brake.boot", args=args, windowless=True)
