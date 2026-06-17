param(
    [Parameter(Mandatory = $true)]
    [string]$ExePath,

    [Parameter(Mandatory = $true)]
    [string]$IconPath
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
        bool ok = UpdateResource(
            handle,
            MakeIntResource(type),
            MakeIntResource(name),
            0,
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
    [ResourceUpdater]::End($handle)
    $handle = [IntPtr]::Zero
} catch {
    if ($handle -ne [IntPtr]::Zero) {
        [ResourceUpdater]::Discard($handle)
    }
    throw
}

Write-Host "Stamped icon into $ExePath"
