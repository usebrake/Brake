# Launch Checklist

## Before making the repo public

- Add current Brake screenshots.
- Run scripts\doctor.ps1.
- Run the Python tests.
- Run npm run build in desktop.
- Build the Windows installer.
- Confirm README install steps work from `BrakeSetup.exe`.
- Upload `BrakeSetup.exe`, the versioned installer, and `SHA256SUMS.txt` to the GitHub release.
- Confirm uninstall works when protection is off.
- Confirm uninstall is blocked or delayed when protection or commitment is active.
- Confirm recovery code reset and emergency cooldown work.

## Before asking for beta testers

- Make GitHub profile and repo branding match Brake.
- Add a clean repo avatar.
- Keep README short and honest.
- Add known limitations.
- Add feedback issue templates.
- Do one clean install on your own PC.
- Do one install on another Windows machine or VM.

## First beta post

- Disclose that you built Brake.
- Lead with privacy and local-only behavior.
- Be clear that it is a Windows beta.
- Ask for testers, not customers.
- Do not claim it is impossible to bypass.
- Do not attach explicit screenshots.

## Release quality bar

Ship when a non-technical tester can install, enable protection, trigger a test lockout, and uninstall without you coaching every step.
