# Fully remove Brake services, user-session processes, shortcuts, and local
# security state. Must be elevated.
#
# Important: Windows uninstall is authoritative. It must work even when
# protection or Commitment Mode is active, otherwise an uninstall can half-run
# and leave services/watchdogs alive without a complete app folder.
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

function Disable-ServiceRestart($svcName) {
    Invoke-Sc @("failure", $svcName, "reset=", "0", "actions=", '""') | Out-Null
    Invoke-Sc @("config", $svcName, "start=", "disabled") | Out-Null
}

function Stop-ServiceIfPresent($svcName) {
    Invoke-Sc @("query", $svcName) | Out-Null
    if ($LASTEXITCODE -ne 0) { return }

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
        $pid = Get-ServicePid $svcName
        if (-not $pid) { return $true }
        Start-Sleep -Milliseconds 250
    }
    return $false
}

function Kill-ServiceProcess($svcName) {
    $pid = Get-ServicePid $svcName
    if (-not $pid) { return }

    Write-Host "Force-stopping $svcName pid=$pid..."
    Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
}

function Delete-ServiceIfPresent($svcName) {
    Invoke-Sc @("query", $svcName) | Out-Null
    if ($LASTEXITCODE -ne 0) { return }

    Write-Host "Deleting $svcName..."
    Invoke-Sc @("delete", $svcName) | Out-Null
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
    Write-Host "Closing remaining Brake processes..."
    Stop-AgentFromPidFile

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
            Write-Host "Stopping $($proc.Name) pid=$($proc.ProcessId)"
            Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
        }
    }
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
    Delete-ServiceIfPresent $svc
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
$uninstallComplete = $true
if (-not (Remove-LocalData)) {
    Write-Warning "Could not fully remove $dataDir because a file is still in use."
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

if (Same-Path $repoRoot $installRoot) {
    Write-Host "Scheduling installed app folder removal: $repoRoot"
    $cleanup = @"
Start-Sleep -Seconds 3
Remove-Item -LiteralPath '$repoRoot' -Recurse -Force -ErrorAction SilentlyContinue
"@
    Start-Process powershell.exe -WindowStyle Hidden -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $cleanup
} else {
    Write-Host "You can now delete the Brake source/app folder if you want a full removal."
}
