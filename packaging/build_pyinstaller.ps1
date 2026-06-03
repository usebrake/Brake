param(
    [string]$Version = "0.1.0-beta",
    [switch]$SkipInstallPyInstaller,
    [switch]$Resume
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$distRoot = Join-Path $repoRoot "dist"
$workRoot = Join-Path $repoRoot "build\pyinstaller"
$specRoot = Join-Path $repoRoot "build\spec"
$bundle = Join-Path $distRoot "LockItUp"

Write-Host "Repo: $repoRoot"
Write-Host "Bundle: $bundle"

if (-not $SkipInstallPyInstaller) {
    Write-Host "Ensuring PyInstaller is installed for this Python..."
    python -m pip install --upgrade pyinstaller
}

if ((Test-Path $bundle) -and -not $Resume) {
    Remove-Item -LiteralPath $bundle -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $bundle, $workRoot, $specRoot | Out-Null

function Build-App($name, $entry, $windowed) {
    $outDir = Join-Path $distRoot $name
    $outExe = Join-Path $outDir "$name.exe"
    if ($Resume -and (Test-Path $outExe)) {
        Write-Host "Skipping $name; existing output found."
        return
    }
    $configSrc = Join-Path $repoRoot "config"
    $assetsSrc = Join-Path $repoRoot "lockitup\gui\assets"
    $iconSrc = Join-Path $repoRoot "lockitup\gui\assets\brake.ico"
    $stylesSrc = Join-Path $repoRoot "lockitup\gui\styles.qss"
    $entrySrc = Join-Path $repoRoot $entry
    $args = @(
        "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--name", $name,
        "--distpath", $distRoot,
        "--workpath", $workRoot,
        "--specpath", $specRoot,
        "--icon", $iconSrc,
        "--collect-all", "nudenet",
        "--collect-all", "PyQt6",
        "--collect-submodules", "win32com",
        "--hidden-import", "servicemanager",
        "--hidden-import", "win32timezone",
        "--add-data", "$configSrc;config",
        "--add-data", "$assetsSrc;lockitup\gui\assets",
        "--add-data", "$stylesSrc;lockitup\gui",
        $entrySrc
    )
    if ($windowed) {
        $args = @("-m", "PyInstaller", "--windowed") + $args[2..($args.Length - 1)]
    }
    Write-Host ""
    Write-Host "Building $name..."
    python @args
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed for $name with exit code $LASTEXITCODE" }
}

Build-App "LockItUp" "packaging\entry_gui.py" $true
Build-App "LockItUpAgent" "packaging\entry_agent.py" $true
Build-App "LockItUpLockout" "packaging\entry_lockout.py" $true
Build-App "LockItUpUninstallGuard" "packaging\entry_uninstall_guard.py" $true
Build-App "LockItUpService" "packaging\entry_service.py" $false
Build-App "LockItUpWatchdog" "packaging\entry_watchdog.py" $false

Write-Host ""
Write-Host "Flattening executable folders into $bundle..."
foreach ($name in @("LockItUpAgent", "LockItUpLockout", "LockItUpUninstallGuard", "LockItUpService", "LockItUpWatchdog")) {
    $src = Join-Path $distRoot $name
    if (-not (Test-Path $src)) { throw "Missing build output: $src" }
    Copy-Item -Path (Join-Path $src "*") -Destination $bundle -Recurse -Force
    Remove-Item -LiteralPath $src -Recurse -Force
}

Copy-Item -Path (Join-Path $repoRoot "installer") -Destination (Join-Path $bundle "installer") -Recurse -Force
Copy-Item -Path (Join-Path $repoRoot "README.md") -Destination $bundle -Force
Copy-Item -Path (Join-Path $repoRoot "LICENSE") -Destination $bundle -Force
Copy-Item -Path (Join-Path $repoRoot "PRIVACY.md") -Destination $bundle -Force
Copy-Item -Path (Join-Path $repoRoot "SECURITY.md") -Destination $bundle -Force

$zip = Join-Path $distRoot "LockItUp-$Version-portable-dev.zip"
if (Test-Path $zip) { Remove-Item -LiteralPath $zip -Force }
Compress-Archive -Path (Join-Path $bundle "*") -DestinationPath $zip

$shaFile = Join-Path $distRoot "SHA256SUMS.txt"
$releaseFiles = @($zip) + (Get-ChildItem -Path $bundle -Filter "*.exe" -File | Sort-Object Name | ForEach-Object { $_.FullName })
$releaseFiles |
    ForEach-Object {
        $rel = $_.Substring($distRoot.Length + 1).Replace("\", "/")
        $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $_).Hash.ToLowerInvariant()
        "$hash  $rel"
    } | Set-Content -Encoding ASCII $shaFile

Write-Host ""
Write-Host "PyInstaller bundle complete:"
Write-Host "  $bundle"
Write-Host "  $zip"
Write-Host "  $shaFile"
Write-Host ""
Write-Host "Next: install Inno Setup and run packaging\build_inno.ps1 to create LockItUpSetup-$Version.exe"
