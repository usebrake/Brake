# Brake read-only diagnostics.
# Run from the Brake repo root: .\scripts\doctor.ps1

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

function Command-Version($Command, $Args) {
    $cmd = Get-Command $Command -ErrorAction SilentlyContinue
    if (-not $cmd) { return $null }
    try {
        $exe = if ($Command -eq "npm") { "npm.cmd" } else { $Command }
        $line = & $exe @Args 2>&1 | Select-Object -First 1
        if ($LASTEXITCODE -ne 0 -and -not $line) { return $null }
        return "$line"
    } catch {
        return "found at $($cmd.Source)"
    }
}

Write-Host "Brake diagnostics"
Write-Host "Repo: $RepoRoot"
Write-Host ""

Result "Repo folder" (Test-Path (Join-Path $RepoRoot "brake\desktop_bridge.py"))
Result "Desktop app" (Test-Path (Join-Path $RepoRoot "desktop\package.json"))
Result "Source launcher" (Test-Path (Join-Path $RepoRoot "start-brake-dev.bat"))
Result "Installer" (Test-Path (Join-Path $RepoRoot "installer\install.bat"))

$py = Command-Version "python" @("--version")
Result "Python" ($null -ne $py) $py

$node = Command-Version "node" @("--version")
Result "Node.js" ($null -ne $node) $node

$npm = Command-Version "npm" @("--version")
Result "npm" ($null -ne $npm) $npm

if ($py) {
    try {
        $import = & python -c "import brake, sys; print(brake.__file__)" 2>$null
        Result "Python can import brake" ($LASTEXITCODE -eq 0) $import
    } catch {
        Result "Python can import brake" $false $_.Exception.Message
    }
}

$shortcutMachine = Join-Path $env:ProgramData "Microsoft\Windows\Start Menu\Programs\Brake\Brake.lnk"
$shortcutUser = Join-Path $env:AppData "Microsoft\Windows\Start Menu\Programs\Brake\Brake.lnk"
Result "Start Menu shortcut" ((Test-Path $shortcutMachine) -or (Test-Path $shortcutUser))

foreach ($svc in @("BrakeService", "BrakeWatchdog")) {
    $query = & sc.exe query $svc 2>$null
    Result "$svc service" ($LASTEXITCODE -eq 0) (($query | Select-String "STATE" | Select-Object -First 1).Line)
}

$dataDir = Join-Path $env:ProgramData "Brake"
Result "ProgramData folder" (Test-Path $dataDir) $dataDir

if (Test-Path $dataDir) {
    Result "State file" (Test-Path (Join-Path $dataDir "state.json"))
    Result "Recovery file" (Test-Path (Join-Path $dataDir "recovery.json"))
}

$animeDir = Join-Path $dataDir "models\anime_nsfw"
if (Test-Path $animeDir) {
    Result "Anime model folder" $true $animeDir
} else {
    Write-Host "[INFO] Anime model folder not present. This is normal until installed."
}

Write-Host ""
if ($Problems -gt 0) {
    Write-Host "$Problems warning(s) found. Paste this output into a GitHub issue if you need help." -ForegroundColor Yellow
    exit 1
}

Write-Host "No obvious setup problems found." -ForegroundColor Green
exit 0