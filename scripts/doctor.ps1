# Brake read-only diagnostics.
# Run from the Brake repo root: .\scripts\doctor.ps1

$ErrorActionPreference = "Continue"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$InstallRoot = Join-Path $env:ProgramFiles "Brake"
$Problems = 0

function Result($Name, $Ok, $Detail = "", $Hint = "") {
    if ($Ok) {
        Write-Host "[OK]   $Name $Detail" -ForegroundColor Green
    } else {
        Write-Host "[WARN] $Name $Detail" -ForegroundColor Yellow
        if ($Hint) { Write-Host "       $Hint" -ForegroundColor DarkYellow }
        $script:Problems += 1
    }
}

function Info($Message) {
    Write-Host "[INFO] $Message"
}

function Command-Version($Command, $Args) {
    $cmd = Get-Command $Command -ErrorAction SilentlyContinue
    if (-not $cmd) { return $null }
    try {
        $commandLine = "$Command $($Args -join ' ')"
        $line = & cmd.exe /d /c $commandLine 2>&1 | Select-Object -First 1
        if ($LASTEXITCODE -ne 0 -and -not $line) { return $null }
        return "$line"
    } catch {
        return "found at $($cmd.Source)"
    }
}

function Same-Path($a, $b) {
    try {
        $ra = (Resolve-Path $a -ErrorAction Stop).Path.TrimEnd('\')
    } catch {
        $ra = [System.IO.Path]::GetFullPath($a).TrimEnd('\')
    }
    try {
        $rb = (Resolve-Path $b -ErrorAction Stop).Path.TrimEnd('\')
    } catch {
        $rb = [System.IO.Path]::GetFullPath($b).TrimEnd('\')
    }
    return [string]::Equals($ra, $rb, [StringComparison]::OrdinalIgnoreCase)
}

Write-Host "Brake diagnostics"
Write-Host "Current folder: $RepoRoot"
Write-Host "Installed app folder: $InstallRoot"
Write-Host ""

if (Same-Path $RepoRoot $InstallRoot) {
    Info "This script is running from the installed app folder."
} else {
    Info "This script is running from a source/download folder. The installed app should live in Program Files after install."
}

Result "Source files present" (Test-Path (Join-Path $RepoRoot "brake\desktop_bridge.py"))
Result "Desktop app present" (Test-Path (Join-Path $RepoRoot "desktop\package.json"))
Result "Installer scripts present" (Test-Path (Join-Path $RepoRoot "installer\register_service.ps1"))
Result "Installed app folder" (Test-Path $InstallRoot) $InstallRoot "Run the latest BrakeSetup.exe to reinstall."

$py = Command-Version "python" @("--version")
Result "Python" ($null -ne $py) $py "Install Python 3.11+ x64 and check Add python.exe to PATH."

$node = Command-Version "node" @("--version")
Result "Node.js" ($null -ne $node) $node "Install Node.js LTS from nodejs.org."

$npm = Command-Version "npm" @("--version")
Result "npm" ($null -ne $npm) $npm "Node.js LTS should install npm."

if ($py) {
    try {
        $import = & python -c "import brake, sys; print(brake.__file__)" 2>$null
        Result "Python can import brake" ($LASTEXITCODE -eq 0) $import "If this fails after install, run the latest BrakeSetup.exe again."
    } catch {
        Result "Python can import brake" $false $_.Exception.Message
    }
}

$shortcutMachine = Join-Path $env:ProgramData "Microsoft\Windows\Start Menu\Programs\Brake\Brake.lnk"
$shortcutUser = Join-Path $env:AppData "Microsoft\Windows\Start Menu\Programs\Brake\Brake.lnk"
Result "Start Menu shortcut" ((Test-Path $shortcutMachine) -or (Test-Path $shortcutUser)) "" "Run the latest BrakeSetup.exe. This is expected after uninstall."

foreach ($svc in @("BrakeService", "BrakeWatchdog")) {
    $query = & sc.exe query $svc 2>$null
    $stateLine = ($query | Select-String "STATE" | Select-Object -First 1).Line
    $exists = $LASTEXITCODE -eq 0
    $running = $exists -and ($stateLine -match "RUNNING")
    Result "$svc service exists" $exists $stateLine "Run the latest BrakeSetup.exe to register services."
    if ($exists) {
        Result "$svc service running" $running $stateLine "If installed, run the latest BrakeSetup.exe again or restart the Brake services."
    }
}

$dataDir = Join-Path $env:ProgramData "Brake"
Result "ProgramData folder" (Test-Path $dataDir) $dataDir "This is created after install or first launch."

if (Test-Path $dataDir) {
    $stateExists = Test-Path (Join-Path $dataDir "state.json")
    $recoveryExists = Test-Path (Join-Path $dataDir "recovery.json")
    Result "State file" $stateExists "" "Normal before first setup or after uninstall."
    Result "Recovery file" $recoveryExists "" "Normal before first setup or after uninstall."
}

$animeDir = Join-Path $dataDir "models\anime_nsfw"
if (Test-Path $animeDir) {
    Result "Anime model folder" $true $animeDir
} else {
    Info "Illustrated model folder not present. This is normal until installed from the Illustrated tab."
}

Write-Host ""
if ($Problems -gt 0) {
    Write-Host "$Problems warning(s) found. Some are normal after uninstall or before first setup." -ForegroundColor Yellow
    exit 1
}

Write-Host "No obvious setup problems found." -ForegroundColor Green
exit 0
