[Setup]
AppId={{C90D3AD0-BFAE-45DC-915D-22A5980A704E}
AppName=Music Catalog Manager
AppVersion=0.1.0
DefaultDirName={localappdata}\Programs\MusicCatalogManager
DefaultGroupName=Music Catalog Manager
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist
OutputBaseFilename=MusicCatalogManager-0.1.0-Setup
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
