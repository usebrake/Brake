param(
    [string]$Version = "0.1.4-beta",
    [string]$InnoCompiler = "",
    [switch]$Incremental,
    [string[]]$PythonComponents = @(),
    [switch]$DesktopChanged,
    [switch]$SkipPyInstaller,
    [switch]$SkipNpmInstall,
    [switch]$SkipInno
)

# Official release, clean rebuild of every component:
#   .\packaging\build_windows_installer.ps1 -Version 0.1.4-beta
# Incremental Python-only rebuild, preserving the existing bundle:
#   .\packaging\build_windows_installer.ps1 -Incremental -PythonComponents BrakeLockout,BrakeUninstallGuard
# Add -DesktopChanged when desktop Electron or React sources changed.

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$desktopRoot = Join-Path $repoRoot "desktop"
$buildTimer = [System.Diagnostics.Stopwatch]::StartNew()
$PythonComponents = @(
    $PythonComponents |
        ForEach-Object { $_ -split "," } |
        ForEach-Object { $_.Trim() } |
        Where-Object { $_ }
)

Write-Host "Building Brake Windows installer artifacts..."
Write-Host "Repo: $repoRoot"
Write-Host "Version: $Version"

if (-not $SkipNpmInstall -and (-not $Incremental -or $DesktopChanged)) {
    Push-Location $desktopRoot
    try {
        Write-Host ""
        Write-Host "Installing desktop dependencies..."
        & npm.cmd install
        if ($LASTEXITCODE -ne 0) { throw "npm install returned $LASTEXITCODE" }
    } finally {
        Pop-Location
    }
}

Push-Location $desktopRoot
try {
    Write-Host ""
    Write-Host "Auditing production desktop dependencies..."
    & npm.cmd audit --omit=dev
    if ($LASTEXITCODE -ne 0) { throw "npm audit --omit=dev returned $LASTEXITCODE" }

    if (-not $Incremental -or $DesktopChanged) {
        Write-Host ""
        Write-Host "Building Electron renderer..."
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw "npm run build returned $LASTEXITCODE" }
    } else {
        Write-Host "Skipping Electron renderer; no desktop change was selected."
    }
} finally {
    Pop-Location
}

if (-not $SkipPyInstaller) {
    if ($Incremental -and $PythonComponents.Count -eq 0) {
        Write-Host "Skipping PyInstaller; no Python components were selected."
    } else {
        Write-Host ""
        $pyInstallerScript = Join-Path $repoRoot "packaging\build_pyinstaller.ps1"
        if ($Incremental) {
            & $pyInstallerScript -SkipInstallPyInstaller -Version $Version -Incremental -Components $PythonComponents
        } else {
            & $pyInstallerScript -SkipInstallPyInstaller -Version $Version
        }
        if ($LASTEXITCODE -ne 0) { throw "build_pyinstaller.ps1 returned $LASTEXITCODE" }
    }
}

if (-not $Incremental -or $DesktopChanged) {
    Write-Host ""
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $repoRoot "packaging\build_electron_package.ps1") -Version $Version
    if ($LASTEXITCODE -ne 0) { throw "build_electron_package.ps1 returned $LASTEXITCODE" }
} else {
    Write-Host "Skipping Electron packaging; no desktop change was selected."
}

if (-not $SkipInno) {
    Write-Host ""
    $args = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $repoRoot "packaging\build_inno.ps1"), "-Version", $Version)
    if ($InnoCompiler) {
        $args += @("-InnoCompiler", $InnoCompiler)
    }
    & powershell.exe @args
    if ($LASTEXITCODE -ne 0) { throw "build_inno.ps1 returned $LASTEXITCODE" }
}

$buildTimer.Stop()
$bundlePath = Join-Path $repoRoot "dist\brake"
$bundleFiles = @(Get-ChildItem -LiteralPath $bundlePath -Recurse -File -ErrorAction SilentlyContinue)
$bundleSize = ($bundleFiles | Measure-Object -Property Length -Sum).Sum
$installerPath = Join-Path $repoRoot "dist\BrakeSetup-$Version.exe"
$installerSize = if (Test-Path $installerPath) { (Get-Item -LiteralPath $installerPath).Length } else { 0 }

Write-Host ""
Write-Host "Windows installer build complete."
Write-Host "Duration: $([math]::Round($buildTimer.Elapsed.TotalSeconds, 1)) seconds"
Write-Host "Bundle files: $($bundleFiles.Count)"
Write-Host "Bundle size: $bundleSize bytes"
if ($installerSize -gt 0) {
    Write-Host "Installer size: $installerSize bytes"
}
