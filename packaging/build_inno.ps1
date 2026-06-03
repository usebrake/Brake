param(
    [string]$Version = "0.1.0-beta",
    [string]$InnoCompiler = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$bundle = Join-Path $repoRoot "dist\LockItUp"
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

$env:LOCKITUP_BUILD_VERSION = $Version
& $InnoCompiler (Join-Path $repoRoot "packaging\LockItUp.iss")
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed with exit code $LASTEXITCODE" }

$installer = Join-Path $repoRoot "dist\LockItUpSetup-$Version.exe"
if (Test-Path $installer) {
    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $installer).Hash.ToLowerInvariant()
    Add-Content -Encoding ASCII -Path (Join-Path $repoRoot "dist\SHA256SUMS.txt") -Value "$hash  LockItUpSetup-$Version.exe"
}

Write-Host "Installer complete: $installer"
