@echo off
cls
color 0A

:: =======================================================
::      BAT-ФАЙЛ ДЛЯ ОНОВЛЕНЬ ТА РЕЛІЗІВ НА GITHUB
::               (Voikan Records - v2)
:: =======================================================

echo.
echo ======================================================
echo           VOIKAN RECORDS - GITHUB UPLOADER
echo ======================================================
echo.

:: Перевірка, чи ми в репозиторії Git
if not exist ".git" (
    echo [ERROR] Papka .git ne znaidena. Vi ne v kornevomu katalozi proektu.
    color 0C
    pause
    exit /b
)

echo [INFO] Perevirka statusu failiv...
git status -s
echo.

:: --- КРОК 1: ЗБЕРЕЖЕННЯ ЗМІН ---
set /p commit_message="Vvedit korotkiy opis zmin (napr. 'Vipraviv bag'): "

if "%commit_message%"=="" (
    set commit_message="Routine update"
)

echo.
echo [INFO] Dodavannya vsih zmin...
git add .
echo [INFO] Zberigannya zmin (commit) z povidomlennyam: "%commit_message%"
git commit -m "%commit_message%"
echo [INFO] Vidpravka zmin na GitHub (push)...
git push origin main

:: Перевірка, чи вдалося відправити зміни
if errorlevel 1 (
    echo.
    echo [ERROR] Ne vdalosya vidpraviti zmini na GitHub! Perevirte z'ednannya abo konflikti.
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

if /i "%create_release%"=="y" (
    echo.
    set /p version_tag="Vvedit nomer novoyi versiyi (napr. 1.0.4): "
    
    if "%version_tag%"=="" (
        echo [ERROR] Nomer versiyi ne mozhe buti porozhnim!
        color 0C
        pause
        exit /b
    )
    
    set full_tag=v%version_tag%
    echo [INFO] Stvoryuyu teg %full_tag%...
    git tag %full_tag%
    
    echo [INFO] Vidpravlyayu teg %full_tag% na GitHub dlya pochatku bildu...
    git push origin %full_tag%
    
    echo.
    echo [OK] ZAPUSK BILDU! Pereidit na vkladku 'Actions' na GitHub, shchob pereviriti.
) else (
    echo.
    echo [INFO] Reliz propuscheno.
)

echo.
echo ======================================================
echo           VSE GOTOVO! ROBOTU ZAVERSHENO.
echo ======================================================
echo.
pause