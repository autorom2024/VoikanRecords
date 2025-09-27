@echo off
setlocal enabledelayedexpansion

cls
color 0A

:: =======================================================
::      BAT-ФАЙЛ З АВТОМАТИЧНИМ КЕРУВАННЯМ ВЕРСІЯМИ
::               (Voikan Records - v3)
:: =======================================================

echo.
echo ======================================================
echo           VOIKAN RECORDS - GITHUB UPLOADER
echo ======================================================
echo.

:: --- НАЛАШТУВАННЯ ---
set VERSION_FILE=_version.txt

:: Перевірка, чи ми в репозиторії Git
if not exist ".git" (
    echo [ERROR] Papka .git ne znaidena. Vi ne v kornevomu katalozi proektu.
    color 0C
    pause
    exit /b
)

:: --- КРОК 1: ЗБЕРЕЖЕННЯ ЗМІН ---
echo [INFO] Perevirka statusu failiv...
git status -s
echo.

set /p commit_message="Vvedit korotkiy opis zmin (napr. 'Vipraviv bag'): "
if "%commit_message%"=="" set commit_message="Routine update"

echo.
echo [INFO] Dodavannya, zberigannya ta vidpravka zmin...
git add .
git commit -m "%commit_message%" > nul
git push origin main > nul

if errorlevel 1 (
    echo.
    echo [ERROR] Ne vdalosya vidpraviti zmini na GitHub!
    color 0C
    pause
    exit /b
)
echo [OK] Zmini uspishno vidpravleno na GitHub.
echo.

:: --- КРОК 2: СТВОРЕННЯ РЕЛІЗУ (ЗАПУСК БІЛДУ) ---
echo ======================================================
echo           STVORENNYA NOVOGO RELIZU
echo ======================================================
echo.
set /p create_release="Chy hochete stvoriti noviy reliz i zapustiti bild? (y/n): "

if /i not "%create_release%"=="y" (
    echo.
    echo [INFO] Reliz propuscheno.
    goto :end_script
)

:: --- КРОК 3: АВТОМАТИЧНЕ ВИЗНАЧЕННЯ ВЕРСІЇ ---
set "CURRENT_VERSION="
if exist "%VERSION_FILE%" (
    set /p CURRENT_VERSION=<"%VERSION_FILE%"
)

if not defined CURRENT_VERSION (
    echo.
    echo [WARNING] Fail z versiyeyu ne znaideno.
    set /p CURRENT_VERSION="Vvedit pochatkovu versiyu (napr. 1.0.4): "
) else (
    echo [INFO] Potochna versiya: %CURRENT_VERSION%
)

:: Розбиваємо версію на частини
for /f "tokens=1-3 delims=." %%a in ("%CURRENT_VERSION%") do (
    set major=%%a
    set minor=%%b
    set patch=%%c
)

:: Збільшуємо останню цифру (патч) на 1
set /a new_patch=%patch% + 1
set NEW_VERSION=%major%.%minor%.%new_patch%

echo.
set /p version_tag="Avtomatychno proponuyetsya versiya: %NEW_VERSION%. Natisnit Enter, shchob pidtverditi, abo vvedit svoyu: "

:: Якщо користувач нічого не ввів, використовуємо запропоновану версію
if "%version_tag%"=="" set version_tag=%NEW_VERSION%

:: --- КРОК 4: СТВОРЕННЯ ТА ВІДПРАВКА ТЕГУ ---
set full_tag=v%version_tag%
echo.
echo [INFO] Stvoryuyu teg %full_tag%...
git tag %full_tag%

echo [INFO] Vidpravlyayu teg %full_tag% na GitHub dlya pochatku bildu...
git push origin %full_tag%

if errorlevel 1 (
    echo [ERROR] Ne vdalosya vidpraviti teg. Mozhlivo, vin vzhe isnuue.
    git tag -d %full_tag% > nul
    color 0C
    pause
    exit /b
)

:: Оновлюємо файл з версією, ТІЛЬКИ ЯКЩО все пройшло успішно
echo %version_tag% > "%VERSION_FILE%"
echo [OK] Versiyu u faili %VERSION_FILE% onovleno na %version_tag%.
echo.
echo [OK] ZAPUSK BILDU! Pereidit na vkladku 'Actions' na GitHub.

:end_script
echo.
echo ======================================================
echo           VSE GOTOVO! ROBOTU ZAVERSHENO.
echo ======================================================
echo.
pause