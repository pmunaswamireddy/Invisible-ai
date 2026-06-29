; Inno Setup Installation Script for Invisible AI
; Compile this script using the Inno Setup Compiler (https://jrsoftware.org/isinfo.php)

[Setup]
AppName=Invisible AI Control Hub
AppVersion=1.0.0
DefaultDirName={userappdata}\InvisibleAI\Program
DefaultGroupName=Invisible AI
OutputDir=dist
OutputBaseFilename=InvisibleAI_Setup
Compression=lzma
SolidCompression=yes
PrivilegesRequired=lowest
SetupIconFile=app_icon.ico

[Files]
Source: "dist\Manager.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\SystemAudioEngine.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: ".env"; DestDir: "{userappdata}\InvisibleAI"; Flags: ignoreversion; Permissions: users-modify

[Icons]
Name: "{group}\Invisible AI Manager"; Filename: "{app}\Manager.exe"
Name: "{userdesktop}\Invisible AI Manager"; Filename: "{app}\Manager.exe"; IconFilename: "{app}\Manager.exe"

[Run]
Filename: "{app}\Manager.exe"; Description: "Launch Invisible AI Manager"; Flags: nowait postinstall skipifsilent
