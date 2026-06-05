# Register the Brake Windows services. Must be elevated.
# Usage (from elevated PowerShell):
#   powershell -ExecutionPolicy Bypass -File register_service.ps1

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$serviceExe = Join-Path $repoRoot "BrakeService.exe"
$watchdogExe = Join-Path $repoRoot "BrakeWatchdog.exe"
$frozenInstall = (Test-Path $serviceExe) -and (Test-Path $watchdogExe)

if (-not $frozenInstall) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCommand) {
        throw "Python was not found in PATH. Install Python 3.11+ x64 and check 'Add python.exe to PATH', then run installer\install.bat again."
    }
    $python = $pythonCommand.Path

    $nodeCommand = Get-Command node -ErrorAction SilentlyContinue
    if (-not $nodeCommand) {
        throw "Node.js was not found in PATH. Install Node.js LTS from nodejs.org, close this terminal, then run installer\install.bat again."
    }

    $npmCommand = Get-Command npm -ErrorAction SilentlyContinue
    if (-not $npmCommand) {
        throw "npm was not found in PATH. Install Node.js LTS from nodejs.org, close this terminal, then run installer\install.bat again."
    }

    if (-not (Test-Path (Join-Path $repoRoot "desktop\package.json"))) {
        throw "desktop\package.json was not found. Make sure you are running installer\install.bat from the extracted Brake source folder."
    }
} else {
    $python = $null
}

Write-Host "Repo: $repoRoot"
if ($frozenInstall) {
    Write-Host "Mode: bundled executable install"
} else {
    Write-Host "Python: $python"
}

function Stop-IfRunning($svcName) {
    & sc.exe query $svcName *> $null
    if ($LASTEXITCODE -ne 0) { return }

    Write-Host "Stopping $svcName if it is running..."
    & sc.exe stop $svcName *> $null
}

Stop-IfRunning "BrakeWatchdog"
Stop-IfRunning "BrakeService"
Start-Sleep -Seconds 2

if (-not $frozenInstall) {
    # Services run as LocalSystem, so they cannot import packages installed in the
    # current user's AppData\Roaming site-packages. Install dependencies into the
    # machine Python while this script is elevated.
    Write-Host ""
    Write-Host "Installing Python dependencies into the system interpreter..."
    & $python -s -m pip install --upgrade --no-user -r (Join-Path $repoRoot "requirements.txt")
    if ($LASTEXITCODE -ne 0) { throw "pip install returned $LASTEXITCODE" }

    $pywin32PostInstall = Join-Path (Split-Path -Parent $python) "Scripts\pywin32_postinstall.py"
    if (Test-Path $pywin32PostInstall) {
        Write-Host "Running pywin32 post-install hook..."
        & $python -s $pywin32PostInstall -install
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "pywin32_postinstall returned $LASTEXITCODE. Continuing; this can happen when an old pywin32 DLL is locked."
        }
    }

    # Make `import brake` discoverable for the SCM-launched service process.
    # Machine env is read by services on each start, so setting it here is enough.
    [Environment]::SetEnvironmentVariable("PYTHONPATH", $repoRoot, "Machine")
    $env:PYTHONPATH = $repoRoot
    Write-Host "Set machine PYTHONPATH = $repoRoot"
}

function Install-Svc($module, $svcName) {
    & sc.exe query $svcName *> $null
    if ($LASTEXITCODE -eq 0) {
        $action = "update"
    } else {
        $action = "install"
    }
    Write-Host ""
    if ($frozenInstall) {
        if ($svcName -eq "BrakeService") {
            $exe = $serviceExe
        } else {
            $exe = $watchdogExe
        }
        Write-Host "Registering service via $exe $action ..."
        & $exe $action
    } else {
        Write-Host "Registering service via $python -m $module $action ..."
        & $python -m $module $action
    }
    if ($LASTEXITCODE -ne 0) { throw "$module $action returned $LASTEXITCODE" }
}

function Configure-Failure($svcName) {
    Write-Host "Configuring failure auto-restart for $svcName ..."
    & sc.exe failure $svcName reset= 0 actions= restart/5000/restart/5000/restart/5000
    & sc.exe config $svcName start= auto | Out-Null
}

Install-Svc "brake.service" "BrakeService"
Install-Svc "brake.watchdog" "BrakeWatchdog"

Configure-Failure "BrakeService"
Configure-Failure "BrakeWatchdog"

Write-Host ""
Write-Host "Starting services..."
& sc.exe start BrakeService    | Out-Null
& sc.exe start BrakeWatchdog   | Out-Null

Start-Sleep -Seconds 1
& sc.exe query BrakeService
& sc.exe query BrakeWatchdog

Write-Host ""
Write-Host "Creating Start Menu shortcut..."
try {
    $guiExe = Join-Path $repoRoot "brake.exe"
    if (-not (Test-Path $guiExe)) { $guiExe = "" }
    & (Join-Path $PSScriptRoot "create_shortcuts.ps1") -RepoRoot $repoRoot -PythonPath $python -GuiExe $guiExe
} catch {
    Write-Warning "Could not create the Brake Start Menu shortcut: $_"
}

Write-Host ""
Write-Host "Done. Open Brake from the Windows Start Menu."
Write-Host "Verify services with: sc query BrakeService"
Write-Host "Logs: $env:ProgramData\\brake\\logs\"
