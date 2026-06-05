# Stop and remove both services. Must be elevated.
#
# Uninstall is free only when protection is disabled and Commitment Mode is
# not active. If protection is enabled, the user must enter the normal
# password or emergency recovery code. During Commitment Mode, only the
# emergency recovery code is accepted.
$ErrorActionPreference = "Continue"
$repoRoot = Split-Path -Parent $PSScriptRoot
$installRoot = Join-Path $env:ProgramFiles "Brake"
$guardExe = Join-Path $repoRoot "BrakeUninstallGuard.exe"
$serviceExe = Join-Path $repoRoot "BrakeService.exe"
$watchdogExe = Join-Path $repoRoot "BrakeWatchdog.exe"
$dataDir = Join-Path $env:ProgramData "Brake"
$agentPidFile = Join-Path $dataDir "agent.pid"
$frozenInstall = (Test-Path $serviceExe) -and (Test-Path $watchdogExe)
$python = $null

function Same-Path($a, $b) {
    try {
        $ra = (Resolve-Path $a -ErrorAction Stop).Path.TrimEnd('\')
    } catch {
        $ra = [System.IO.Path]::GetFullPath($a).TrimEnd('\')
    }
    try {
        $rb = (Resolve-Path $b -ErrorAction Stop).Path.TrimEnd('\')
    } catch {
        $rb = [System.IO.Path]::GetFullPath($b).TrimEnd('\')
    }
    return [string]::Equals($ra, $rb, [StringComparison]::OrdinalIgnoreCase)
}

$installedUnregister = Join-Path $installRoot "installer\unregister_service.ps1"
if (-not (Same-Path $repoRoot $installRoot) -and (Test-Path $installedUnregister)) {
    Write-Host "Forwarding uninstall to installed Brake app: $installRoot"
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $installedUnregister
    exit $LASTEXITCODE
}

if (-not $frozenInstall) {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) { $python = $cmd.Path }
}

if ($frozenInstall -or $python) {
    Write-Host "Verifying uninstall is allowed..."
    if ($frozenInstall -and (Test-Path $guardExe)) {
        & $guardExe
    } else {
        & $python -m brake.uninstall_guard
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

& sc.exe stop BrakeWatchdog   | Out-Null
& sc.exe stop BrakeService    | Out-Null
Start-Sleep -Seconds 2

if ($frozenInstall) {
    & $watchdogExe remove
    & $serviceExe remove
} elseif ($python) {
    & $python -m brake.watchdog remove
    & $python -m brake.service  remove
} else {
    & sc.exe delete BrakeWatchdog
    & sc.exe delete BrakeService
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

function Stop-BrakeUserProcesses {
    Write-Host "Closing remaining Brake GUI/agent processes..."
    try {
        $processes = Get-CimInstance Win32_Process |
            Where-Object {
                $_.Name -in @(
                    "python.exe",
                    "pythonw.exe",
                    "electron.exe",
                    "node.exe",
                    "brake.exe",
                    "BrakeAgent.exe",
                    "BrakeLockout.exe",
                    "BrakeUninstallGuard.exe",
                    "wscript.exe"
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
        $isBrake =
            ($cmd.IndexOf("brake.", [StringComparison]::OrdinalIgnoreCase) -ge 0) -or
            ($cmd.IndexOf("start-brake", [StringComparison]::OrdinalIgnoreCase) -ge 0) -or
            ($cmd.IndexOf($repoRoot, [StringComparison]::OrdinalIgnoreCase) -ge 0) -or
            ($cmd.IndexOf($installRoot, [StringComparison]::OrdinalIgnoreCase) -ge 0) -or
            ($cmd.IndexOf($dataDir, [StringComparison]::OrdinalIgnoreCase) -ge 0) -or
            ($exe.IndexOf($repoRoot, [StringComparison]::OrdinalIgnoreCase) -ge 0) -or
            ($exe.IndexOf($installRoot, [StringComparison]::OrdinalIgnoreCase) -ge 0)

        if ($isBrake) {
            Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
        }
    }

    Start-Sleep -Seconds 1
}

function Remove-SensitiveDataFiles {
    if (-not (Test-Path $dataDir)) { return $true }

    $sensitivePatterns = @(
        "state.json",
        "state.key",
        "state.initialized",
        "recovery.json",
        "state.json.*.tmp",
        "recovery.json.*.tmp"
    )

    for ($i = 0; $i -lt 20; $i++) {
        foreach ($pattern in $sensitivePatterns) {
            Get-ChildItem -LiteralPath $dataDir -Filter $pattern -Force -ErrorAction SilentlyContinue |
                ForEach-Object {
                    Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue
                }
        }

        $remaining = @()
        foreach ($pattern in $sensitivePatterns) {
            $remaining += @(Get-ChildItem -LiteralPath $dataDir -Filter $pattern -Force -ErrorAction SilentlyContinue)
        }
        if ($remaining.Count -eq 0) { return $true }

        Stop-AgentIfRunning
        Stop-BrakeUserProcesses
        Start-Sleep -Milliseconds 500
    }

    return $false
}

function Remove-DataDir {
    if (-not (Test-Path $dataDir)) { return $true }

    for ($i = 0; $i -lt 20; $i++) {
        Remove-Item -LiteralPath $dataDir -Recurse -Force -ErrorAction SilentlyContinue
        if (-not (Test-Path $dataDir)) { return $true }
        Stop-AgentIfRunning
        Stop-BrakeUserProcesses
        Start-Sleep -Milliseconds 500
    }
    return $false
}

Stop-AgentIfRunning
Stop-BrakeUserProcesses

Write-Host "Removing login recovery autostart..."
Remove-ItemProperty `
    -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" `
    -Name "Brake" `
    -ErrorAction SilentlyContinue

Write-Host "Removing Start Menu shortcut..."
$shortcutDirs = @(
    (Join-Path $env:ProgramData "Microsoft\Windows\Start Menu\Programs\Brake"),
    (Join-Path $env:AppData "Microsoft\Windows\Start Menu\Programs\Brake")
)
foreach ($shortcutDir in $shortcutDirs) {
    if (Test-Path $shortcutDir) {
        Remove-Item -LiteralPath $shortcutDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Write-Host "Removing Brake local data..."
$uninstallComplete = $true
if (-not (Remove-SensitiveDataFiles)) {
    Write-Warning "Could not remove Brake security files from $dataDir."
    Write-Warning "Restart Windows, run uninstall again, and do not reinstall until this succeeds."
    $uninstallComplete = $false
} elseif (-not (Remove-DataDir)) {
    Write-Warning "Could not fully remove $dataDir because a file is still in use."
    Write-Warning "Brake security files were removed, but logs or folders may remain."
    Write-Warning "Restart Windows, then delete $dataDir manually or run uninstall again."
    $uninstallComplete = $false
}

$machinePythonPath = [Environment]::GetEnvironmentVariable("PYTHONPATH", "Machine")
if ($machinePythonPath -and (Same-Path $machinePythonPath $repoRoot)) {
    [Environment]::SetEnvironmentVariable("PYTHONPATH", $null, "Machine")
    Write-Host "Cleared machine PYTHONPATH for Brake."
} else {
    Write-Host "Machine PYTHONPATH did not point only at this Brake install; leaving it unchanged."
}

if (-not $uninstallComplete) {
    Write-Host ""
    Write-Warning "Uninstall incomplete. Brake local data was not fully removed."
    Write-Warning "Do not reinstall yet if you want a fresh recovery code. Restart Windows and run uninstall again."
    exit 1
}

Write-Host "Services and shortcut removed."
Write-Host "Local data removed, including recovery code and state files."

if (Same-Path $repoRoot $installRoot) {
    Write-Host "Scheduling installed app folder removal: $repoRoot"
    $cleanup = "Start-Sleep -Seconds 2; Remove-Item -LiteralPath '$repoRoot' -Recurse -Force -ErrorAction SilentlyContinue"
    Start-Process powershell.exe -WindowStyle Hidden -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $cleanup
} else {
    Write-Host "You can now delete the Brake source/app folder if you want a full removal."
}
