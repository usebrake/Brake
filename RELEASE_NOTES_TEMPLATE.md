# Brake v0.1.3-beta Source Preview

Free source-available Windows technical beta.

## Current Distribution

There is no official public installer yet. This release is GitHub ZIP first for source beta testers.

## Install From GitHub ZIP

Before you start, install Python 3.11+ x64 from python.org and check **Add python.exe to PATH**.

1. Download the ZIP from GitHub: Code -> Download ZIP.
2. Extract it.
3. Double-click `installer\install.bat`.
4. Approve the Windows admin prompt.
5. Open Brake from the Windows Start Menu.

The install script sets up the background services and creates the Start Menu shortcut.

## Developer Install

```powershell
pip install -r requirements.txt
.\installer\install.bat
```

## Known Beta Warnings

- This is not a polished consumer installer.
- First detection model setup may take time or download model assets.
- False positives and missed detections are possible.
- This is a friction tool, not an impossible-to-bypass security product.

## Feedback Wanted

- Install failures.
- Missed explicit content.
- False positives.
- Confusing recovery or commitment behavior.
- Uninstall problems.
