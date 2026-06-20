param(
    [switch]$NoAppFolderCleanup
)

# Fully remove Brake services, user-session processes, shortcuts, and local
# security state. Must be elevated. Protection/commitment policy is enforced
# by BrakeUninstallGuard before this cleanup runs from the Windows uninstaller.
$ErrorActionPreference = "Continue"

$repoRoot = Split-Path -Parent $PSScriptRoot
$installRoot = Join-Path $env:ProgramFiles "Brake"
$dataDir = Join-Path $env:ProgramData "Brake"
$agentPidFile = Join-Path $dataDir "agent.pid"
$serviceNames = @("BrakeWatchdog", "BrakeService")

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

function Test-IsAdmin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

$installedUnregister = Join-Path $installRoot "installer\unregister_service.ps1"
if (-not (Same-Path $repoRoot $installRoot) -and (Test-Path $installedUnregister)) {
    Write-Host "Forwarding uninstall to installed Brake app: $installRoot"
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $installedUnregister
    exit $LASTEXITCODE
}

if (-not (Test-IsAdmin)) {
    Write-Warning "Brake uninstall must run as administrator."
    exit 5
}

function Invoke-Sc {
    param([string[]]$ScArgs)
    & sc.exe @ScArgs 2>&1 | ForEach-Object { Write-Host $_ }
    return $LASTEXITCODE
}

function Test-ServicePresent($svcName) {
    & sc.exe query $svcName *> $null
    return $LASTEXITCODE -eq 0
}

function Disable-ServiceRestart($svcName) {
    Invoke-Sc @("failure", $svcName, "reset=", "0", "actions=", '""') | Out-Null
    Invoke-Sc @("config", $svcName, "start=", "disabled") | Out-Null
}

function Stop-ServiceIfPresent($svcName) {
    if (-not (Test-ServicePresent $svcName)) { return }

    Write-Host "Stopping $svcName..."
    Invoke-Sc @("stop", $svcName) | Out-Null
}

function Get-ServicePid($svcName) {
    try {
        $svc = Get-CimInstance Win32_Service -Filter "Name='$svcName'" -ErrorAction Stop
        if ($svc -and $svc.ProcessId -and $svc.ProcessId -ne 0) {
            return [int]$svc.ProcessId
        }
    } catch {
    }
    return $null
}

function Wait-ServiceStopped($svcName, [int]$seconds = 10) {
    for ($i = 0; $i -lt ($seconds * 4); $i++) {
        $servicePid = Get-ServicePid $svcName
        if (-not $servicePid) { return $true }
        Start-Sleep -Milliseconds 250
    }
    return $false
}

function Kill-ServiceProcess($svcName) {
    $servicePid = Get-ServicePid $svcName
    if (-not $servicePid) { return }

    Write-Host "Force-stopping $svcName pid=$servicePid..."
    Stop-Process -Id $servicePid -Force -ErrorAction SilentlyContinue
}

function Delete-ServiceIfPresent($svcName) {
    if (-not (Test-ServicePresent $svcName)) { return $true }

    for ($i = 0; $i -lt 6; $i++) {
        Write-Host "Deleting $svcName..."
        Invoke-Sc @("delete", $svcName) | Out-Null
        Start-Sleep -Milliseconds 500
        if (-not (Test-ServicePresent $svcName)) { return $true }
        Stop-BrakeProcesses | Out-Null
    }

    return -not (Test-ServicePresent $svcName)
}

function Wait-ServiceDeleted($svcName, [int]$seconds = 10) {
    for ($i = 0; $i -lt ($seconds * 4); $i++) {
        Invoke-Sc @("query", $svcName) | Out-Null
        if ($LASTEXITCODE -ne 0) { return $true }
        Start-Sleep -Milliseconds 250
    }
    return $false
}

function Stop-AgentFromPidFile {
    if (-not (Test-Path $agentPidFile)) { return }
    try {
        $agentPid = [int]((Get-Content -Raw -LiteralPath $agentPidFile).Trim())
    } catch {
        return
    }
    if ($agentPid -le 0) { return }

    Stop-Process -Id $agentPid -Force -ErrorAction SilentlyContinue
}

function Stop-BrakeProcesses {
    param([int]$Passes = 5)

    Write-Host "Closing remaining Brake processes..."
    Stop-AgentFromPidFile

    for ($pass = 0; $pass -lt $Passes; $pass++) {
        try {
            $processes = Get-CimInstance Win32_Process |
                Where-Object {
                    $_.Name -in @(
                        "python.exe",
                        "pythonw.exe",
                        "electron.exe",
                        "node.exe",
                        "brake.exe",
                        "Brake.exe",
                        "BrakeAgent.exe",
                        "BrakeBoot.exe",
                        "BrakeBridge.exe",
                        "BrakeLockout.exe",
                        "BrakeUninstallGuard.exe",
                        "wscript.exe"
                    )
                }
        } catch {
            Write-Warning "Could not enumerate Brake processes: $_"
            return $false
        }

        $found = $false
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
                $found = $true
                Write-Host "Stopping $($proc.Name) pid=$($proc.ProcessId)"
                & taskkill.exe /PID $proc.ProcessId /T /F 2>&1 | ForEach-Object { Write-Host $_ }
                Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
            }
        }

        if (-not $found) { return $true }
        Start-Sleep -Milliseconds 600
    }

    return $false
}

