# Stop Brake services and user-session processes before installer file copy.
# This is for updates only: it does not remove services, data, recovery state,
# models, or commitments.
$ErrorActionPreference = "Continue"
$installRoot = Join-Path $env:ProgramFiles "Brake"
$dataDir = Join-Path $env:ProgramData "Brake"

function Stop-IfRunning($svcName) {
    & sc.exe query $svcName *> $null
    if ($LASTEXITCODE -ne 0) { return }
    Write-Host "Stopping $svcName..."
    & sc.exe stop $svcName *> $null
}

function Stop-BrakeUserProcesses {
    param([int]$Passes = 5)

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
                        "BrakeUninstallGuard.exe"
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
                ($cmd.IndexOf($installRoot, [StringComparison]::OrdinalIgnoreCase) -ge 0) -or
                ($cmd.IndexOf($dataDir, [StringComparison]::OrdinalIgnoreCase) -ge 0) -or
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

Stop-IfRunning "BrakeWatchdog"
Stop-IfRunning "BrakeService"
Stop-BrakeUserProcesses -Passes 8 | Out-Null
Start-Sleep -Seconds 2
exit 0
