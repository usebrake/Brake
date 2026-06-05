# Brake

Brake is a free source-available Windows beta for local screen accountability.

It watches the screen locally, detects explicit content, and triggers commitment-style lockouts. The code is public so people can inspect what it does, but this is **not open source** and not a polished consumer release yet. See [LICENSE](LICENSE).

## Screenshots

Screenshots are being refreshed for the new Brake UI.

## Current Status

This is a **source beta**.

For now, Brake is distributed from GitHub as source code. It includes a development launcher, but it is still not a polished one-click installer.

Do not download random `.exe` files claiming to be brake. There is no official public installer yet.

## Why Trust It?

- Runs locally on your Windows PC.
- No cloud account.
- No telemetry.
- No screenshots saved.
- Detection logs contain only labels, confidence values, and timing/debug data.
- The source is public so people can inspect the privacy and security behavior.

## What It Does

- Detects photographic nudity with NudeNet.
- Detects illustrated/anime NSFW content with a HuggingFace image classifier when optional dependencies are installed.
- Uses three sensitivity modes for partial nudity:
  - Light ignores partial nudity.
  - Balanced gives a short warning pause with cooldown.
  - Strict requires two matching scans, then uses escalating warning pauses.
- Hard explicit content triggers the full lockout path in every mode.
- Partial nudity never causes shutdown.
- Can shut down Windows after a hard lockout.
- Runs a short strict-watch window after reboot.
- Supports Commitment Mode so normal password disable is blocked until a chosen time.
- Provides a per-install emergency recovery code shown once.

## Honest Limits

Brake is a friction tool, not magic.

- A determined Windows admin can eventually bypass local software.
- Safe Mode, booting another OS, and using another device are outside the current protection model.
- False positives and missed detections are possible.
- The beta may be rough around setup, recovery, service behavior, and detection tuning.

## Install From GitHub ZIP

Brake is not a polished one-click installer yet, but the GitHub ZIP can still create the Start Menu app shortcut.

Before you start:

- Install **Python 3.11+ x64** from python.org.
- During Python install, check **Add python.exe to PATH**.
- Install **Node.js LTS** from nodejs.org.
- Install the **Microsoft Visual C++ Redistributable 2015-2022** if it is not already installed.

Then install Brake:

1. Click **Code** on GitHub.
2. Click **Download ZIP**.
3. Extract the ZIP somewhere normal, such as your Desktop.
4. Open the extracted folder. It may contain a nested folder named `brake-main`.
5. Open the folder that contains `installer\install.bat`.
6. Double-click `installer\install.bat`.
7. Approve the Windows admin prompt.
8. Open **Brake** from the Windows Start Menu.

The install script sets up the background services and creates the Start Menu shortcut. In the current source beta, that shortcut opens the Electron development launcher. It installs desktop dependencies the first time, then starts Brake.

If the Start Menu shortcut does not appear, open the same folder and double-click `start-brake-dev.bat`.

## Developer Install

Requirements:

- Windows 10/11 x64
- Python 3.11+ x64
- Visual C++ Redistributable 2015-2022

Install dependencies:

```powershell
pip install -r requirements.txt
```

Install the Windows services from an elevated terminal:

```powershell
.\installer\install.bat
```

Open Brake for development:

```powershell
.\start-brake-dev.bat
```

Uninstall:

```powershell
.\installer\uninstall.bat
```

The uninstaller is free only when protection is disabled and Commitment Mode is not active.

If protection is enabled without an active commitment, uninstall requires the normal password. The emergency recovery code starts a 10-minute cooldown first.

During an active commitment, uninstall cannot happen immediately. The emergency recovery code starts the 10-minute cooldown; after protection turns off, uninstall can continue. The normal password is not enough, because Commitment Mode is meant to prevent ordinary password disable.

After uninstall, the Windows services, Start Menu shortcut, and local Brake data are removed. You can then delete the extracted source/app folder.

## Test Mode

Test mode compresses timers and skips real shutdown:

```cmd
set BRAKE_TEST_MODE=1
python -m brake.agent
```

Use it to test the detection -> lockout -> shutdown/probation path without losing your session.

## Recovery Code

On first GUI launch, Brake generates a unique emergency recovery code and shows it once.

The recovery code can reset your password immediately. It can also start a 10-minute emergency cooldown to turn Brake off on that machine, including during Commitment Mode.

Do not save it somewhere easy to reach on the same computer. Write it down, take a photo on your phone, or give it to someone you trust. If you want the strongest commitment, you can choose not to copy it, but then a forgotten password may require a full reset.

## Packaging Status

Packaging scripts exist under `packaging/`, but packaging is experimental and not the current public launch path.

Important: this project currently uses PyQt6. Do not publish a proprietary/source-available installer until the PyQt6 commercial/GPL licensing question is resolved or the GUI is ported to a suitable alternative such as PySide6.

## What Happens If The GUI Closes?

After install, the GUI is only the control panel. The background service and agent do the actual screen watching.

- Closing the GUI does not stop protection.
- Pressing Ctrl+C in the development launcher stops the source-mode desktop app and its dev agent.
- Killing the GUI process only closes the GUI.
- If the agent process is killed, the Windows service should start it again.
- If both Brake Windows services are stopped by an administrator, background protection stops until the services are started again or Windows restarts.

## Development Tests

```powershell
python -m tests.test_state
python -m tests.test_ipc
python -m tests.test_escalation
python -m tests.test_test_mode
python -m tests.test_sensitivity
python -m tests.test_uninstall_guard
```

## Feedback Wanted

Please use the GitHub issue templates for:

- install problems
- false positives
- missed detections
- confusing recovery/commitment behavior
- bugs

Do not attach explicit screenshots, passwords, or recovery codes.

## Third-Party Notices

See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for current beta dependency/model license notes.
