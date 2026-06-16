param(
    [string]$Version = "0.1.3-beta",
    [string]$InnoCompiler = "",
    [switch]$SkipPyInstaller,
    [switch]$SkipNpmInstall,
    [switch]$SkipInno
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$desktopRoot = Join-Path $repoRoot "desktop"

Write-Host "Building Brake Windows installer artifacts..."
Write-Host "Repo: $repoRoot"
Write-Host "Version: $Version"

if (-not $SkipNpmInstall) {
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
    Write-Host "Building Electron renderer..."
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw "npm run build returned $LASTEXITCODE" }
} finally {
    Pop-Location
}

if (-not $SkipPyInstaller) {
    Write-Host ""
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $repoRoot "packaging\build_pyinstaller.ps1") -SkipInstallPyInstaller -Version $Version
    if ($LASTEXITCODE -ne 0) { throw "build_pyinstaller.ps1 returned $LASTEXITCODE" }
}

Write-Host ""
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $repoRoot "packaging\build_electron_package.ps1") -Version $Version
if ($LASTEXITCODE -ne 0) { throw "build_electron_package.ps1 returned $LASTEXITCODE" }

if (-not $SkipInno) {
    Write-Host ""
    $args = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $repoRoot "packaging\build_inno.ps1"), "-Version", $Version)
    if ($InnoCompiler) {
        $args += @("-InnoCompiler", $InnoCompiler)
    }
    & powershell.exe @args
    if ($LASTEXITCODE -ne 0) { throw "build_inno.ps1 returned $LASTEXITCODE" }
}

Write-Host ""
Write-Host "Windows installer build complete."
