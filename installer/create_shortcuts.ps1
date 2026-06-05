param(
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$PythonPath = "",
    [string]$GuiExe = ""
)

$ErrorActionPreference = "Stop"

function Resolve-GuiTarget {
    if ($GuiExe -and (Test-Path $GuiExe)) {
        return @{
            Target = (Resolve-Path $GuiExe).Path
            Args = ""
        }
    }

    $sourceVbs = Join-Path $RepoRoot "start-brake.vbs"
    if (Test-Path $sourceVbs) {
        return @{
            Target = (Join-Path $env:SystemRoot "System32\wscript.exe")
            Args = "`"$((Resolve-Path $sourceVbs).Path)`""
        }
    }

    $sourceLauncher = Join-Path $RepoRoot "start-brake-dev.bat"
    if (Test-Path $sourceLauncher) {
        return @{
            Target = (Resolve-Path $sourceLauncher).Path
            Args = ""
        }
    }

    if (-not $PythonPath) {
        $cmd = Get-Command python -ErrorAction Stop
        $PythonPath = $cmd.Path
    }

    $pythonDir = Split-Path -Parent $PythonPath
    $pythonw = Join-Path $pythonDir "pythonw.exe"
    if (-not (Test-Path $pythonw)) {
        $pythonw = $PythonPath
    }

    return @{
        Target = $pythonw
        Args = "-m brake.gui"
    }
}

$target = Resolve-GuiTarget
$shortcutDir = Join-Path $env:ProgramData "Microsoft\Windows\Start Menu\Programs\Brake"
$shortcutPath = Join-Path $shortcutDir "Brake.lnk"
$legacyShortcutPath = Join-Path $shortcutDir "brake.lnk"
$iconPath = Join-Path $RepoRoot "desktop\src\assets\brake-ring.ico"
if (-not (Test-Path $iconPath)) {
    $iconPath = Join-Path $RepoRoot "brake\gui\assets\brake.ico"
}

New-Item -ItemType Directory -Force -Path $shortcutDir | Out-Null
if (Test-Path $legacyShortcutPath) {
    Remove-Item -LiteralPath $legacyShortcutPath -Force
}

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $target.Target
$shortcut.Arguments = $target.Args
$shortcut.WorkingDirectory = $RepoRoot
$shortcut.Description = "Open Brake"
if (Test-Path $iconPath) {
    $shortcut.IconLocation = $iconPath
}
$shortcut.Save()

Write-Host "Created Start Menu shortcut: $shortcutPath"
Write-Host "Shortcut target: $($target.Target) $($target.Args)"