# TODO: milestone 9
# icacls C:\Program Files\LockItUp /inheritance:r /grant:r "SYSTEM:(OI)(CI)F" "Administrators:(OI)(CI)F" "Users:(OI)(CI)RX"
# Deny write to state.json + state.key for everyone except SYSTEM + Administrators.
Write-Host "set_acls.ps1 not implemented yet"
exit 1
