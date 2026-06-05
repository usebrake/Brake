# Troubleshooting

## Brake is not in the Start Menu

Run installer\install.bat again from the folder that contains it.

If it still does not appear, double-click start-brake-dev.bat from the Brake folder.

## start-brake-dev.bat does not work

Make sure Node.js LTS is installed.

Then run:

```powershell
.\scripts\doctor.ps1
```

Copy the output into a GitHub install issue.

## The app opens but protection does not work

Run installer\install.bat as administrator again. The background services need to be installed and running.

You can check them with:

```powershell
sc query BrakeService
sc query BrakeWatchdog
```

## The anime detector says missing dependencies

Run installer\install.bat again. It installs Python dependencies into the system Python used by the service.

## Uninstall is blocked

If protection is on, enter your password.

If commitment is active, use your recovery code and wait for the emergency cooldown.

## Windows says a file is in use

Restart Windows. Then run installer\uninstall.bat before opening Brake.

## I found a false positive or missed detection

Open a GitHub issue using the false positive or missed detection template.

Do not attach explicit screenshots. Describe the content type and include detector labels/confidence if you have logs.
