param(
    [string]$Version = "0.1.4-beta",
    [switch]$SkipInstallPyInstaller,
    [Alias("Resume")]
    [switch]$Incremental,
    [string[]]$Components = @()
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$distRoot = Join-Path $repoRoot "dist"
$workRoot = Join-Path $repoRoot "build\pyinstaller"
$specRoot = Join-Path $repoRoot "build\spec"
$bundle = Join-Path $distRoot "brake"
$pythonExe = (Get-Command python -ErrorAction Stop).Source
$foreignBuildPathPattern = '(?i)[\\/](?:\.cache[\\/]codex-runtimes|\.codex[\\/]plugins[\\/]cache)[\\/]'
$allComponents = @(
    "BrakeAgent",
    "BrakeBoot",
    "BrakeBridge",
    "BrakeLockout",
    "BrakeUninstallGuard",
    "BrakeService",
    "BrakeWatchdog"
)
$Components = @(
    $Components |
        ForEach-Object { $_ -split "," } |
        ForEach-Object { $_.Trim() } |
        Where-Object { $_ }
)

if ($Components.Count -gt 0) {
    $unknownComponents = @($Components | Where-Object { $_ -notin $allComponents })
    if ($unknownComponents.Count -gt 0) {
        throw "Unknown component(s): $($unknownComponents -join ', '). Valid components: $($allComponents -join ', ')"
    }
    $selectedComponents = @($Components | Select-Object -Unique)
} else {
    $selectedComponents = $allComponents
}

Write-Host "Repo: $repoRoot"
Write-Host "Bundle: $bundle"

if (-not $SkipInstallPyInstaller) {
    Write-Host "Ensuring PyInstaller is installed for this Python..."
    python -m pip install --upgrade pyinstaller
}

if ($Incremental) {
    if (-not (Test-Path $bundle)) {
        throw "Incremental build requires an existing bundle at $bundle. Run a clean full build first."
    }
} else {
    foreach ($path in @($bundle, $workRoot, $specRoot)) {
        if (Test-Path $path) {
            Remove-Item -LiteralPath $path -Recurse -Force
        }
    }
    foreach ($name in $allComponents) {
        $componentOutput = Join-Path $distRoot $name
        if (Test-Path $componentOutput) {
            Remove-Item -LiteralPath $componentOutput -Recurse -Force
        }
    }
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
    $configSrc = Join-Path $repoRoot "config"
    $assetsSrc = Join-Path $repoRoot "brake\\gui\assets"
    $iconSrc = Join-Path $repoRoot "brake\\gui\assets\brake.ico"
    $stylesSrc = Join-Path $repoRoot "brake\\gui\styles.qss"
    $entrySrc = Join-Path $repoRoot $entry
    $versionFile = Write-VersionFile $name $description
    $args = @(
        "-m", "PyInstaller",
        "--noconfirm",
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
            # Let PyInstaller's Qt hooks include the Windows platform and
            # image plugins required by these modules. Collecting all of
            # PyQt6 also pulls in unused QML, QtQuick3D, multimedia,
            # Bluetooth, PDF, SQL, bindings, translations, and tools.
            "--hidden-import", "PyQt6.QtCore",
            "--hidden-import", "PyQt6.QtGui",
            "--hidden-import", "PyQt6.QtWidgets",
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
    $originalPath = $env:PATH
    $originalPythonPath = $env:PYTHONPATH
    $originalQtPluginPath = $env:QT_PLUGIN_PATH
    $originalQmlImportPath = $env:QML2_IMPORT_PATH
    try {
        # PyInstaller searches PATH while resolving native dependencies. Codex
        # adds its own media/runtime DLL directories to PATH, and collecting
        # those DLLs creates an incompatible mixed C/C++ runtime in Brake.
        $env:PATH = (($originalPath -split ';') | Where-Object {
            $_ -and $_ -notmatch $foreignBuildPathPattern
        }) -join ';'
        $env:PYTHONPATH = $null
        $env:QT_PLUGIN_PATH = $null
        $env:QML2_IMPORT_PATH = $null

        & $pythonExe @args
        $pyInstallerExitCode = $LASTEXITCODE
    } finally {
        $env:PATH = $originalPath
        $env:PYTHONPATH = $originalPythonPath
        $env:QT_PLUGIN_PATH = $originalQtPluginPath
        $env:QML2_IMPORT_PATH = $originalQmlImportPath
    }
    if ($pyInstallerExitCode -ne 0) { throw "PyInstaller failed for $name with exit code $pyInstallerExitCode" }

    $analysisToc = Join-Path $workRoot "$name\Analysis-00.toc"
    if (Test-Path -LiteralPath $analysisToc) {
        $foreignRuntimeReference = Select-String -LiteralPath $analysisToc -Pattern 'codex-runtimes|\.codex[\\\\/]plugins[\\\\/]cache' -Quiet
        if ($foreignRuntimeReference) {
            throw "PyInstaller resolved $name against a Codex-owned native runtime. Refusing to merge a contaminated bundle."
        }
    }
}

if ("BrakeAgent" -in $selectedComponents) {
    Build-App "BrakeAgent" "packaging\entry_agent.py" $true "Brake Agent" -NeedsNudeNet
}
if ("BrakeBoot" -in $selectedComponents) {
    Build-App "BrakeBoot" "packaging\entry_boot.py" $true "Brake Startup Recovery"
}
if ("BrakeBridge" -in $selectedComponents) {
    Build-App "BrakeBridge" "packaging\entry_bridge.py" $false "Brake Desktop Bridge"
}
if ("BrakeLockout" -in $selectedComponents) {
    Build-App "BrakeLockout" "packaging\entry_lockout.py" $true "Brake Lockout" -NeedsPyQt
}
if ("BrakeUninstallGuard" -in $selectedComponents) {
    Build-App "BrakeUninstallGuard" "packaging\entry_uninstall_guard.py" $true "Brake Uninstall Guard" -NeedsPyQt
}
if ("BrakeService" -in $selectedComponents) {
    Build-App "BrakeService" "packaging\entry_service.py" $false "Brake Service"
}
if ("BrakeWatchdog" -in $selectedComponents) {
    Build-App "BrakeWatchdog" "packaging\entry_watchdog.py" $false "Brake Watchdog"
}

Write-Host ""
Write-Host "Flattening executable folders into $bundle..."
foreach ($name in $selectedComponents) {
    $src = Join-Path $distRoot $name
    if (-not (Test-Path $src)) { throw "Missing build output: $src" }
    Copy-Item -Path (Join-Path $src "*") -Destination $bundle -Recurse -Force
    Remove-Item -LiteralPath $src -Recurse -Force
}

# Brake's Qt windows use hard-coded English text plus PNG and ICO assets.
# These files are pulled in conservatively by PyInstaller's QtGui hook but
# have no runtime callers in Brake. Keep every other Qt dependency that the
# hook selected, including the Windows platform, style, and touch plugins.
$qtRoot = Join-Path $bundle "_internal\PyQt6\Qt6"
$unusedQtPaths = @(
    (Join-Path $qtRoot "translations"),
    (Join-Path $qtRoot "bin\Qt6Pdf.dll"),
    (Join-Path $qtRoot "bin\Qt6Svg.dll"),
    (Join-Path $qtRoot "plugins\iconengines\qsvgicon.dll"),
    (Join-Path $qtRoot "plugins\imageformats\qgif.dll"),
    (Join-Path $qtRoot "plugins\imageformats\qicns.dll"),
    (Join-Path $qtRoot "plugins\imageformats\qjpeg.dll"),
    (Join-Path $qtRoot "plugins\imageformats\qpdf.dll"),
    (Join-Path $qtRoot "plugins\imageformats\qsvg.dll"),
    (Join-Path $qtRoot "plugins\imageformats\qtga.dll"),
    (Join-Path $qtRoot "plugins\imageformats\qtiff.dll"),
    (Join-Path $qtRoot "plugins\imageformats\qwbmp.dll"),
    (Join-Path $qtRoot "plugins\imageformats\qwebp.dll")
)
foreach ($path in $unusedQtPaths) {
    if (Test-Path $path) {
        Remove-Item -LiteralPath $path -Recurse -Force
    }
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
$releaseFiles = @()
if (-not $Incremental) {
    if (Test-Path $zip) { Remove-Item -LiteralPath $zip -Force }
    Compress-Archive -Path (Join-Path $bundle "*") -DestinationPath $zip
    $releaseFiles += $zip
}

$shaFile = Join-Path $distRoot "SHA256SUMS.txt"
$releaseFiles += @(Get-ChildItem -Path $bundle -Filter "*.exe" -File | Sort-Object Name | ForEach-Object { $_.FullName })
$releaseFiles |
    ForEach-Object {
        $rel = $_.Substring($distRoot.Length + 1).Replace("\", "/")
        $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $_).Hash.ToLowerInvariant()
        "$hash  $rel"
    } | Set-Content -Encoding ASCII $shaFile

Write-Host ""
Write-Host "PyInstaller bundle complete:"
Write-Host "  $bundle"
if (-not $Incremental) {
    Write-Host "  $zip"
}
Write-Host "  $shaFile"
Write-Host ""
Write-Host "Next: package the Electron shell as Brake.exe, then run packaging\build_inno.ps1 to create BrakeSetup-$Version.exe"
