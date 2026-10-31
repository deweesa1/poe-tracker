; PoE Tracker installer (Inno Setup 6). Built by installer/build.ps1, which first
; puts everything to install in ..\build:
;   build\PoE Tracker.exe      the launcher
;   build\python\              a private copy of Python with the tracker's packages
;   build\app\poetracker\      the tracker itself (updated in place by the app)
; Installs per user (no admin prompt) so the app can update its own files.
; Your data stays in %LOCALAPPDATA%\PoETracker and is never touched.

#define AppName "PoE Tracker"
#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif
#define AppExe "PoE Tracker.exe"
#define AppUserModelID "deweesa1.PoETracker"

[Setup]
AppId={{42A7F66B-2B6C-581F-B374-8BF9ECAC810C}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=deweesa1
AppPublisherURL=https://github.com/deweesa1/poe-tracker
AppSupportURL=https://github.com/deweesa1/poe-tracker/issues
AppUpdatesURL=https://github.com/deweesa1/poe-tracker/releases
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=PoE-Tracker-Setup
SetupIconFile=..\poetracker\ui\static\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
; close a running tracker so its files can be replaced
CloseApplications=yes
RestartApplications=no

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "..\build\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"; AppUserModelID: "{#AppUserModelID}"; Comment: "Path of Exile play tracker"
Name: "{autoprograms}\{#AppName} (with log window)"; Filename: "{app}\{#AppExe}"; Parameters: "--console"; Comment: "PoE Tracker with a window showing its messages"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon; AppUserModelID: "{#AppUserModelID}"

[InstallDelete]
; the developer-mode shortcut that version 0.1.0 added
Type: files; Name: "{autoprograms}\{#AppName} (dev).lnk"

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch PoE Tracker"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; files the app writes itself (updates, Python's caches); your data is elsewhere
Type: filesandordirs; Name: "{app}\app"
Type: filesandordirs; Name: "{app}\python"
