#define MyAppName "Brake"
#define MyAppVersion GetEnv("BRAKE_BUILD_VERSION")
#if MyAppVersion == ""
#define MyAppVersion "0.1.5-beta"
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
VersionInfoProductVersion=0.1.5.0
VersionInfoTextVersion={#MyAppVersion}
VersionInfoVersion=0.1.5.0
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

[InstallDelete]
; _internal is generated packaging output and contains no Brake user data.
; Clear it during upgrades so removed or incompatible DLLs cannot survive
; from an older installation and override the replacement bundle.
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{group}\\Brake"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\resources\app\src\assets\brake-ring.ico"; AppUserModelID: "com.usebrake.Brake"
Name: "{commondesktop}\\Brake"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\resources\app\src\assets\brake-ring.ico"; AppUserModelID: "com.usebrake.Brake"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch Brake"; Flags: nowait postinstall skipifsilent

[Code]
function RunUninstallGuard(): Boolean;
var
  ResultCode: Integer;
  GuardExe: String;
begin
  GuardExe := ExpandConstant('{app}\BrakeUninstallGuard.exe');
  if not FileExists(GuardExe) then
  begin
    MsgBox(
      'Brake cannot uninstall because the uninstall guard is missing. Reinstall Brake, turn protection off, then uninstall again.',
      mbError,
      MB_OK
    );
    Result := False;
    exit;
  end;

  if not Exec(GuardExe, '', '', SW_SHOW, ewWaitUntilTerminated, ResultCode) then
  begin
    MsgBox('Brake could not start the uninstall guard. Reinstall Brake and try again.', mbError, MB_OK);
    Result := False;
    exit;
  end;

  Result := ResultCode = 0;
end;

function RunUninstallCleanup(): Boolean;
var
  ResultCode: Integer;
  CleanupScript: String;
begin
  CleanupScript := ExpandConstant('{app}\installer\unregister_service.ps1');
  if not FileExists(CleanupScript) then
  begin
    MsgBox(
      'Brake cannot uninstall because the cleanup script is missing. Reinstall Brake, turn protection off, then uninstall again.',
      mbError,
      MB_OK
    );
    Result := False;
    exit;
  end;

  if not Exec(
    ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
    '-NoProfile -ExecutionPolicy Bypass -File "' + CleanupScript + '" -NoAppFolderCleanup',
    '',
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  ) then
  begin
    MsgBox('Brake could not start uninstall cleanup. App files were not removed.', mbError, MB_OK);
    Result := False;
    exit;
  end;

  if ResultCode <> 0 then
  begin
    MsgBox(
      'Brake cleanup did not finish cleanly. App files were not removed. Restart Windows, then try uninstall again.',
      mbError,
      MB_OK
    );
    Result := False;
    exit;
  end;

  Result := True;
end;

function InitializeUninstall(): Boolean;
begin
  Result := RunUninstallGuard();
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
  begin
    if not RunUninstallCleanup() then
      Abort;
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
  StopScript: String;
begin
  StopScript := ExpandConstant('{app}\installer\stop_for_update.ps1');
  if FileExists(StopScript) then
  begin
    if not Exec(
      ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
      '-NoProfile -ExecutionPolicy Bypass -File "' + StopScript + '"',
      '',
      SW_HIDE,
      ewWaitUntilTerminated,
      ResultCode
    ) then
    begin
      Result :=
        'Brake Setup could not start the update preparation step. ' +
        'Setup has been stopped before any files were replaced. Restart Windows and try again.';
      exit;
    end;

    if ResultCode <> 0 then
    begin
      Result :=
        'Brake Setup could not safely stop the existing Brake processes. ' +
        'Setup has been stopped before any files were replaced. Restart Windows and try again. ' +
        'Update preparation returned exit code ' + IntToStr(ResultCode) + '.';
      exit;
    end;
  end;
  Result := '';
end;

function ServiceIsRegistered(const ServiceName: String): Boolean;
var
  ResultCode: Integer;
begin
  Result :=
    Exec(
      ExpandConstant('{sys}\sc.exe'),
      'query "' + ServiceName + '"',
      '',
      SW_HIDE,
      ewWaitUntilTerminated,
      ResultCode
    ) and (ResultCode = 0);
end;

procedure VerifyBrakeServices;
var
  MissingServices: String;
begin
  MissingServices := '';
  if not ServiceIsRegistered('BrakeService') then
    MissingServices := 'BrakeService';
  if not ServiceIsRegistered('BrakeWatchdog') then
  begin
    if MissingServices <> '' then
      MissingServices := MissingServices + ' and ';
    MissingServices := MissingServices + 'BrakeWatchdog';
  end;

  if MissingServices <> '' then
    RaiseException(
      'Brake Setup could not verify the required Windows services: ' + MissingServices + '. ' +
      'Installation was not completed. Restart Windows and run setup again.'
    );
end;

procedure RegisterAndVerifyBrakeServices;
var
  RegisterScript: String;
  ResultCode: Integer;
begin
  RegisterScript := ExpandConstant('{app}\installer\register_service.ps1');
  if not FileExists(RegisterScript) then
    RaiseException(
      'Brake Setup could not find the service registration script. ' +
      'Installation was not completed. Download a fresh installer and try again.'
    );

  WizardForm.StatusLabel.Caption := 'Installing Brake services...';
  if not Exec(
    ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
    '-NoProfile -ExecutionPolicy Bypass -File "' + RegisterScript + '" -NoPrompt',
    '',
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  ) then
    RaiseException(
      'Brake Setup could not start service registration. ' +
      'Installation was not completed. Restart Windows and run setup again.'
    );

  if ResultCode <> 0 then
    RaiseException(
      'Brake Setup could not register its required Windows services. ' +
      'Installation was not completed. Restart Windows and run setup again. ' +
      'Service registration returned exit code ' + IntToStr(ResultCode) + '.'
    );

  VerifyBrakeServices;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    RegisterAndVerifyBrakeServices;
end;
