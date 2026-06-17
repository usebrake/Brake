param(
    [Parameter(Mandatory = $true)]
    [string]$ExePath,

    [Parameter(Mandatory = $true)]
    [string]$IconPath,

    [string]$Version = "0.1.3.0",
    [string]$FileDescription = "Brake",
    [string]$ProductName = "Brake",
    [string]$CompanyName = "usebrake",
    [string]$InternalName = "Brake.exe",
    [string]$OriginalFilename = "Brake.exe"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $ExePath)) {
    throw "Executable not found: $ExePath"
}
if (-not (Test-Path -LiteralPath $IconPath)) {
    throw "Icon not found: $IconPath"
}

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;

public static class ResourceUpdater
{
    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    private static extern IntPtr BeginUpdateResource(string pFileName, bool bDeleteExistingResources);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool UpdateResource(
        IntPtr hUpdate,
        IntPtr lpType,
        IntPtr lpName,
        ushort wLanguage,
        byte[] lpData,
        uint cbData
    );

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool EndUpdateResource(IntPtr hUpdate, bool fDiscard);

    public static IntPtr MakeIntResource(int value)
    {
        return new IntPtr(value);
    }

    public static IntPtr Begin(string path)
    {
        IntPtr handle = BeginUpdateResource(path, false);
        if (handle == IntPtr.Zero)
        {
            throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
        }
        return handle;
    }

    public static void Update(IntPtr handle, int type, int name, byte[] data)
    {
        UpdateWithLanguage(handle, type, name, 0, data);
    }

    public static void UpdateWithLanguage(IntPtr handle, int type, int name, ushort language, byte[] data)
    {
        bool ok = UpdateResource(
            handle,
            MakeIntResource(type),
            MakeIntResource(name),
            language,
            data,
            (uint)data.Length
        );
        if (!ok)
        {
            throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
        }
    }

    public static void End(IntPtr handle)
    {
        bool ok = EndUpdateResource(handle, false);
        if (!ok)
        {
            throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
        }
    }

    public static void Discard(IntPtr handle)
    {
        EndUpdateResource(handle, true);
    }
}
"@

function Read-UInt16($Bytes, [int]$Offset) {
    return [BitConverter]::ToUInt16($Bytes, $Offset)
}

function Read-UInt32($Bytes, [int]$Offset) {
    return [BitConverter]::ToUInt32($Bytes, $Offset)
}

function Add-UInt16($List, [int]$Value) {
    $List.AddRange([BitConverter]::GetBytes([uint16]$Value))
}

function Add-UInt32($List, [uint32]$Value) {
    $List.AddRange([BitConverter]::GetBytes($Value))
}

function UInt32-Hex([string]$Value) {
    return [Convert]::ToUInt32($Value, 16)
}

function Add-UnicodeZ($List, [string]$Value) {
    $List.AddRange([Text.Encoding]::Unicode.GetBytes($Value))
    Add-UInt16 $List 0
}

function Align-Dword($List) {
    while (($List.Count % 4) -ne 0) {
        $List.Add([byte]0)
    }
}

function Set-UInt16At($List, [int]$Offset, [int]$Value) {
    $bytes = [BitConverter]::GetBytes([uint16]$Value)
    $List[$Offset] = $bytes[0]
    $List[$Offset + 1] = $bytes[1]
}

function Start-VersionBlock($List, [string]$Key, [int]$ValueLength, [int]$Type) {
    $start = $List.Count
    Add-UInt16 $List 0
    Add-UInt16 $List $ValueLength
    Add-UInt16 $List $Type
    Add-UnicodeZ $List $Key
    Align-Dword $List
    return $start
}

function End-VersionBlock($List, [int]$Start) {
    Set-UInt16At $List $Start ($List.Count - $Start)
}

function Get-VersionParts([string]$Value) {
    $parts = @($Value -split "[^0-9]+" | Where-Object { $_ -ne "" } | ForEach-Object { [int]$_ })
    while ($parts.Count -lt 4) {
        $parts += 0
    }
    return $parts[0..3]
}

function Add-VersionString($List, [string]$Key, [string]$Value) {
    $start = Start-VersionBlock $List $Key ($Value.Length + 1) 1
    Add-UnicodeZ $List $Value
    Align-Dword $List
    End-VersionBlock $List $start
}

