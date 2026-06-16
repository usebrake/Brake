"""Runtime command selection for source vs packaged Brake launches."""
from __future__ import annotations

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
        assert runtime.lockout_command(["--duration", "1"])[0].endswith("BrakeLockout.exe")
        assert runtime.lockout_command(["--duration", "1"])[1:] == ["--duration", "1"]
        assert runtime.service_command(["debug"])[0].endswith("BrakeService.exe")
        assert runtime.watchdog_command(["debug"])[0].endswith("BrakeWatchdog.exe")

    _with_frozen_app(root, check)
    print("  [ok] packaged commands use Brake-named executables")


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
        test_packaged_autostart_uses_brake_boot_exe,
    ]
    for fn in tests:
        print(f"\n{fn.__name__}")
        fn()
    print("\nAll tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
