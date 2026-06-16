#define MyAppName "Brake"
#define MyAppVersion GetEnv("BRAKE_BUILD_VERSION")
#if MyAppVersion == ""
#define MyAppVersion "0.1.0-beta"
#endif
#define MyAppPublisher "UseBrake"
#define MyAppExeName "Brake.exe"
#define SourceDir "..\dist\\Brake"

[Setup]
AppId={{7D093DB2-55F5-4499-8F08-663E3C465625}
AppName=Brake
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\\Brake
DefaultGroupName=Brake
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=BrakeSetup-{#MyAppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
LicenseFile=..\LICENSE

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\\Brake"; Filename: "{app}\{#MyAppExeName}"
Name: "{commondesktop}\\Brake"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Run]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\installer\register_service.ps1"""; StatusMsg: "Installing Brake services..."; Flags: runhidden waituntilterminated
Filename: "{app}\{#MyAppExeName}"; Description: "Launch Brake"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\installer\unregister_service.ps1"""; Flags: runhidden waituntilterminated
