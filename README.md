# Brake

**Local screen accountability for Windows.**

Brake is a free source-available Windows beta for local screen accountability. It checks your screen locally, detects explicit content, and triggers lockouts designed to interrupt the session before it becomes automatic.

The code is public so people can inspect what it does. Brake is **not open source** and not a polished consumer release yet. See [LICENSE](LICENSE).

## Current Status

Brake is a Windows beta with a normal installer.

Download the installer only from the official GitHub release or the Brake website. The source is public for review, but normal users do not need to install from source.

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
- Optionally detects illustrated explicit content with a separate local model.
- Treats clear explicit content as a full lockout.
- Incidental nudity does not create a short warning lockout.
- Shuts down Windows after a full lockout by default. This can be changed in Advanced when you are not in a commitment.
- Remembers full lockouts for 24 hours so repeated incidents can make the next lockout longer.
- Supports Commitment Mode so your password cannot turn protection off early.
- Shows a per-install recovery code once on first launch.

## Honest Limits

Brake adds friction. It is not magic.

- A determined Windows administrator can eventually bypass local software.
- Safe Mode, another operating system, another device, or deleting source files are outside the current beta protection model.
- False positives and missed detections are possible.

## Install

Read the install guide first: [docs/INSTALL.md](docs/INSTALL.md).

Short version:

1. Download `BrakeSetup.exe` from the latest GitHub release.
2. Double-click the installer.
3. Approve the Windows admin prompt.
4. Open Brake from the installer, desktop shortcut, or Start Menu.
5. Save your recovery code on first launch.
6. Turn on protection and set your password.

Download:

[BrakeSetup.exe](https://github.com/usebrake/Brake/releases/latest/download/BrakeSetup.exe)

After install, the downloaded installer is no longer the app. Brake runs from `C:\Program Files\Brake`, so you can delete `BrakeSetup.exe`.

If Windows search does not show Brake immediately, open `C:\Program Files\Brake\Brake.exe` or run the Start Menu shortcut at `C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Brake.lnk`.

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

The recovery code can reset your password immediately. It can also start an emergency cooldown before Brake turns protection off, including during Commitment Mode. The default cooldown is 15 minutes and can be changed in Advanced.

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

For development/source install checks:

```powershell
.\scripts\check_source_install.ps1
```

## Development Tests

```powershell
python -m tests.test_state
python -m tests.test_ipc
python -m tests.test_incident_memory
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
