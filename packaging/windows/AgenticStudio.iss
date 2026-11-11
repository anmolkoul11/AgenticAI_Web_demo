; Build only from the curated PyInstaller application directory.
; Per-user installation: no Windows service, administrator elevation or firewall rule.
#define ReleaseRoot GetEnv("AGENTIC_RELEASE_ROOT")
#define ReleaseVersion GetEnv("AGENTIC_RELEASE_VERSION")
#define FileVersion GetEnv("AGENTIC_RELEASE_FILE_VERSION")
#define StagingRoot GetEnv("AGENTIC_RELEASE_STAGING")
#if ReleaseRoot == "" || ReleaseVersion == "" || StagingRoot == ""
  #error "Use scripts/Build-WindowsRelease.ps1 to supply the release paths and version."
#endif

[Setup]
AppId={{7C6BBA54-7453-4E2E-8C60-17A8357B3349}
AppName=Agentic Studio
AppVersion={#ReleaseVersion}
AppPublisher=Agentic Studio
DefaultDirName={localappdata}\Programs\Agentic Studio
DefaultGroupName=Agentic Studio
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#ReleaseRoot}
OutputBaseFilename=AgenticStudio-Setup-{#ReleaseVersion}-win-x64
SetupIconFile={#StagingRoot}\app.ico
UninstallDisplayIcon={app}\AgenticStudio.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=no
RestartApplications=no
VersionInfoVersion={#FileVersion}

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "{#ReleaseRoot}\AgenticStudio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Agentic Studio"; Filename: "{app}\AgenticStudio.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\Agentic Studio"; Filename: "{app}\AgenticStudio.exe"; WorkingDir: "{app}"; Tasks: desktopicon
Name: "{group}\Getting started"; Filename: "{app}\GettingStarted.txt"
Name: "{group}\Browser Companion files"; Filename: "{app}\BrowserCompanion"

[Run]
Filename: "{app}\AgenticStudio.exe"; Description: "Open Agentic Studio"; Flags: nowait postinstall skipifsilent

; Intentionally no [UninstallDelete] for user data. Saved accounts/results live
; outside {app}, and uninstall/upgrade must preserve them.
