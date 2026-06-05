param(
    [string]$InstallRoot = (Join-Path $env:ProgramFiles "Brake")
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $InstallRoot)) {
    throw "Install root does not exist: $InstallRoot"
}

$resolved = (Resolve-Path $InstallRoot).Path
$programFiles = (Resolve-Path $env:ProgramFiles).Path
if (-not $resolved.StartsWith($programFiles, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to harden a folder outside Program Files: $resolved"
}

Write-Host "Hardening installed app files..."
Write-Host "Install root: $resolved"

& icacls.exe $resolved /inheritance:r | Out-Null
if ($LASTEXITCODE -ne 0) { throw "icacls inheritance update failed with $LASTEXITCODE" }

& icacls.exe $resolved `
    /grant:r "SYSTEM:(OI)(CI)F" `
    /grant:r "Administrators:(OI)(CI)F" `
    /grant:r "Users:(OI)(CI)RX" `
    /grant:r "Authenticated Users:(OI)(CI)RX" | Out-Null
if ($LASTEXITCODE -ne 0) { throw "icacls grant update failed with $LASTEXITCODE" }

Write-Host "Installed app files are read-only for standard users."