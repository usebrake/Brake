# Brake source install sanity check. Read-only.
# Run from the Brake repo root: .\scripts\check_source_install.ps1

$ErrorActionPreference = "Continue"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Problems = 0

function Result($Name, $Ok, $Detail = "") {
    if ($Ok) {
        Write-Host "[OK]   $Name $Detail" -ForegroundColor Green
    } else {
        Write-Host "[WARN] $Name $Detail" -ForegroundColor Yellow
        $script:Problems += 1
    }
}

Write-Host "Brake source install check"
Write-Host "Repo: $RepoRoot"
Write-Host ""

Result "Not running from downloaded nested GitHub copy" ($RepoRoot -notmatch "BrakeFromGithub") ""
Result "Source package present" (Test-Path (Join-Path $RepoRoot "brake\__init__.py"))
Result "Electron package present" (Test-Path (Join-Path $RepoRoot "desktop\package.json"))
Result "Launcher present" (Test-Path (Join-Path $RepoRoot "start-brake-dev.bat"))
Result "Installer present" (Test-Path (Join-Path $RepoRoot "installer\install.bat"))
Result "Uninstaller present" (Test-Path (Join-Path $RepoRoot "installer\uninstall.bat"))

$nodeModules = Join-Path $RepoRoot "desktop\node_modules"
if (Test-Path $nodeModules) {
    Result "Desktop dependencies installed" $true
} else {
    Write-Host "[INFO] Desktop dependencies are not installed yet. start-brake-dev.bat will install them on first run."
}

try {
    $status = & python -m brake.desktop_bridge status 2>$null
    Result "Backend status command" ($LASTEXITCODE -eq 0) ""
} catch {
    Result "Backend status command" $false $_.Exception.Message
}

$shortcut = Join-Path $env:ProgramData "Microsoft\Windows\Start Menu\Programs\Brake\Brake.lnk"
if (Test-Path $shortcut) {
    try {
        $shell = New-Object -ComObject WScript.Shell
        $lnk = $shell.CreateShortcut($shortcut)
        Result "Start Menu shortcut target exists" (Test-Path $lnk.TargetPath) $lnk.TargetPath
        Result "Start Menu shortcut points at this folder" ($lnk.WorkingDirectory -eq $RepoRoot) $lnk.WorkingDirectory
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
