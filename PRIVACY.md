# Privacy

Brake is designed to run locally.

## Data That Stays On Your PC

- State: `C:\ProgramData\Brake\state.json`
- Machine key: `C:\ProgramData\Brake\state.key`
- Recovery token hash: `C:\ProgramData\Brake\recovery.json`
- Lockout and incident memory records
- Logs

## Network

The app does not send telemetry or screenshots to a server.

Brake may download model files during first use or installation, depending on the feature:

- NudeNet model assets
- `BrakeIllustratedDetector.zip` from the official Brake GitHub release when you install the optional Illustrated detector

These downloads are model assets only. They are not screenshots or user activity.

## Screenshots

Brake captures the screen in memory to run detection. Screenshots are discarded after scanning and should never be written to disk.

## Recovery Code

The emergency recovery code is shown once. Only an Argon2 hash is stored locally. The plaintext code is not recoverable from Brake after the dialog closes.
