# Install Brake From GitHub

Brake is currently a source beta. That means GitHub gives you the code, and the install script sets up the app on your computer.

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
10. Open Brake from the Windows Start Menu.

On first launch, Brake may install desktop dependencies. That can take a little time.

## If Brake is not in the Start Menu

Open the extracted Brake folder and double-click start-brake-dev.bat.

If that fails, run:

```powershell
.\scripts\doctor.ps1
```

Then copy the output into a GitHub install issue.

## Important source beta note

Do not move or delete the extracted Brake folder after installing. Source installs still depend on that folder. A packaged installer will remove this rough edge later.
