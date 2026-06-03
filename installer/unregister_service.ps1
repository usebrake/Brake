# Stop and remove both services. Must be elevated.
#
# Uninstall is free only when protection is disabled and Commitment Mode is
# not active. If protection is enabled, the user must enter the normal
# password or emergency recovery code. During Commitment Mode, only the
# emergency recovery code is accepted.
$ErrorActionPreference = "Continue"
$repoRoot = Split-Path -Parent $PSScriptRoot
$guardExe = Join-Path $repoRoot "LockItUpUninstallGuard.exe"
$serviceExe = Join-Path $repoRoot "LockItUpService.exe"
$watchdogExe = Join-Path $repoRoot "LockItUpWatchdog.exe"
$dataDir = Join-Path $env:ProgramData "LockItUp"
$agentPidFile = Join-Path $dataDir "agent.pid"
$frozenInstall = (Test-Path $serviceExe) -and (Test-Path $watchdogExe)
$python = $null
if (-not $frozenInstall) {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) { $python = $cmd.Path }
}

if ($frozenInstall -or $python) {
    Write-Host "Verifying uninstall is allowed..."
    if ($frozenInstall -and (Test-Path $guardExe)) {
        & $guardExe
    } else {
        & $python -m lockitup.uninstall_guard
    }
    $guardExit = $LASTEXITCODE
    if ($guardExit -ne 0) {
        Write-Host ""
        Write-Host "Uninstall refused (exit code $guardExit)."
        Write-Host "If protection is enabled, enter the password or emergency recovery code."
        Write-Host "If Commitment Mode is active, only the emergency recovery code is accepted."
        exit $guardExit
    }
    Write-Host "Uninstall authorized."
}

& sc.exe stop LockItUpWatchdog   | Out-Null
& sc.exe stop LockItUpService    | Out-Null
Start-Sleep -Seconds 2

if ($frozenInstall) {
    & $watchdogExe remove
    & $serviceExe remove
} elseif ($python) {
    & $python -m lockitup.watchdog remove
    & $python -m lockitup.service  remove
} else {
    & sc.exe delete LockItUpWatchdog
    & sc.exe delete LockItUpService
}

function Stop-AgentIfRunning {
    if (-not (Test-Path $agentPidFile)) { return }
    try {
        $agentPid = [int]((Get-Content -Raw -LiteralPath $agentPidFile).Trim())
    } catch {
        return
    }
    $proc = Get-Process -Id $agentPid -ErrorAction SilentlyContinue
    if (-not $proc) { return }

    Write-Host "Stopping remaining Brake agent process..."
    Stop-Process -Id $agentPid -Force -ErrorAction SilentlyContinue
    for ($i = 0; $i -lt 20; $i++) {
        Start-Sleep -Milliseconds 250
        if (-not (Get-Process -Id $agentPid -ErrorAction SilentlyContinue)) {
            return
        }
    }
}

function Stop-LockItUpUserProcesses {
    Write-Host "Closing remaining Brake GUI/agent processes..."
    try {
        $processes = Get-CimInstance Win32_Process |
            Where-Object {
                $_.Name -in @(
                    "python.exe",
                    "pythonw.exe",
                    "LockItUp.exe",
                    "LockItUpAgent.exe",
                    "LockItUpLockout.exe",
                    "LockItUpUninstallGuard.exe"
                )
            }
    } catch {
        Write-Warning "Could not enumerate user processes: $_"
        return
    }

    foreach ($proc in $processes) {
        if ($proc.ProcessId -eq $PID) { continue }
        $cmd = [string]$proc.CommandLine
        $exe = [string]$proc.ExecutablePath
        $isLockItUp =
            ($cmd.IndexOf("lockitup.gui", [StringComparison]::OrdinalIgnoreCase) -ge 0) -or
            ($cmd.IndexOf("lockitup.agent", [StringComparison]::OrdinalIgnoreCase) -ge 0) -or
            ($cmd.IndexOf("lockitup.lockout", [StringComparison]::OrdinalIgnoreCase) -ge 0) -or
            ($cmd.IndexOf("LockItUp", [StringComparison]::OrdinalIgnoreCase) -ge 0) -or
            ($exe.IndexOf("LockItUp", [StringComparison]::OrdinalIgnoreCase) -ge 0)

        if ($isLockItUp) {
            Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
        }
    }

    Start-Sleep -Seconds 1
}

function Remove-DataDir {
    if (-not (Test-Path $dataDir)) { return $true }
    for ($i = 0; $i -lt 10; $i++) {
        Remove-Item -LiteralPath $dataDir -Recurse -Force -ErrorAction SilentlyContinue
        if (-not (Test-Path $dataDir)) { return $true }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

Stop-AgentIfRunning
Stop-LockItUpUserProcesses

Write-Host "Removing login recovery autostart..."
Remove-ItemProperty `
    -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" `
    -Name "Brake" `
    -ErrorAction SilentlyContinue
Remove-ItemProperty `
    -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" `
    -Name "LockItUp" `
    -ErrorAction SilentlyContinue

Write-Host "Removing Start Menu shortcut..."
$shortcutDirs = @(
    (Join-Path $env:ProgramData "Microsoft\Windows\Start Menu\Programs\Brake"),
    (Join-Path $env:ProgramData "Microsoft\Windows\Start Menu\Programs\LockItUp")
)
foreach ($shortcutDir in $shortcutDirs) {
    if (Test-Path $shortcutDir) {
        Remove-Item -LiteralPath $shortcutDir -Recurse -Force
    }
}

Write-Host "Removing Brake local data..."
if (-not (Remove-DataDir)) {
    Write-Warning "Could not remove $dataDir because a file is still in use."
    Write-Warning "Restart Windows, then delete that folder manually."
}

Write-Host "Services and shortcut removed."
if (-not (Test-Path $dataDir)) {
    Write-Host "Local data removed."
}
Write-Host "PYTHONPATH machine env not cleared (intentional for source installs)."
Write-Host "You can now delete the Brake source/app folder if you want a full removal."
