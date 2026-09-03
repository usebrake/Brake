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

The uninstaller does not accept your password or recovery code. It blocks uninstall until protection is already off.

1. Open Brake.
2. Use your password to turn protection off.
3. Run the uninstaller again.

If you cannot use your password, enter your recovery code inside Brake to start the configured emergency cooldown. Wait for the cooldown to finish and protection to turn off, then run the uninstaller again.

## If commitment is active

Your normal password cannot turn protection off during commitment, and the uninstaller remains blocked.

Open Brake and use your recovery code to start the configured emergency cooldown. When the cooldown finishes, Brake turns protection off and clears the commitment. Then run the uninstaller again.

## If Windows says a file is in use

Close the Brake window from the tray menu, then run uninstall again.

If a Brake process is still holding a file, restart Windows and run uninstall before opening Brake again.
