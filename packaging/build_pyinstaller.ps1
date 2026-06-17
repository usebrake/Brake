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
$bundle = Join-Path $distRoot "brake"

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

function Get-VersionTuple([string]$rawVersion) {
    $numbers = @()
    foreach ($part in ($rawVersion -split "[^0-9]+")) {
        if ($part -ne "") { $numbers += [int]$part }
    }
    while ($numbers.Count -lt 4) { $numbers += 0 }
    return $numbers[0..3]
}

function Escape-VersionString([string]$value) {
    return $value.Replace("\", "\\").Replace("'", "\'")
}

function Write-VersionFile($name, $description) {
    $parts = Get-VersionTuple $Version
    $versionTuple = "($($parts[0]), $($parts[1]), $($parts[2]), $($parts[3]))"
    $safeVersion = Escape-VersionString $Version
    $safeDescription = Escape-VersionString $description
    $path = Join-Path $specRoot "$name.version.txt"
    @"
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=$versionTuple,
    prodvers=$versionTuple,
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [
          StringStruct('CompanyName', 'UseBrake'),
          StringStruct('FileDescription', '$safeDescription'),
          StringStruct('FileVersion', '$safeVersion'),
          StringStruct('InternalName', '$name'),
          StringStruct('OriginalFilename', '$name.exe'),
          StringStruct('ProductName', 'Brake'),
          StringStruct('ProductVersion', '$safeVersion')
        ]
      )
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"@ | Set-Content -Encoding UTF8 -Path $path
    return $path
}

function Build-App(
    $name,
    $entry,
    $windowed,
    $description,
    [switch]$NeedsNudeNet,
    [switch]$NeedsPyQt,
    [switch]$NeedsAnimeExport
) {
    $outDir = Join-Path $distRoot $name
    $outExe = Join-Path $outDir "$name.exe"
    if ($Resume -and (Test-Path $outExe)) {
        Write-Host "Skipping $name; existing output found."
        return
    }
    $configSrc = Join-Path $repoRoot "config"
    $assetsSrc = Join-Path $repoRoot "brake\\gui\assets"
    $iconSrc = Join-Path $repoRoot "brake\\gui\assets\brake.ico"
    $stylesSrc = Join-Path $repoRoot "brake\\gui\styles.qss"
    $entrySrc = Join-Path $repoRoot $entry
    $versionFile = Write-VersionFile $name $description
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
        "--version-file", $versionFile,
        "--hidden-import", "servicemanager",
        "--hidden-import", "win32timezone",
        "--add-data", "$configSrc;config",
        $entrySrc
    )
    if ($NeedsNudeNet) {
        $args = $args[0..($args.Length - 2)] + @("--collect-all", "nudenet") + $args[-1]
    }
    if ($NeedsPyQt) {
        $args = $args[0..($args.Length - 2)] + @(
            "--collect-all", "PyQt6",
            "--add-data", "$assetsSrc;brake\\gui\assets",
            "--add-data", "$stylesSrc;brake\\gui"
        ) + $args[-1]
    }
    if ($NeedsAnimeExport) {
        $args = $args[0..($args.Length - 2)] + @("--hidden-import", "brake.detectors.anime_onnx_export") + $args[-1]
    } else {
        $args = $args[0..($args.Length - 2)] + @(
            "--exclude-module", "torch",
            "--exclude-module", "transformers",
            "--exclude-module", "onnx",
            "--exclude-module", "huggingface_hub"
        ) + $args[-1]
    }
    if ($windowed) {
        $args = @("-m", "PyInstaller", "--windowed") + $args[2..($args.Length - 1)]
    }
    Write-Host ""
    Write-Host "Building $name..."
    python @args
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed for $name with exit code $LASTEXITCODE" }
}

Build-App "BrakeAgent" "packaging\entry_agent.py" $true "Brake Agent" -NeedsNudeNet
Build-App "BrakeBoot" "packaging\entry_boot.py" $true "Brake Startup Recovery"
Build-App "BrakeBridge" "packaging\entry_bridge.py" $false "Brake Desktop Bridge"
Build-App "BrakeLockout" "packaging\entry_lockout.py" $true "Brake Lockout" -NeedsPyQt
Build-App "BrakeUninstallGuard" "packaging\entry_uninstall_guard.py" $true "Brake Uninstall Guard" -NeedsPyQt
Build-App "BrakeService" "packaging\entry_service.py" $false "Brake Service"
Build-App "BrakeWatchdog" "packaging\entry_watchdog.py" $false "Brake Watchdog"

Write-Host ""
Write-Host "Flattening executable folders into $bundle..."
foreach ($name in @("BrakeAgent", "BrakeBoot", "BrakeBridge", "BrakeLockout", "BrakeUninstallGuard", "BrakeService", "BrakeWatchdog")) {
    $src = Join-Path $distRoot $name
    if (-not (Test-Path $src)) { throw "Missing build output: $src" }
    Copy-Item -Path (Join-Path $src "*") -Destination $bundle -Recurse -Force
    Remove-Item -LiteralPath $src -Recurse -Force
}

$installerBundle = Join-Path $bundle "installer"
if (Test-Path $installerBundle) {
    Remove-Item -LiteralPath $installerBundle -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $installerBundle | Out-Null
Copy-Item -Path (Join-Path $repoRoot "installer\*") -Destination $installerBundle -Recurse -Force
Copy-Item -Path (Join-Path $repoRoot "README.md") -Destination $bundle -Force
Copy-Item -Path (Join-Path $repoRoot "LICENSE") -Destination $bundle -Force
Copy-Item -Path (Join-Path $repoRoot "PRIVACY.md") -Destination $bundle -Force
Copy-Item -Path (Join-Path $repoRoot "SECURITY.md") -Destination $bundle -Force

$zip = Join-Path $distRoot "Brake-$Version-portable-dev.zip"
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
Write-Host "Next: package the Electron shell as Brake.exe, then run packaging\build_inno.ps1 to create BrakeSetup-$Version.exe"
