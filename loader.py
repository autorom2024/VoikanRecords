import sys
import os
import subprocess
import requests
import zipfile
from pathlib import Path
from PySide6.QtWidgets import QApplication, QMessageBox, QProgressDialog
from PySide6.QtCore import Qt

# Це посилання робот на GitHub потім може вшити автоматично
HEAVY_LIBS_URL = "URL_TO_YOUR_HEAVY_LIBS.ZIP" 

def run_main_app():
    # Запускаємо основну програму в новому процесі
    subprocess.Popen([sys.executable, "main.py"])
    sys.exit(0)

def main():
    app = QApplication(sys.argv)
    
    app_dir = Path(sys.executable).parent
    libs_dir = app_dir / "libs"
    
    if libs_dir.exists():
        # Якщо бібліотеки вже є, додаємо їх в шлях і запускаємо програму
        sys.path.insert(0, str(libs_dir))
        run_main_app()

    # Якщо бібліотек немає, показуємо діалог
    reply = QMessageBox.question(None, "Перший запуск", 
                                 "Для роботи потрібно завантажити додаткові компоненти (2-3 ГБ). Завантажити?",
                                 QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
    
    if reply == QMessageBox.No:
        sys.exit(1)
        
    # Тут код для завантаження і розпаковки heavy_libs.zip в папку libs...
    # ... (схожий на той, що я давав для updater.py)
    
    # Після успішного завантаження і розпаковки
    QMessageBox.information(None, "Готово", "Компоненти встановлено. Програма зараз запуститься.")
    run_main_app()

if __name__ == "__main__":
    main()