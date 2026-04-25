[Setup]
AppId={{B7620497-D91D-4E4A-A8D4-CC9750C28CA8}
AppName=NailQue
AppVersion=1.0.0
AppPublisher=NailQue
DefaultDirName={autopf}\NailQue
DefaultGroupName=NailQue
OutputDir=dist-installers
OutputBaseFilename=NailQue-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"

[Files]
Source: "dist\NailQue.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\NailQue"; Filename: "{app}\NailQue.exe"
Name: "{autodesktop}\NailQue"; Filename: "{app}\NailQue.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\NailQue.exe"; Description: "Launch NailQue"; Flags: nowait postinstall skipifsilent
