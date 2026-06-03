# Threat Model

Brake is for self-accountability on Windows. It is meant to raise friction high enough that quitting is easier than bypassing.

## In Scope

- Detecting explicit screen content locally.
- Triggering lockouts and shutdown/probation flows.
- Preventing casual disable through the GUI.
- Blocking normal disable during Commitment Mode.
- Guarding uninstall while protection/commitment is active.
- Restarting the agent/service after simple process kills.
- Detecting tampered state files with HMAC signatures.

## Out Of Scope

- Stopping a determined Windows administrator forever.
- Blocking Safe Mode.
- Blocking boot from USB or another operating system.
- Blocking use of another device.
- Kernel-driver level controls.
- Network-level DNS filtering.
- Browser-extension filtering.

## Important Recovery Tradeoff

The per-install recovery code is a real escape hatch. It can bypass Commitment Mode. This is intentional for beta safety, because lockout software without recovery can become hostile if something breaks.

Users who want stricter accountability should store the recovery code with a trusted person or in a place that is hard to access impulsively.
