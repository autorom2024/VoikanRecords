import sys
import os
import json
import requests
import subprocess
import zipfile
import threading
from pathlib import Path
from PySide6.QtWidgets import QMessageBox, QProgressDialog
from PySide6.QtCore import Qt

# --- НАЛАШТУВАННЯ ---
# Поточна версія програми. ЇЇ ТРЕБА МІНЯТИ ВРУЧНУ при кожній новій збірці.
CURRENT_VERSION = "v1.0.0" 

# Твій репозиторій на GitHub
GITHUB_REPO = "autorom2024/VoikanRecords"

def check_for_updates(main_window):
    """Перевіряє оновлення у фоновому потоці і показує діалог."""
    
    def _worker():
        print("Перевірка оновлень...")
        try:
            # Робимо запит до API GitHub, щоб отримати інформацію про останній реліз
            url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            
            latest_meta = response.json()
            latest_version = latest_meta["tag_name"]
            
            print(f"Поточна версія: {CURRENT_VERSION}, остання версія: {latest_version}")

            if latest_version > CURRENT_VERSION:
                notes = latest_meta.get("body", "Нові виправлення та покращення.")
                assets = latest_meta.get("assets", [])
                if not assets:
                    print("Оновлення знайдене, але в релізі немає файлів для завантаження.")
                    return

                # Шукаємо наш .zip архів
                download_asset = None
                for asset in assets:
                    if asset['name'].endswith('.zip'):
                        download_asset = asset
                        break
                
                if not download_asset:
                    print("Не знайдено .zip архів в останньому релізі.")
                    return

                reply = QMessageBox.question(main_window, "Є оновлення!",
                                             f"Доступна нова версія {latest_version}!\n\nЩо нового:\n{notes}\n\nОновитись зараз?",
                                             QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
                
                if reply == QMessageBox.Yes:
                    download_and_install_update(main_window, download_asset)

        except Exception as e:
            print(f"Не вдалося перевірити оновлення: {e}")

    # Запускаємо перевірку у фоновому потоці, щоб не блокувати інтерфейс
    update_thread = threading.Thread(target=_worker, daemon=True)
    update_thread.start()


def download_and_install_update(main_window, asset):
    """Завантажує та встановлює оновлення."""
    try:
        download_url = asset["browser_download_url"]
        filename = asset["name"]
        
        app_path = Path(sys.executable)
        update_path = app_path.parent / filename
        
        # Створюємо діалог прогресу
        progress = QProgressDialog("Завантаження оновлення...", "Скасувати", 0, 100, main_window)
        progress.setWindowModality(Qt.WindowModal)
        progress.setWindowTitle("Оновлення")
        progress.show()

        with requests.get(download_url, stream=True) as r:
            r.raise_for_status()
            total_size = int(r.headers.get('content-length', 0))
            progress.setMaximum(total_size)
            downloaded_size = 0
            with open(update_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if progress.wasCanceled():
                        raise Exception("Завантаження скасовано.")
                    f.write(chunk)
                    downloaded_size += len(chunk)
                    progress.setValue(downloaded_size)

        progress.setValue(total_size)
        
        # Створюємо .bat скрипт для заміни файлів
        updater_script_path = app_path.parent / "apply_update.bat"
        with open(updater_script_path, "w", encoding='cp866') as f: # Використовуємо кодування для кирилиці в .bat
            f.write(f"@echo off\n")
            f.write(f"chcp 65001 > nul\n") # Переключаємо кодову сторінку на UTF-8
            f.write(f"echo Очікування закриття Voikan...\n")
            f.write(f"timeout /t 3 /nobreak > NUL\n")
            f.write(f"echo Розпакування оновлення...\n")
            f.write(f'tar -xf "{filename}"\n') # Використовуємо вбудований в Windows tar для розпаковки
            f.write(f"echo Очищення...\n")
            f.write(f'del "{filename}"\n') # Видаляємо архів
            f.write(f"echo Оновлення завершено! Запуск нової версії...\n")
            f.write(f'start "" "Voikan.exe"\n') # Запускаємо оновлену програму
            f.write(f"del \"%~f0\"\n") # Самознищення .bat скрипта

        subprocess.Popen(f'"{updater_script_path}"', shell=True)
        sys.exit(0) # Закриваємо поточну програму

    except Exception as e:
        QMessageBox.critical(main_window, "Помилка оновлення", f"Не вдалося завантажити або встановити оновлення:\n{e}")