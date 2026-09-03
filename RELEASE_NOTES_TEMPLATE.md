# Brake v0.1.5-beta Windows Beta

Free source-available Windows technical beta.

## What changed

- Emergency recovery cooldowns are now honored immediately by read-only detection processes when they expire.
- Starting or extending a commitment now cancels any pending emergency unlock, and the desktop app explains that consequence before confirmation.
- Setup now stops with an error when update preparation, service registration, or required-service verification fails.
- Install, uninstall, shutdown, feedback, and checksum guidance now match the implemented beta behavior.
- The production Browserslist dependency chain is updated to `4.28.8`.

## Current Distribution

Download `BrakeSetup.exe` from this release. The setup file includes everything normal users need.

The optional Illustrated detector downloads `BrakeIllustratedDetector.zip` from this release when enabled inside the app. You do not need to download it manually.

## Install

1. Download `BrakeSetup.exe`.
2. Double-click the installer.
3. Approve the Windows admin prompt.
4. Open Brake from the installer, desktop shortcut, or Start Menu.
5. Save your recovery code on first launch.

The installer sets up the background services and creates shortcuts. Verify `BrakeSetup.exe` against the `SHA256SUMS.txt` file included with the same release before running setup.

## Known Beta Warnings

- Windows may show a SmartScreen warning because the beta installer is not code-signed yet.
- Optional Illustrated detector setup may take time while the app downloads the local model package.
- False positives and missed detections are possible.
- This is a friction tool, not an impossible-to-bypass security product.

## Feedback Wanted

- Install failures.
- Missed explicit content.
- False positives.
- Confusing recovery or commitment behavior.
- Uninstall problems.
