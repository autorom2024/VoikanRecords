# main.py
import os
import sys
from datetime import datetime, timedelta
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import QThread, Signal

# === ІНТЕГРАЦІЯ ОНОВЛЕННЯ: Крок 1 ===
import updater # Імпортуємо наш новий модуль для оновлень

from auth_logic import (
    check_user_license, get_machine_id, load_local_license,
    get_google_auth_credentials, get_user_info
)
from ui.login_window import LoginWindow
from ui.main_window import MainWindow
from ui.splash_screen import SplashScreen
from ui.theme_loader import load_stylesheet

os.environ.setdefault("QT_OPENGL", "software")
os.environ.setdefault("QT_QUICK_BACKEND", "software")
os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "0")

main_window = None
app = None
splash = None

class LicenseCheckThread(QThread):
    finished = Signal(dict)

    def __init__(self, machine_id):
        super().__init__()
        self.machine_id = machine_id

    def run(self):
        license_info = {}
        try:
            credentials = get_google_auth_credentials()
            user_data = get_user_info(credentials)
            if not user_data or not user_data.get('email'):
                license_info = {'show_login_window': True}
            else:
                license_info = check_user_license(user_data, self.machine_id)
        except Exception as e:
            print(f"Помилка у потоці перевірки ліцензії: {e}")
            license_info = {'access_granted': False, 'message': f"Помилка підключення: {e}"}
        
        self.finished.emit(license_info)

def on_license_check_complete(license_info):
    global main_window, app, splash
    
    if splash:
        splash.close()

    if license_info.get('show_login_window'):
        login_dialog = LoginWindow()
        if login_dialog.exec():
            user_data = login_dialog.user_data
            machine_id = get_machine_id()
            license_info = check_user_license(user_data, machine_id)
        else:
            if app: app.quit()
            return

    if license_info and license_info.get('access_granted'):
        main_window = MainWindow(app, license_info)
        main_window.show()

        # === ІНТЕГРАЦІЯ ОНОВЛЕННЯ: Крок 2 (після онлайн-перевірки) ===
        # Запускаємо перевірку оновлень, коли програма вже завантажилась
        updater.check_for_updates(main_window)

    else:
        error_message = license_info.get('message', 'Доступ заборонено або ліцензія неактивна.')
        QMessageBox.critical(None, "Доступ заборонено", error_message)
        if app: app.quit()

def run_app():
    global main_window, app, splash
    
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)

    try:
        app.setStyleSheet(load_stylesheet("dark_modern.qss"))
    except Exception as e:
        print(f"Не вдалося завантажити стилі: {e}")

    machine_id = get_machine_id()
    local_license = load_local_license()
    
    is_valid_local = False
    if local_license:
        stored_hwid = local_license.get('hwid')
        last_check_str = local_license.get('last_check')
        last_check_time = datetime.fromisoformat(last_check_str) if last_check_str else None

        if stored_hwid == machine_id and last_check_time and (datetime.now() - last_check_time) < timedelta(days=1):
            if local_license.get('access_granted'):
                is_valid_local = True
        
    if is_valid_local:
        print("Використовується збережена локальна ліцензія. Запуск моментальний.")
        main_window = MainWindow(app, local_license)
        main_window.show()

        # === ІНТЕГРАЦІЯ ОНОВЛЕННЯ: Крок 2 (після локальної перевірки) ===
        # Запускаємо перевірку оновлень, коли програма вже завантажилась
        updater.check_for_updates(main_window)

    else:
        print("Потрібна онлайн-верифікація.")
        splash = SplashScreen()
        splash.show()
        
        thread = LicenseCheckThread(machine_id)
        thread.finished.connect(on_license_check_complete)
        thread.start()
        app.thread = thread

    sys.exit(app.exec())

if __name__ == "__main__":
    run_app()
# це тестова зміси