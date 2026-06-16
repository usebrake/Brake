# Troubleshooting

## Brake is not in the Start Menu

Windows search can take a moment to index new shortcuts. Try opening Brake directly:

```text
C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Brake.lnk
C:\Users\<you>\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Brake.lnk
C:\Program Files\Brake\Brake.exe
```

If those files are missing, run the latest `BrakeSetup.exe` again and approve the admin prompt.

The installed app should be here:

```text
C:\Program Files\Brake
```

## The downloaded installer was deleted

That is okay after install. Brake runs from `C:\Program Files\Brake`.

If `C:\Program Files\Brake` was deleted, reinstall by running the latest `BrakeSetup.exe`.

## BrakeSetup.exe does not finish installing

Restart Windows, then run the latest `BrakeSetup.exe` again and approve the admin prompt.

If it still fails, open a GitHub install issue and include anything useful from:

```text
C:\ProgramData\Brake\logs\
```

## The Start Menu shortcut opens nothing

Check:

```text
C:\ProgramData\Brake\logs\desktop-launch.log
```

## The app opens but protection does not work

Run the latest `BrakeSetup.exe` again and approve the admin prompt. The background services need to be installed and running.

You can check them with:

```powershell
sc query BrakeService
sc query BrakeWatchdog
```

## The illustrated detector does not install

Run the latest `BrakeSetup.exe` again. If the issue remains, open a GitHub issue and include the model status shown in the Illustrated tab.

## Uninstall is blocked

If protection is on, enter your password.

If commitment is active, use your recovery code and wait for the emergency cooldown.

## Windows says a file is in use

Restart Windows. Then run the uninstaller before opening Brake again.

## Old recovery code still works after reinstall

That means local data survived uninstall. Run the installed uninstaller again as administrator.

Do not reinstall until the uninstall window says `Local data removed, including recovery code and state files.`

## I found a false positive or missed detection

Open a GitHub issue using the false positive or missed detection template.

Do not attach explicit screenshots. Describe the content type and include detector labels/confidence if you have logs.
