# Install Brake From GitHub

Brake is currently a source beta. GitHub gives you the code, and the install script turns that source folder into an installed Windows app.

There is no official one-click public installer yet.

## Requirements

Install these first:

- Python 3.11+ x64 from python.org
- Node.js LTS from nodejs.org
- Microsoft Visual C++ Redistributable 2015-2022

When installing Python, check Add python.exe to PATH.

## Install steps

1. On GitHub, click Code.
2. Click Download ZIP.
3. Extract the ZIP to your Desktop or another normal folder.
4. Open the extracted folder.
5. If you see a folder named brake-main, open that folder.
6. Open the folder that contains installer\install.bat.
7. Double-click installer\install.bat.
8. Approve the Windows admin prompt.
9. Wait for the script to finish.
10. When it asks `Open Brake now?`, press Enter to open it or type `n` to skip.
11. Later, open Brake from the Windows Start Menu by searching for `Brake`.

The installer copies Brake to:

```text
C:\Program Files\Brake
```

It also builds the desktop app, creates the Start Menu shortcut, registers the background services, and makes installed app files read-only for standard users.

After install, you can delete the downloaded ZIP/extracted folder. Do not delete `C:\Program Files\Brake` unless you are uninstalling.

## If Brake is not in the Start Menu

Windows search can take a moment to notice new shortcuts. First try these:

```text
C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Brake.lnk
C:\Users\<you>\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Brake.lnk
C:\Program Files\Brake\start-brake.vbs
```

If none of those exist, run installer\install.bat again from the extracted Brake source folder.

If that fails, run:

```powershell
.\scripts\doctor.ps1
```

Then copy the output into a GitHub install issue.

## Running without installing

For development only, you can still run:

```powershell
.\start-brake-dev.bat
```

That uses development mode and is not the same as the installed app.
