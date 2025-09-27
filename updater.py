# updater.py
import sys
import os
import requests
import subprocess
from PySide6.QtWidgets import QMessageBox, QProgressDialog
from PySide6.QtCore import QThread, Signal, Qt

# --- НАЛАШТУВАННЯ ---
# Вкажіть ваш репозиторій на GitHub у форматі "власник/назва_репозиторію"
GITHUB_REPO = "autorom2024/VoikanRecords" 
# Вкажіть назву файлу інсталятора, який ви завантажуєте в релізи
INSTALLER_ASSET_NAME = "VoikanInstaller.exe" 

from version import __version__ as CURRENT_VERSION

class UpdateCheckThread(QThread):
    """Потік для перевірки оновлень у фоні, щоб не блокувати UI."""
    finished = Signal(dict)

    def run(self):
        api_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
        try:
            response = requests.get(api_url, timeout=5)
            response.raise_for_status()
            data = response.json()
            
            latest_version = data['tag_name'].lstrip('v')
            release_notes = data['body']
            assets = data.get('assets', [])
            download_url = None
            for asset in assets:
                if asset['name'] == INSTALLER_ASSET_NAME:
                    download_url = asset['browser_download_url']
                    break
            
            if download_url and latest_version > CURRENT_VERSION:
                self.finished.emit({
                    "update_found": True,
                    "latest_version": latest_version,
                    "release_notes": release_notes,
                    "download_url": download_url
                })
            else:
                self.finished.emit({"update_found": False})
        except Exception as e:
            print(f"Помилка перевірки оновлень: {e}")
            self.finished.emit({"update_found": False, "error": str(e)})

class UpdateDownloadThread(QThread):
    """Потік для завантаження оновлення з відображенням прогресу."""
    progress = Signal(int)
    finished = Signal(str)

    def __init__(self, url, save_path):
        super().__init__()
        self.url = url
        self.save_path = save_path

    def run(self):
        try:
            response = requests.get(self.url, stream=True, timeout=30)
            response.raise_for_status()
            total_size = int(response.headers.get('content-length', 0))
            bytes_downloaded = 0
            
            with open(self.save_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
                    bytes_downloaded += len(chunk)
                    if total_size > 0:
                        progress_percent = int((bytes_downloaded / total_size) * 100)
                        self.progress.emit(progress_percent)
            
            self.finished.emit(self.save_path)
        except Exception as e:
            print(f"Помилка завантаження: {e}")
            self.finished.emit(None)

class Updater:
    def __init__(self, parent_window):
        self.parent = parent_window
        self.check_thread = None
        self.download_thread = None

    def check(self):
        self.check_thread = UpdateCheckThread()
        self.check_thread.finished.connect(self.on_check_finished)
        self.check_thread.start()

    def on_check_finished(self, result):
        if not result.get("update_found"):
            return

        latest_version = result["latest_version"]
        release_notes = result["release_notes"]
        
        msg_box = QMessageBox(self.parent)
        msg_box.setWindowTitle("Доступне оновлення")
        msg_box.setText(f"Доступна нова версія: <b>{latest_version}</b> (ваша версія: {CURRENT_VERSION}).")
        msg_box.setInformativeText("<b>Що нового:</b>\n" + release_notes)
        msg_box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msg_box.setDefaultButton(QMessageBox.StandardButton.Yes)
        
        if msg_box.exec() == QMessageBox.StandardButton.Yes:
            self.download_update(result["download_url"])

    def download_update(self, url):
        temp_dir = os.path.join(os.environ.get("TEMP", "C:\\Temp"), "VoikanUpdater")
        os.makedirs(temp_dir, exist_ok=True)
        save_path = os.path.join(temp_dir, INSTALLER_ASSET_NAME)

        self.progress_dialog = QProgressDialog("Завантаження оновлення...", "Скасувати", 0, 100, self.parent)
        self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress_dialog.setAutoClose(True)
        self.progress_dialog.show()

        self.download_thread = UpdateDownloadThread(url, save_path)
        self.download_thread.progress.connect(self.progress_dialog.setValue)
        self.download_thread.finished.connect(self.on_download_finished)
        self.download_thread.start()

    def on_download_finished(self, installer_path):
        self.progress_dialog.close()
        if not installer_path:
            QMessageBox.critical(self.parent, "Помилка", "Не вдалося завантажити оновлення.")
            return

        QMessageBox.information(self.parent, "Оновлення готове", "Зараз програма закриється, і запуститься інсталятор оновлення.")
        
        # Запускаємо інсталятор і закриваємо поточну програму
        subprocess.Popen([installer_path])
        QApplication.instance().quit()

def check_for_updates(main_window):
    """Головна функція для запуску перевірки оновлень."""
    updater_instance = Updater(main_window)
    main_window.updater = updater_instance # Зберігаємо екземпляр, щоб він не був видалений збирачем сміття
    updater_instance.check()