param(
    [string]$Version = "0.1.4-beta",
    [string]$InnoCompiler = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$bundle = Join-Path $repoRoot "dist\\Brake"
if (-not (Test-Path $bundle)) {
    throw "Missing $bundle. Run packaging\build_pyinstaller.ps1 first."
}

if (-not $InnoCompiler) {
    $candidates = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
    )
    foreach ($c in $candidates) {
        if ($c -and (Test-Path $c)) {
            $InnoCompiler = $c
            break
        }
    }
}

if (-not $InnoCompiler -or -not (Test-Path $InnoCompiler)) {
    throw "Inno Setup compiler not found. Install Inno Setup 6 or pass -InnoCompiler C:\Path\ISCC.exe"
}

$env:BRAKE_BUILD_VERSION = $Version
& $InnoCompiler (Join-Path $repoRoot "packaging\brake.iss")
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed with exit code $LASTEXITCODE" }

$installer = Join-Path $repoRoot "dist\\BrakeSetup-$Version.exe"
if (Test-Path $installer) {
    $latestInstaller = Join-Path $repoRoot "dist\\BrakeSetup.exe"
    Copy-Item -LiteralPath $installer -Destination $latestInstaller -Force

    $checksumsPath = Join-Path $repoRoot "dist\SHA256SUMS.txt"
    $existingChecksums = @()
    if (Test-Path $checksumsPath) {
        $existingChecksums = Get-Content -LiteralPath $checksumsPath | Where-Object {
            $_ -notmatch "  BrakeSetup(?:-$([regex]::Escape($Version)))?\.exe$"
        }
    }
    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $installer).Hash.ToLowerInvariant()
    $updatedChecksums = @($existingChecksums) + @(
        "$hash  BrakeSetup-$Version.exe",
        "$hash  BrakeSetup.exe"
    )
    Set-Content -Encoding ASCII -LiteralPath $checksumsPath -Value $updatedChecksums
}

Write-Host "Installer complete: $installer"
