@echo off
cls

:: =======================================================
::      BAT-ФАЙЛ ДЛЯ ВІДПРАВКИ ОНОВЛЕНЬ НА GITHUB
::                    (Voikan Records)
:: =======================================================

echo.
echo ======================================================
echo           VOIKAN RECORDS - GITHUB UPLOADER
echo ======================================================
echo.

:: Перевірка, чи ми в репозиторії Git
if not exist ".git" (
    echo [ERROR] Papka .git ne znaidena. Vi ne v kornevomu katalozi proektu.
    pause
    exit /b
)

echo [INFO] Perevirka statusu failiv...
git status -s
echo.

:: Запитуємо опис змін
set /p commit_message="Vvedit korotkiy opis zmin (napr. 'Vipraviv bag'): "

:: Якщо користувач нічого не ввів, використовуємо стандартне повідомлення
if "%commit_message%"=="" (
    set commit_message="Routine update"
)

echo.
echo [INFO] Dodavannya vsih zmin...
git add .
echo [OK] Faily dodano.
echo.

echo [INFO] Zberigannya zmin (commit) z povidomlennyam: "%commit_message%"
git commit -m "%commit_message%"
echo [OK] Zmini zberezheno.
echo.

echo [INFO] Vidpravka zmin na GitHub (push)...
git push
echo.

echo ======================================================
echo           VSE GOTOVO! Zmini na GitHub.
echo ======================================================
echo.
pause