function Remove-PathRobust {
    param([string]$Path, [switch]$Recurse)
    if (-not (Test-Path -LiteralPath $Path)) { return $true }

    for ($i = 0; $i -lt 20; $i++) {
        if ($Recurse) {
            Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction SilentlyContinue
        } else {
            Remove-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
        }
        if (-not (Test-Path -LiteralPath $Path)) { return $true }
        Stop-BrakeProcesses
        Start-Sleep -Milliseconds 500
    }
    return $false
}

function Remove-LocalData {
    if (-not (Test-Path $dataDir)) { return $true }

    $sensitivePatterns = @(
        "state.json",
        "state.key",
        "state.initialized",
        "recovery.json",
        "agent.pid",
        "state.json.*.tmp",
        "recovery.json.*.tmp"
    )

    foreach ($pattern in $sensitivePatterns) {
        Get-ChildItem -LiteralPath $dataDir -Filter $pattern -Force -ErrorAction SilentlyContinue |
            ForEach-Object {
                Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue
            }
    }

    return (Remove-PathRobust -Path $dataDir -Recurse)
}

Write-Host "Disabling Brake service restart..."
$uninstallComplete = $true
foreach ($svc in $serviceNames) {
    Disable-ServiceRestart $svc
}

# Stop watchdog first so it cannot restart BrakeService while uninstall runs.
foreach ($svc in $serviceNames) {
    Stop-ServiceIfPresent $svc
}

foreach ($svc in $serviceNames) {
    if (-not (Wait-ServiceStopped $svc 10)) {
        Kill-ServiceProcess $svc
    }
}

Stop-BrakeProcesses
Start-Sleep -Seconds 1

foreach ($svc in $serviceNames) {
    Disable-ServiceRestart $svc
    if (-not (Delete-ServiceIfPresent $svc)) {
        Write-Warning "$svc could not be deleted."
        $uninstallComplete = $false
    }
}

foreach ($svc in $serviceNames) {
    if (-not (Wait-ServiceDeleted $svc 15)) {
        Write-Warning "$svc is still registered after delete."
        $uninstallComplete = $false
    }
}

Write-Host "Removing login recovery autostart..."
Remove-ItemProperty `
    -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" `
    -Name "Brake" `
    -ErrorAction SilentlyContinue

Write-Host "Removing Brake shortcuts..."
$shortcutPaths = @(
    (Join-Path $env:ProgramData "Microsoft\Windows\Start Menu\Programs\Brake"),
    (Join-Path $env:AppData "Microsoft\Windows\Start Menu\Programs\Brake"),
    (Join-Path $env:PUBLIC "Desktop\Brake.lnk"),
    (Join-Path ([Environment]::GetFolderPath("Desktop")) "Brake.lnk")
)
foreach ($shortcut in $shortcutPaths) {
    Remove-PathRobust -Path $shortcut -Recurse | Out-Null
}

Write-Host "Removing Brake local data..."
if (-not (Remove-LocalData)) {
    Write-Warning "Could not fully remove $dataDir because a file is still in use."
    $uninstallComplete = $false
}

if (-not (Stop-BrakeProcesses -Passes 8)) {
    Write-Warning "Brake processes are still running after repeated stop attempts."
    $uninstallComplete = $false
}

$machinePythonPath = [Environment]::GetEnvironmentVariable("PYTHONPATH", "Machine")
if ($machinePythonPath -and (Same-Path $machinePythonPath $repoRoot)) {
    [Environment]::SetEnvironmentVariable("PYTHONPATH", $null, "Machine")
    Write-Host "Cleared machine PYTHONPATH for Brake."
}

$remainingServices = @(
    Get-CimInstance Win32_Service -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like "Brake*" -or $_.DisplayName -like "Brake*" }
)
$remainingProcesses = @(
    Get-Process -ErrorAction SilentlyContinue |
        Where-Object { $_.ProcessName -like "Brake*" }
)

if ($remainingServices.Count -gt 0) {
    Write-Warning "Brake services are still registered:"
    $remainingServices | ForEach-Object { Write-Warning "  $($_.Name) $($_.State) pid=$($_.ProcessId)" }
    $uninstallComplete = $false
}
if ($remainingProcesses.Count -gt 0) {
    Write-Warning "Brake processes are still running:"
    $remainingProcesses | ForEach-Object { Write-Warning "  $($_.ProcessName) pid=$($_.Id)" }
    $uninstallComplete = $false
}

if (-not $uninstallComplete) {
    Write-Warning "Uninstall incomplete. Restart Windows and run uninstall again."
    exit 1
}

Write-Host "Brake services, processes, shortcuts, and local data removed."

if ($NoAppFolderCleanup) {
    Write-Host "Installed app folder will be removed by the Windows uninstaller."
} elseif (Same-Path $repoRoot $installRoot) {
    Write-Host "Scheduling installed app folder removal: $repoRoot"
    $cleanup = @"
Start-Sleep -Seconds 3
Remove-Item -LiteralPath '$repoRoot' -Recurse -Force -ErrorAction SilentlyContinue
"@
    Start-Process powershell.exe -WindowStyle Hidden -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $cleanup
} else {
    Write-Host "You can now delete the Brake source/app folder if you want a full removal."
}

exit 0
