# Privacy

Brake is designed to run locally.

## Data That Stays On Your PC

- State: `C:\ProgramData\\brake\\state.json`
- Machine key: `C:\ProgramData\\brake\\state.key`
- Recovery token hash: `C:\ProgramData\\brake\\recovery.json`
- Lockout/probation records
- Logs

## Network

The app does not send telemetry or screenshots to a server.

Some ML dependencies may download model files during first use or installation, depending on your environment:

- NudeNet model assets
- HuggingFace `Falconsai/nsfw_image_detection` model for illustrated/anime NSFW detection

These model downloads come from the dependency providers, not a Brake backend.

## Screenshots

Brake captures the screen in memory to run detection. Screenshots are discarded after scanning and should never be written to disk.

## Recovery Code

The emergency recovery code is shown once. Only an Argon2 hash is stored locally. The plaintext code is not recoverable from brake after the dialog closes.
