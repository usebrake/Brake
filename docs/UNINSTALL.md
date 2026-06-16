# Uninstall Brake

Use the installed uninstaller. Do not delete the installed folder first.

## Normal uninstall

If protection is off and no commitment is active:

1. Open Windows Settings.
2. Go to Apps > Installed apps.
3. Find Brake and choose Uninstall.
4. Approve the Windows admin prompt.
5. Wait for the script to finish.

The uninstaller removes the services, Start Menu shortcut, local Brake data, recovery code, and the installed app folder.

If uninstall cannot remove local data, it now fails loudly. Do not reinstall yet if it says uninstall is incomplete. Restart Windows, run uninstall again, and wait for `Local data removed, including recovery code and state files.`

You can also run the installed uninstaller directly from `C:\Program Files\Brake`.

## If protection is on

If protection is on without an active commitment, uninstall requires your password.

If you use the recovery code instead, Brake starts the configured emergency cooldown. After the cooldown finishes, protection turns off and uninstall can continue.

## If commitment is active

Your normal password cannot uninstall during commitment.

The recovery code can start the configured emergency cooldown. When the cooldown finishes, Brake turns protection off and clears the commitment so uninstall can continue.

## If Windows says a file is in use

Close the Brake window from the tray menu, then run uninstall again.

If a Brake process is still holding a file, restart Windows and run uninstall before opening Brake again.
