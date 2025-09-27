; installer_script.iss
; ФІНАЛЬНА РОБОЧА ВЕРСІЯ (для релізу)

#define AppName "Voikan Records"
#define AppVersion "1.0.5" 
#define AppPublisher "Voikan"
#define AppExeName "run.bat"

[Setup]
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
OutputBaseFilename=Voikan-Installer-{#AppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "ukrainian"; MessagesFile: "compiler:Languages\Ukrainian.isl"

[Dirs]
Name: "{app}\python"

[Files]
Source: "python-3.11.9-embed-amd64.zip"; DestDir: "{tmp}"
Source: "unzip.bat"; DestDir: "{tmp}"
Source: "setup_logic.py"; DestDir: "{app}"
Source: "requirements-core.txt"; DestDir: "{app}"
Source: "requirements-heavy.txt"; DestDir: "{app}"

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"

[Run]
; КРОК 1: Розпаковуємо наш Python (вікно приховано)
Filename: "{tmp}\unzip.bat"; Parameters: """{tmp}"" ""{app}"""; Flags: runhidden waituntilterminated

; КРОК 2: Запускаємо наш "мозок" (вікно приховано)
Filename: "{app}\python\python.exe"; Parameters: """{app}\setup_logic.py"" ""{app}"""; Flags: runhidden waituntilterminated