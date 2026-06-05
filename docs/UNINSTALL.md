# Uninstall Brake

Use the uninstall script. Do not delete the installed folder first.

## Normal uninstall

If protection is off and no commitment is active:

1. Open `C:\Program Files\Brake`.
2. Double-click installer\uninstall.bat.
3. Approve the Windows admin prompt.
4. Wait for the script to finish.

The uninstaller removes the services, Start Menu shortcut, local Brake data, and the installed app folder.

You can also run installer\uninstall.bat from your original downloaded source folder. If Brake is installed, it forwards uninstall to `C:\Program Files\Brake`.

## If protection is on

If protection is on without an active commitment, uninstall requires your password.

If you use the recovery code instead, Brake starts a 10-minute emergency cooldown. After the cooldown finishes, protection turns off and uninstall can continue.

## If commitment is active

Your normal password cannot uninstall during commitment.

The recovery code can start a 10-minute emergency cooldown. When the cooldown finishes, Brake turns protection off and clears the commitment so uninstall can continue.

## If Windows says a file is in use

Close the Brake window from the tray menu, then run uninstall again.

If a Python, Node, or Electron process is still holding a file, restart Windows and run installer\uninstall.bat before opening Brake again.