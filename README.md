# Brake

**Local screen accountability for Windows.**

Brake is a free source-available Windows beta for local screen accountability. It checks your screen locally, detects explicit content, and triggers lockouts designed to interrupt the session before it becomes automatic.

The code is public so people can inspect what it does. Brake is **not open source** and not a polished consumer release yet. See [LICENSE](LICENSE).

## Current Status

Brake is a **source beta**.

There is no official public one-click installer yet. Do not download random `.exe` files claiming to be Brake.

The current GitHub version installs from source. The install script copies Brake to `C:\Program Files\Brake`, builds the desktop app, creates a Start Menu shortcut, and registers the background services.

## Why Trust It?

- Runs locally on your Windows PC.
- No cloud account.
- No telemetry.
- No screenshots saved.
- No screenshots uploaded.
- Detection logs contain labels, confidence values, and timing/debug data only.
- The source is public for privacy and security review.

## Screenshots

Screenshots are being refreshed for the new Brake UI.

## What Brake Does

- Detects real photo/video explicit content with NudeNet.
- Optionally detects illustrated/anime NSFW content with a separate local model.
- Offers Light, Balanced, and Strict sensitivity.
- Treats clear explicit content as a full lockout.
- In Balanced mode, warns on nudity first, then escalates repeated nudity to a full lockout.
- Shuts down Windows after a full lockout.
- Runs a five-minute strict-watch window after restart.
- Supports Commitment Mode so your password cannot turn protection off early.
- Shows a per-install recovery code once on first launch.

## Honest Limits

Brake adds friction. It is not magic.

- A determined Windows administrator can eventually bypass local software.
- Safe Mode, another operating system, another device, or deleting source files are outside the current beta protection model.
- False positives and missed detections are possible.
- Source installs are still rougher than a packaged app.

## Install

Read the simple install guide first: [docs/INSTALL.md](docs/INSTALL.md).

Short version:

1. Install Python 3.11+ x64.
2. Install Node.js LTS.
3. Download this repo as a ZIP from GitHub.
4. Extract it.
5. Open the folder that contains `installer\install.bat`.
6. Double-click `installer\install.bat`.
7. Approve the Windows admin prompt.
8. At the end of install, choose whether to open Brake now.
9. Later, open Brake from the Windows Start Menu by searching for `Brake`.

After install, the downloaded ZIP/extracted folder is no longer the app. Brake runs from `C:\Program Files\Brake`, so you can delete the downloaded folder.

If Windows search does not show Brake immediately, open `C:\Program Files\Brake\start-brake.vbs` or run the Start Menu shortcut at `C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Brake.lnk`.

## User Guide

Start here: [docs/USER_GUIDE.md](docs/USER_GUIDE.md).

Helpful docs:

- [Install](docs/INSTALL.md)
- [Uninstall](docs/UNINSTALL.md)
- [Recovery code](docs/RECOVERY_CODE.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [FAQ](docs/FAQ.md)

## Recovery Code

Brake shows a recovery code once on first launch.

The recovery code can reset your password immediately. It can also start a 15-minute emergency cooldown before Brake turns protection off, including during Commitment Mode.

Do not store it somewhere easy to reach on the same computer if you want strong commitment. Write it down, take a photo on your phone, or give it to someone you trust.

## What Happens If The App Closes?

After install, the desktop app is the control panel. The background services and agent do the screen checking.

- Closing the app window does not stop protection.
- Killing only the GUI closes only the GUI.
- If the agent process is killed, the Windows service should restart it.
- If both Brake Windows services are stopped by an administrator, background protection stops until the services are started again or Windows restarts.
- In development mode, pressing Ctrl+C in the launcher can stop the development desktop process.

## Diagnostics

Run:

```powershell
.\scripts\doctor.ps1
```

For source install checks:

```powershell
.\scripts\check_source_install.ps1
```

## Development Tests

```powershell
python -m tests.test_state
python -m tests.test_ipc
python -m tests.test_escalation
python -m tests.test_test_mode
python -m tests.test_sensitivity
python -m tests.test_uninstall_guard
```

Desktop build:

```powershell
cd desktop
npm run build
```

## Feedback Wanted

Please use the GitHub issue templates for install problems, false positives, missed detections, recovery/commitment confusion, and bugs.

Do not attach explicit screenshots, passwords, or recovery codes.

## Third-Party Notices

See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for current beta dependency/model license notes.
