@echo off
setlocal

REM ==== 1. Шлях до робочої папки ====
set "BUILD_ROOT=%~dp0build_root"

REM ==== 2. Створити папку build_root ====
if exist "%BUILD_ROOT%" (
    echo Видаляю стару build_root ...
    rmdir /s /q "%BUILD_ROOT%"
)
mkdir "%BUILD_ROOT%"

REM ==== 3. Завантажити Python Embedded 3.11.9 (x64) ====
echo Завантажую embedded-Python 3.11.9 ...
powershell -Command "Invoke-WebRequest -Uri https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip -OutFile '%BUILD_ROOT%\python-3.11.9-embed-amd64.zip'"

REM ==== 4. Скопіювати твої локальні файли у build_root ====
echo Копіюю файли проекту ...
copy /y requirements-core.txt "%BUILD_ROOT%"
copy /y requirements-heavy.txt "%BUILD_ROOT%"
copy /y main.py "%BUILD_ROOT%"
copy /y version.py "%BUILD_ROOT%"
copy /y updater.py "%BUILD_ROOT%"

xcopy /e /i /y assets "%BUILD_ROOT%\assets"
xcopy /e /i /y ui "%BUILD_ROOT%\ui"
xcopy /e /i /y logic "%BUILD_ROOT%\logic"

REM ==== 5. Додати службові скрипти ====
copy /y setup_logic_v2.py "%BUILD_ROOT%"
copy /y heavy_setup.py "%BUILD_ROOT%"

REM ==== 6. Додати unzip.bat ====
(
echo @echo off
echo REM Args: %%1 = {tmp}, %%2 = {app}
echo set "SRC=%%~1"
echo set "APP=%%~2"
echo set "ZIP=%%SRC%%\python-3.11.9-embed-amd64.zip"
echo set "DEST=%%APP%%\python"
echo if exist "%%DEST%%" rd /s /q "%%DEST%%"
echo mkdir "%%DEST%%" 1^>nul 2^>nul
echo powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -Force '%%ZIP%%' '%%DEST%%'"
echo exit /b %%ERRORLEVEL%%
) > "%BUILD_ROOT%\unzip.bat"

echo ================================
echo Готово! Папка build_root зібрана.
echo ================================
pause
