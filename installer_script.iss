; installer_script.iss
; ФІНАЛЬНА ВЕРСІЯ (пакуємо код, довантажуємо бібліотеки)

#define AppName "Voikan Records"
#define AppVersion "1.1.0" 
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
Name: "{app}\assets"
Name: "{app}\ui"
Name: "{app}\logic"

[Files]
; Включаємо АРХІВ З PYTHON та "мозок"
Source: "python-3.11.9-embed-amd64.zip"; DestDir: "{tmp}"
Source: "unzip.bat"; DestDir: "{tmp}"
Source: "setup_logic.py"; DestDir: "{app}"
Source: "requirements-core.txt"; DestDir: "{app}"
Source: "requirements-heavy.txt"; DestDir: "{app}"

; === Включаємо ВЕСЬ твій код в інсталятор ===
Source: "main.py"; DestDir: "{app}"
Source: "updater.py"; DestDir: "{app}"
Source: "version.py"; DestDir: "{app}"
Source: "auth_logic.py"; DestDir: "{app}"
Source: "assets\*"; DestDir: "{app}\assets"; Flags: recursesubdirs createallsubdirs
Source: "ui\*"; DestDir: "{app}\ui"; Flags: recursesubdirs createallsubdirs
Source: "logic\*"; DestDir: "{app}\logic"; Flags: recursesubdirs createallsubdirs
; Додай сюди інші .py файли з кореневої папки, якщо вони є

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"

[Run]
; Розпаковуємо Python
Filename: "{tmp}\unzip.bat"; Parameters: """{tmp}"" ""{app}"""; Flags: runhidden waituntilterminated
; Запускаємо "мозок", щоб він довантажив бібліотеки
Filename: "{app}\python\python.exe"; Parameters: """{app}\setup_logic.py"" ""{app}"""; Flags: runhidden waituntilterminated