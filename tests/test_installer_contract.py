"""Static checks for installer failure gates that must run before setup completes."""
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]


def test_update_stop_failure_blocks_prepare_to_install() -> None:
    script = (_REPO_ROOT / "packaging" / "Brake.iss").read_text(encoding="utf-8")

    prepare = script.split("function PrepareToInstall", 1)[1].split("function ServiceIsRegistered", 1)[0]
    assert "if not Exec(" in prepare
    assert "if ResultCode <> 0 then" in prepare
    assert "Setup has been stopped before any files were replaced." in prepare


def test_setup_verifies_both_registered_services() -> None:
    installer = (_REPO_ROOT / "packaging" / "Brake.iss").read_text(encoding="utf-8")
    register = (_REPO_ROOT / "installer" / "register_service.ps1").read_text(encoding="utf-8")

    registration_gate = installer.split("procedure RegisterAndVerifyBrakeServices", 1)[1]
    assert "if not Exec(" in registration_gate
    assert "if ResultCode <> 0 then" in registration_gate
    assert "VerifyBrakeServices;" in registration_gate
    assert "if CurStep = ssPostInstall then" in registration_gate
    verify = installer.split("procedure VerifyBrakeServices", 1)[1]
    assert "ServiceIsRegistered('BrakeService')" in verify
    assert "ServiceIsRegistered('BrakeWatchdog')" in verify
    assert "RaiseException(" in verify
    assert 'Assert-ServiceRegistered "BrakeService"' in register
    assert 'Assert-ServiceRegistered "BrakeWatchdog"' in register


if __name__ == "__main__":
    test_update_stop_failure_blocks_prepare_to_install()
    test_setup_verifies_both_registered_services()
    print("Installer contract tests passed.")
