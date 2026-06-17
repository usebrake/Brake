param(
    [string]$Version = "0.1.3-beta"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$desktopRoot = Join-Path $repoRoot "desktop"
$bundle = Join-Path $repoRoot "dist\brake"
$electronDist = Join-Path $desktopRoot "node_modules\electron\dist"
$electronExe = Join-Path $electronDist "electron.exe"

if (-not (Test-Path $electronExe)) {
    throw "Electron runtime not found at $electronExe. Run npm install in desktop first."
}
if (-not (Test-Path (Join-Path $desktopRoot "dist\index.html"))) {
    throw "desktop\dist is missing. Run npm run build in desktop first."
}

New-Item -ItemType Directory -Force -Path $bundle | Out-Null

Write-Host "Copying Electron runtime into $bundle..."
Copy-Item -Path (Join-Path $electronDist "*") -Destination $bundle -Recurse -Force

$targetElectronExe = Join-Path $bundle "electron.exe"
$targetBrakeExe = Join-Path $bundle "Brake.exe"
$iconPath = Join-Path $desktopRoot "src\assets\brake-ring.ico"
if (Test-Path $targetBrakeExe) {
    Remove-Item -LiteralPath $targetBrakeExe -Force
}
Move-Item -LiteralPath $targetElectronExe -Destination $targetBrakeExe -Force

Write-Host "Stamping Brake icon into Electron shell..."
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $repoRoot "packaging\set_exe_icon.ps1") -ExePath $targetBrakeExe -IconPath $iconPath -Version $Version
if ($LASTEXITCODE -ne 0) { throw "set_exe_icon.ps1 returned $LASTEXITCODE" }

$appRoot = Join-Path $bundle "resources\app"
if (Test-Path $appRoot) {
    Remove-Item -LiteralPath $appRoot -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $appRoot | Out-Null

Copy-Item -Path (Join-Path $desktopRoot "electron") -Destination (Join-Path $appRoot "electron") -Recurse -Force
Copy-Item -Path (Join-Path $desktopRoot "dist") -Destination (Join-Path $appRoot "dist") -Recurse -Force
Copy-Item -Path (Join-Path $desktopRoot "src\assets") -Destination (Join-Path $appRoot "src\assets") -Recurse -Force

@"
{
  "name": "brake",
  "version": "$Version",
  "main": "electron/main.cjs",
  "description": "Brake desktop app",
  "private": true
}
"@ | Set-Content -Encoding UTF8 -Path (Join-Path $appRoot "package.json")

Write-Host "Electron package complete:"
Write-Host "  $targetBrakeExe"