function New-VersionResource {
    $parts = Get-VersionParts $Version
    $fileVersionMs = ([uint32]$parts[0] -shl 16) -bor [uint32]$parts[1]
    $fileVersionLs = ([uint32]$parts[2] -shl 16) -bor [uint32]$parts[3]

    $strings = [ordered]@{
        CompanyName = $CompanyName
        FileDescription = $FileDescription
        FileVersion = $Version
        InternalName = $InternalName
        LegalCopyright = "Copyright (C) 2026 usebrake"
        OriginalFilename = $OriginalFilename
        ProductName = $ProductName
        ProductVersion = $Version
    }

    $list = New-Object 'System.Collections.Generic.List[byte]'
    $root = Start-VersionBlock $list "VS_VERSION_INFO" 52 0

    Add-UInt32 $list (UInt32-Hex "FEEF04BD")
    Add-UInt32 $list (UInt32-Hex "00010000")
    Add-UInt32 $list $fileVersionMs
    Add-UInt32 $list $fileVersionLs
    Add-UInt32 $list $fileVersionMs
    Add-UInt32 $list $fileVersionLs
    Add-UInt32 $list (UInt32-Hex "0000003F")
    Add-UInt32 $list 0
    Add-UInt32 $list (UInt32-Hex "00040004")
    Add-UInt32 $list 1
    Add-UInt32 $list 0
    Add-UInt32 $list 0
    Add-UInt32 $list 0
    Align-Dword $list

    $stringFileInfo = Start-VersionBlock $list "StringFileInfo" 0 1
    $stringTable = Start-VersionBlock $list "040904b0" 0 1
    foreach ($key in $strings.Keys) {
        Add-VersionString $list $key $strings[$key]
    }
    End-VersionBlock $list $stringTable
    End-VersionBlock $list $stringFileInfo

    $varFileInfo = Start-VersionBlock $list "VarFileInfo" 0 1
    $translation = Start-VersionBlock $list "Translation" 4 0
    Add-UInt16 $list 0x0409
    Add-UInt16 $list 0x04B0
    Align-Dword $list
    End-VersionBlock $list $translation
    End-VersionBlock $list $varFileInfo

    End-VersionBlock $list $root
    return $list.ToArray()
}

$ico = [IO.File]::ReadAllBytes((Resolve-Path -LiteralPath $IconPath))
if ($ico.Length -lt 6) {
    throw "Invalid ICO file: $IconPath"
}

$reserved = Read-UInt16 $ico 0
$type = Read-UInt16 $ico 2
$count = Read-UInt16 $ico 4
if ($reserved -ne 0 -or $type -ne 1 -or $count -lt 1) {
    throw "Invalid ICO header: $IconPath"
}

$entries = @()
for ($i = 0; $i -lt $count; $i++) {
    $offset = 6 + ($i * 16)
    if (($offset + 16) -gt $ico.Length) {
        throw "Invalid ICO directory: $IconPath"
    }

    $imageSize = [int](Read-UInt32 $ico ($offset + 8))
    $imageOffset = [int](Read-UInt32 $ico ($offset + 12))
    if ($imageSize -lt 1 -or $imageOffset -lt 0 -or ($imageOffset + $imageSize) -gt $ico.Length) {
        throw "Invalid ICO image entry: $IconPath"
    }

    $image = New-Object byte[] $imageSize
    [Array]::Copy($ico, $imageOffset, $image, 0, $imageSize)

    $entries += [PSCustomObject]@{
        Width = $ico[$offset]
        Height = $ico[$offset + 1]
        ColorCount = $ico[$offset + 2]
        Reserved = $ico[$offset + 3]
        Planes = Read-UInt16 $ico ($offset + 4)
        BitCount = Read-UInt16 $ico ($offset + 6)
        ImageSize = $imageSize
        Image = $image
        ResourceId = $i + 1
    }
}

$group = New-Object byte[] (6 + ($count * 14))
[BitConverter]::GetBytes([uint16]0).CopyTo($group, 0)
[BitConverter]::GetBytes([uint16]1).CopyTo($group, 2)
[BitConverter]::GetBytes([uint16]$count).CopyTo($group, 4)
for ($i = 0; $i -lt $count; $i++) {
    $entry = $entries[$i]
    $offset = 6 + ($i * 14)
    $group[$offset] = $entry.Width
    $group[$offset + 1] = $entry.Height
    $group[$offset + 2] = $entry.ColorCount
    $group[$offset + 3] = $entry.Reserved
    [BitConverter]::GetBytes([uint16]$entry.Planes).CopyTo($group, $offset + 4)
    [BitConverter]::GetBytes([uint16]$entry.BitCount).CopyTo($group, $offset + 6)
    [BitConverter]::GetBytes([uint32]$entry.ImageSize).CopyTo($group, $offset + 8)
    [BitConverter]::GetBytes([uint16]$entry.ResourceId).CopyTo($group, $offset + 12)
}

$handle = [IntPtr]::Zero
try {
    $handle = [ResourceUpdater]::Begin((Resolve-Path -LiteralPath $ExePath))
    foreach ($entry in $entries) {
        [ResourceUpdater]::Update($handle, 3, $entry.ResourceId, $entry.Image)
    }

    # ID 1 is the normal application icon group. 32512 is also updated because
    # some Windows shells prefer the default application resource ID.
    [ResourceUpdater]::Update($handle, 14, 1, $group)
    [ResourceUpdater]::Update($handle, 14, 32512, $group)

    $versionResource = New-VersionResource
    [ResourceUpdater]::UpdateWithLanguage($handle, 16, 1, 0, $versionResource)
    [ResourceUpdater]::UpdateWithLanguage($handle, 16, 1, 1033, $versionResource)

    [ResourceUpdater]::End($handle)
    $handle = [IntPtr]::Zero
} catch {
    if ($handle -ne [IntPtr]::Zero) {
        [ResourceUpdater]::Discard($handle)
    }
    throw
}

Write-Host "Stamped icon and metadata into $ExePath"
