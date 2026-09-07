"""Runtime command selection for source vs packaged Brake launches."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _with_frozen_app(exe_dir: Path, fn) -> None:
    original_executable = sys.executable
    had_frozen = hasattr(sys, "frozen")
    original_frozen = getattr(sys, "frozen", None)
    try:
        sys.executable = str(exe_dir / "Brake.exe")
        sys.frozen = True  # type: ignore[attr-defined]
        fn()
    finally:
        sys.executable = original_executable
        if had_frozen:
            sys.frozen = original_frozen  # type: ignore[attr-defined]
        else:
            delattr(sys, "frozen")


def test_packaged_commands_use_brake_named_exes() -> None:
    from brake import runtime

    root = Path(tempfile.mkdtemp(prefix="brake-runtime-cmd-"))
    for exe in ("BrakeAgent.exe", "BrakeBoot.exe", "BrakeLockout.exe", "BrakeService.exe", "BrakeWatchdog.exe"):
        (root / exe).write_bytes(b"")

    def check() -> None:
        assert runtime.agent_command()[0].endswith("BrakeAgent.exe")
        assert runtime.boot_command()[0].endswith("BrakeBoot.exe")
        lockout = runtime.lockout_command(["--duration", "1"])
        assert lockout[0].endswith("BrakeLockout.exe")
        assert lockout[1:3] == ["--data-dir", str(runtime.paths.data_dir())]
        assert lockout[3:] == ["--duration", "1"]
        assert runtime.service_command(["debug"])[0].endswith("BrakeService.exe")
        assert runtime.watchdog_command(["debug"])[0].endswith("BrakeWatchdog.exe")

    _with_frozen_app(root, check)
    print("  [ok] packaged commands use Brake-named executables")


def test_lockout_command_pins_runtime_data_directory() -> None:
    from brake import runtime

    original = os.environ.get("BRAKE_DATA_DIR")
    data_dir = Path(tempfile.mkdtemp(prefix="brake-runtime-state-"))
    try:
        os.environ["BRAKE_DATA_DIR"] = str(data_dir)
        command = runtime.lockout_command(["--duration", "60"])
    finally:
        if original is None:
            os.environ.pop("BRAKE_DATA_DIR", None)
        else:
            os.environ["BRAKE_DATA_DIR"] = original

    assert command[-4:] == ["--data-dir", str(data_dir), "--duration", "60"]
    print("  [ok] lockout child receives the scanner's canonical data directory")


def test_packaged_autostart_uses_brake_boot_exe() -> None:
    from brake import autostart

    root = Path(tempfile.mkdtemp(prefix="brake-autostart-cmd-"))
    (root / "BrakeBoot.exe").write_bytes(b"")

    def check() -> None:
        cmd = autostart._build_command()
        assert "BrakeBoot.exe" in cmd
        assert "python" not in cmd.lower()

    _with_frozen_app(root, check)
    print("  [ok] packaged autostart uses BrakeBoot.exe")


def main() -> int:
    tests = [
        test_packaged_commands_use_brake_named_exes,
        test_lockout_command_pins_runtime_data_directory,
        test_packaged_autostart_uses_brake_boot_exe,
    ]
    for fn in tests:
        print(f"\n{fn.__name__}")
        fn()
    print("\nAll tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
