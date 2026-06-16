# Install Brake for Windows

Brake installs like a normal Windows app. The setup file includes everything normal users need.

## Download

Download the latest Windows installer:

[Download BrakeSetup.exe](https://github.com/usebrake/Brake/releases/latest/download/BrakeSetup.exe)

You can also view the public source code on GitHub:

[View source on GitHub](https://github.com/usebrake/Brake)

## Install steps

1. Download `BrakeSetup.exe`.
2. Double-click the installer.
3. Approve the Windows admin prompt.
4. Follow the installer window.
5. Launch Brake from the installer, desktop shortcut, or Start Menu.
6. On first launch, save your recovery code.
7. Turn on protection and set your password.

The installer copies Brake to:

```text
C:\Program Files\Brake
```

Brake stores local settings, logs, recovery state, and optional model files in:

```text
C:\ProgramData\Brake
```

You can delete the downloaded `BrakeSetup.exe` after installation.

## Updating Brake

Download the newest `BrakeSetup.exe` and run it again.

The installer stops the old Brake services, replaces the app files, re-registers the services, and keeps your existing local settings in `C:\ProgramData\Brake`.

Do not update while you are in an active lockout or commitment unless you intentionally want to interrupt the running installed app.

## If Brake is not in the Start Menu

Windows search can take a moment to notice new shortcuts. Try opening Brake directly:

```text
C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Brake.lnk
C:\Users\<you>\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Brake.lnk
C:\Program Files\Brake\Brake.exe
```

If those files are missing, run the latest `BrakeSetup.exe` again and approve the admin prompt.

## Development install

The source repository still includes development scripts for contributors. Normal users should use `BrakeSetup.exe`.
