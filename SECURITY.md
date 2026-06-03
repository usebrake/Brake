# Security Policy

Brake is a local accountability tool. It is designed to add friction, not to be impossible for a determined administrator to bypass.

## Reporting A Security Issue

For now, open a GitHub issue with the "Security concern" wording in the title, but do not include private screenshots, recovery codes, or passwords. If the project later gets a public email address, this file should be updated with private reporting instructions.

## What Brake Logs

Brake may log:

- detector name
- detector label
- confidence value
- scan timing
- capture dimensions and mean color
- service/agent startup and errors

Brake should not log:

- screenshots
- image bytes
- passwords
- recovery-code plaintext
- private screen text

## Known Security Limits

- A Windows admin can eventually bypass local software.
- Safe Mode and external boot media are outside the current protection model.
- Another device is outside the protection model.
- Unsigned beta builds may trigger Windows SmartScreen warnings.

See [THREAT_MODEL.md](THREAT_MODEL.md) for details.
