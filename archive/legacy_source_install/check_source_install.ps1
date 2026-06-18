# Brake source install sanity check. Read-only.
# Run from the Brake repo root: .\scripts\check_source_install.ps1

$ErrorActionPreference = "Continue"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$InstallRoot = Join-Path $env:ProgramFiles "Brake"
$Problems = 0

function Result($Name, $Ok, $Detail = "") {
    if ($Ok) {
        Write-Host "[OK]   $Name $Detail" -ForegroundColor Green
    } else {
        Write-Host "[WARN] $Name $Detail" -ForegroundColor Yellow
        $script:Problems += 1
    }
}

function Info($Message) {
    Write-Host "[INFO] $Message"
}

Write-Host "Brake source install check"
Write-Host "Current folder: $RepoRoot"
Write-Host "Expected install folder: $InstallRoot"
Write-Host ""

Result "Source package present" (Test-Path (Join-Path $RepoRoot "brake\__init__.py"))
Result "Electron package present" (Test-Path (Join-Path $RepoRoot "desktop\package.json"))
Result "Launcher present" (Test-Path (Join-Path $RepoRoot "start-brake-dev.bat"))
Result "Installer present" (Test-Path (Join-Path $RepoRoot "installer\install.bat"))
Result "Uninstaller present" (Test-Path (Join-Path $RepoRoot "installer\uninstall.bat"))

if (Test-Path $InstallRoot) {
    Result "Installed app folder exists" $true $InstallRoot
    Result "Installed app marker" (Test-Path (Join-Path $InstallRoot ".brake-source-install"))
    Result "Installed desktop build" (Test-Path (Join-Path $InstallRoot "desktop\dist\index.html"))
    Result "Installed desktop dependencies" (Test-Path (Join-Path $InstallRoot "desktop\node_modules"))
} else {
    Info "Brake is not installed into Program Files yet. Run installer\install.bat."
}

try {
    $status = & python -m brake.desktop_bridge status 2>$null
    Result "Backend status command from current folder" ($LASTEXITCODE -eq 0) ""
} catch {
    Result "Backend status command from current folder" $false $_.Exception.Message
}

$shortcut = Join-Path $env:ProgramData "Microsoft\Windows\Start Menu\Programs\Brake\Brake.lnk"
if (Test-Path $shortcut) {
    try {
        $shell = New-Object -ComObject WScript.Shell
        $lnk = $shell.CreateShortcut($shortcut)
        Result "Start Menu shortcut target exists" (Test-Path $lnk.TargetPath) $lnk.TargetPath
        Result "Start Menu shortcut points to installed app" ($lnk.WorkingDirectory -eq $InstallRoot) $lnk.WorkingDirectory
    } catch {
        Result "Read Start Menu shortcut" $false $_.Exception.Message
    }
} else {
    Result "Start Menu shortcut exists" $false $shortcut
}

Write-Host ""
if ($Problems -gt 0) {
    Write-Host "$Problems warning(s) found." -ForegroundColor Yellow
    exit 1
}

Write-Host "Source install looks consistent." -ForegroundColor Green
exit 0