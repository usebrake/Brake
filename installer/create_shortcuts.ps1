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
        Args = "-m lockitup.gui"
    }
}

$target = Resolve-GuiTarget
$shortcutDir = Join-Path $env:ProgramData "Microsoft\Windows\Start Menu\Programs\Brake"
$shortcutPath = Join-Path $shortcutDir "Brake.lnk"
$legacyShortcutDir = Join-Path $env:ProgramData "Microsoft\Windows\Start Menu\Programs\LockItUp"
$iconPath = Join-Path $RepoRoot "lockitup\gui\assets\brake.ico"

New-Item -ItemType Directory -Force -Path $shortcutDir | Out-Null
if (Test-Path $legacyShortcutDir) {
    Remove-Item -LiteralPath $legacyShortcutDir -Recurse -Force
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
