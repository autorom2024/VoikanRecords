@echo off
setlocal

REM 1) .gitignore
(
echo token_autofill.json
echo photo_qt_config.json
echo photo_qt_presets.json
echo client_secret.json
echo credentials.json
echo *.pkl
echo *.db
echo *.sqlite
echo secrets/
echo .env
) >> .gitignore

REM 2) прибрати з індексу
git rm --cached token_autofill.json photo_qt_config.json photo_qt_presets.json 2>nul
git rm --cached client_secret.json credentials.json 2>nul
for %%E in (pkl db sqlite) do git ls-files *.^%E -z | git update-index -z --assume-unchanged --stdin 2>nul

git add .gitignore
git commit -m "Stop tracking secrets; move to .env" || echo Nothing to commit

REM 3) створити чисту історію
git checkout --orphan clean-main
git add .
git commit -m "Initial clean commit (no secrets)"
git branch -D main
git branch -m main
git push -u origin main --force

echo [OK] Готово. Тепер перевипусти ключі OpenAI/Google і поклади їх у .env (поза гітом).
pause
