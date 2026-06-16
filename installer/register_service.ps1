param(
    [switch]$SkipCopy,
    [switch]$NoPrompt
)

# Register the Brake Windows services. Must be elevated.
# Usage:
#   installer\install.bat

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$installRoot = Join-Path $env:ProgramFiles "Brake"
$serviceExe = Join-Path $repoRoot "BrakeService.exe"
$watchdogExe = Join-Path $repoRoot "BrakeWatchdog.exe"
$frozenInstall = (Test-Path $serviceExe) -and (Test-Path $watchdogExe)

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

function Stop-IfRunning($svcName) {
    & sc.exe query $svcName *> $null
    if ($LASTEXITCODE -ne 0) { return }

    Write-Host "Stopping $svcName if it is running..."
    & sc.exe stop $svcName *> $null
}

function Stop-BrakeUserProcesses {
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
        Write-Warning "Could not enumerate user processes: $_"
        return
    }

    foreach ($proc in $processes) {
        if ($proc.ProcessId -eq $PID) { continue }
        $cmd = [string]$proc.CommandLine
        $exe = [string]$proc.ExecutablePath
        $isBrake =
            ($cmd.IndexOf("brake.", [StringComparison]::OrdinalIgnoreCase) -ge 0) -or
            ($cmd.IndexOf($installRoot, [StringComparison]::OrdinalIgnoreCase) -ge 0) -or
            ($exe.IndexOf($installRoot, [StringComparison]::OrdinalIgnoreCase) -ge 0)

        if ($isBrake) {
            Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
        }
    }
}

function Ensure-ElectronRuntime {
    param([string]$DesktopRoot)

    $electronExe = Join-Path $DesktopRoot "node_modules\electron\dist\electron.exe"
    if (Test-Path $electronExe) {
        return
    }

    Write-Host "Preparing Electron runtime..."
    $electronInstall = Join-Path $DesktopRoot "node_modules\electron\install.js"
    if (-not (Test-Path $electronInstall)) {
        throw "Electron install script was not found. Run npm install again."
    }

    Push-Location $DesktopRoot
    try {
        & node.exe $electronInstall
        if ($LASTEXITCODE -ne 0) { throw "Electron runtime install returned $LASTEXITCODE" }
    } finally {
        Pop-Location
    }

    if (-not (Test-Path $electronExe)) {
        throw "Electron runtime is still missing after install: $electronExe"
    }
}

function Copy-SourceInstall {
    if (-not (Test-Path (Join-Path $repoRoot "desktop\package.json"))) {
        throw "desktop\package.json was not found. Run installer\install.bat from the extracted Brake source folder."
    }

    Write-Host "Installing Brake source beta to: $installRoot"
    Write-Host "After install, you can delete the downloaded ZIP/extracted source folder."

    Stop-IfRunning "BrakeWatchdog"
    Stop-IfRunning "BrakeService"
    Stop-BrakeUserProcesses
    Start-Sleep -Seconds 1

    New-Item -ItemType Directory -Force -Path $installRoot | Out-Null

    $excludeDirs = @(
        ".git",
        ".brake-electron-dev-data",
        ".brake-dev-data",
        ".brake-recovery-test-data",
        ".claude",
        "__pycache__",
        "BrakeFromGithub",
        "Design Elements",
        "desktop\node_modules",
        "desktop\dist"
    )
    $excludeFiles = @("*.pyc", "*.pyo")

    & robocopy.exe $repoRoot $installRoot /MIR /XD $excludeDirs /XF $excludeFiles /R:2 /W:1 /NFL /NDL /NP
    $copyCode = $LASTEXITCODE
    if ($copyCode -gt 7) {
        throw "robocopy failed with exit code $copyCode"
    }

    New-Item -ItemType File -Force -Path (Join-Path $installRoot ".brake-source-install") | Out-Null
    $installedRegister = Join-Path $installRoot "installer\register_service.ps1"
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $installedRegister -SkipCopy
    exit $LASTEXITCODE
}

if (-not $frozenInstall -and -not $SkipCopy -and -not (Same-Path $repoRoot $installRoot)) {
    Copy-SourceInstall
}

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
    Write-Host "Mode: source beta installed app"
    Write-Host "Python: $python"
}

Stop-IfRunning "BrakeWatchdog"
Stop-IfRunning "BrakeService"
Start-Sleep -Seconds 2

if (-not $frozenInstall) {
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

    Write-Host ""
    Write-Host "Installing and building the Brake desktop app..."
    Push-Location (Join-Path $repoRoot "desktop")
    try {
        & npm.cmd install
        if ($LASTEXITCODE -ne 0) { throw "npm install returned $LASTEXITCODE" }
        Ensure-ElectronRuntime -DesktopRoot (Get-Location).Path
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw "npm run build returned $LASTEXITCODE" }
    } finally {
        Pop-Location
    }

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
Write-Host "Applying installed-file permissions..."
try {
    & (Join-Path $PSScriptRoot "set_acls.ps1") -InstallRoot $repoRoot
} catch {
    Write-Warning "Could not harden installed app files: $_"
}

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
    $guiExe = Join-Path $repoRoot "Brake.exe"
    if (-not (Test-Path $guiExe)) { $guiExe = "" }
    & (Join-Path $PSScriptRoot "create_shortcuts.ps1") -RepoRoot $repoRoot -PythonPath $python -GuiExe $guiExe
} catch {
    Write-Warning "Could not create the Brake Start Menu shortcut: $_"
}

Write-Host ""
Write-Host "Done. Open Brake from the Windows Start Menu by searching for 'Brake'."
Write-Host "Installed app folder: $repoRoot"
Write-Host "If Windows search does not show it immediately, open:"
Write-Host "  $env:ProgramData\Microsoft\Windows\Start Menu\Programs\Brake.lnk"
Write-Host "  $repoRoot\start-brake.vbs"
Write-Host "Logs: $env:ProgramData\Brake\logs\"

if ($NoPrompt) {
    exit 0
}

$openNow = Read-Host "Open Brake now? [Y/n]"
if ($openNow -notmatch "^(n|no)$") {
    $vbsLauncher = Join-Path $repoRoot "start-brake.vbs"
    $batLauncher = Join-Path $repoRoot "start-brake-dev.bat"
    try {
        if (Test-Path $vbsLauncher) {
            Start-Process -FilePath (Join-Path $env:SystemRoot "System32\wscript.exe") -ArgumentList "`"$vbsLauncher`"" -WorkingDirectory $repoRoot
        } elseif (Test-Path $batLauncher) {
            Start-Process -FilePath $batLauncher -WorkingDirectory $repoRoot
        } else {
            Write-Warning "Could not find a Brake launcher in $repoRoot."
        }
    } catch {
        Write-Warning "Could not open Brake automatically: $_"
    }
}
