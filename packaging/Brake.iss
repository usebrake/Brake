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
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription=Brake Setup
VersionInfoProductName=Brake
VersionInfoProductVersion=0.1.3.0
VersionInfoTextVersion={#MyAppVersion}
VersionInfoVersion=0.1.3.0
DefaultDirName={autopf}\\Brake
DefaultGroupName=Brake
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=BrakeSetup-{#MyAppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\desktop\src\assets\brake-ring.ico
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
LicenseFile=..\LICENSE
CloseApplications=no

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\\Brake"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\resources\app\src\assets\brake-ring.ico"; AppUserModelID: "com.usebrake.Brake"
Name: "{commondesktop}\\Brake"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\resources\app\src\assets\brake-ring.ico"; AppUserModelID: "com.usebrake.Brake"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Run]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\installer\register_service.ps1"" -NoPrompt"; StatusMsg: "Installing Brake services..."; Flags: runhidden waituntilterminated
Filename: "{app}\{#MyAppExeName}"; Description: "Launch Brake"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\installer\unregister_service.ps1"""; Flags: runhidden waituntilterminated; RunOnceId: "RemoveBrakeServices"

[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
  StopScript: String;
begin
  StopScript := ExpandConstant('{app}\installer\stop_for_update.ps1');
  if FileExists(StopScript) then
  begin
    Exec(
      ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
      '-NoProfile -ExecutionPolicy Bypass -File "' + StopScript + '"',
      '',
      SW_HIDE,
      ewWaitUntilTerminated,
      ResultCode
    );
  end;
  Result := '';
end;
