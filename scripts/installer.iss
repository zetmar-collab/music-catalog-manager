#ifdef AcceptanceTest
#define ProductId "{{7E9FD57B-A67F-4D14-984B-BCFC688237C5}"
#define ProductGroup "Music Catalog Manager Acceptance Test 0.4.0"
#define SetupOutput "..\build"
#define SetupFilename "MusicCatalogManager-Acceptance-Setup"
#else
#define ProductId "{{C90D3AD0-BFAE-45DC-915D-22A5980A704E}"
#define ProductGroup "Music Catalog Manager"
#define SetupOutput "..\dist"
#define SetupFilename "MusicCatalogManager-0.4.0-Setup"
#endif

[Setup]
AppId={#ProductId}
AppName=Music Catalog Manager
AppVersion=0.4.0
DefaultDirName={localappdata}\Programs\MusicCatalogManager
DefaultGroupName={#ProductGroup}
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#SetupOutput}
OutputBaseFilename={#SetupFilename}
SetupIconFile=..\src\music_catalog_manager\resources\icon.ico
UninstallDisplayIcon={app}\MusicCatalogManager.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
LicenseFile=..\LICENSE
DisableProgramGroupPage=yes

[Languages]
Name: "polish"; MessagesFile: "compiler:Languages\Polish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: desktopicon; Description: "{cm:CreateDesktopIcon}"; Flags: unchecked

[Files]
Source: "..\dist\MusicCatalogManager\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Music Catalog Manager"; Filename: "{app}\MusicCatalogManager.exe"
Name: "{autodesktop}\Music Catalog Manager"; Filename: "{app}\MusicCatalogManager.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\MusicCatalogManager.exe"; Description: "{cm:LaunchProgram,Music Catalog Manager}"; Flags: nowait postinstall skipifsilent

; Intentionally no deletion of the user's catalog or audio-backups during uninstall.
