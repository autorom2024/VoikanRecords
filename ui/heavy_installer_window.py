# ui/heavy_installer_window.py

import sys
import subprocess
import os
from PySide6.QtWidgets import (QApplication, QDialog, QVBoxLayout, QLabel, QProgressBar, QTextEdit)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QMovie # Для анімації

# --- Потік для встановлення ---
# Він буде працювати у фоні, щоб не "вішати" інтерфейс.
class InstallThread(QThread):
    progress_update = Signal(str)
    finished = Signal(bool)

    def __init__(self, python_exe_path, requirements_path):
        super().__init__()
        self.python_exe = python_exe_path
        self.requirements_path = requirements_path

    def run(self):
        try:
            # Це та сама команда для встановлення PyTorch, яку ми обговорювали
            # Ми читаємо її з requirements-heavy.txt
            command = [
                self.python_exe,
                "-m", "pip", "install", "--upgrade", "--no-cache-dir",
                "-r", self.requirements_path
            ]
            
            # Запускаємо процес і читаємо його вивід в реальному часі
            self.progress_update.emit(f"Запуск команди: {' '.join(command)}")
            
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, # Об'єднуємо stdout та stderr
                text=True,
                encoding='utf-8',
                errors='replace', # Ігноруємо помилки кодування
                creationflags=subprocess.CREATE_NO_WINDOW # Не показувати чорне вікно консолі
            )

            # Читаємо вивід по рядках
            for line in iter(process.stdout.readline, ''):
                if line:
                    self.progress_update.emit(line.strip())
            
            process.stdout.close()
            return_code = process.wait()

            if return_code == 0:
                self.progress_update.emit("\nВстановлення успішно завершено!")
                self.finished.emit(True) # Сигнал про успіх
            else:
                self.progress_update.emit(f"\nПОМИЛКА: Процес завершився з кодом {return_code}")
                self.finished.emit(False) # Сигнал про невдачу

        except Exception as e:
            self.progress_update.emit(f"\nКритична помилка: {e}")
            self.finished.emit(False)


# --- Вікно-заставка ---
class HeavyInstallerWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        # Налаштування вікна
        self.setWindowTitle("Войкан: Підготовка AI-рушія")
        self.setFixedSize(600, 400)
        self.setWindowFlags(Qt.Window | Qt.CustomizeWindowHint | Qt.WindowTitleHint) # Забороняємо закриття

        # Створюємо елементи інтерфейсу, використовуючи твій стиль
        self.setStyleSheet("""
            QDialog {
                background-color: #161A21;
                color: #E0E7F1;
                font-family: 'Segoe UI', 'Roboto', sans-serif;
            }
            QLabel {
                background-color: transparent;
            }
            QProgressBar { 
                background-color: #1E232B; 
                border: 1px solid #38414F; 
                border-radius: 10px; 
                text-align: center; 
                color: #C7D0DC; 
                min-height: 18px; 
            }
            QProgressBar::chunk { 
                border-radius: 9px; 
                background-color: #3882F6; 
            }
            QTextEdit {
                background-color: #1E232B; 
                border: 1px solid #38414F; 
                border-radius: 8px; 
                color: #A0ACC0;
                font-family: 'Consolas', 'Courier New', monospace;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        self.title_label = QLabel("Підготовка до першого запуску", self)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #E0E7F1;")
        
        self.info_label = QLabel("Зараз будуть завантажені AI-компоненти (PyTorch). Це може зайняти значний час.", self)
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.info_label.setWordWrap(True)
        self.info_label.setStyleSheet("color: #A0ACC0;")


        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 0) # "Невизначений" прогрес-бар

        self.log_output = QTextEdit(self)
        self.log_output.setReadOnly(True)

        layout.addWidget(self.title_label)
        layout.addWidget(self.info_label)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.log_output)
        
        self.install_thread = None

    def start_installation(self):
        """Запускає процес встановлення."""
        # Визначаємо шлях до Python
        # sys.executable - це найнадійніший спосіб отримати шлях до поточного python.exe
        python_exe = sys.executable
        
        # Визначаємо шлях до requirements-heavy.txt
        # Припускаємо, що програма запускається з папки 'app', а файл лежить на рівень вище
        if getattr(sys, 'frozen', False):
             # Якщо програма "заморожена" (скомпільована в .exe)
             app_root = os.path.dirname(sys.executable)
        else:
             # Якщо запускається як звичайний .py скрипт
             app_root = os.path.dirname(os.path.dirname(__file__)) # D:/VOIKAN R/ui -> D:/VOIKAN R

        requirements_file = os.path.join(app_root, "requirements-heavy.txt")
        
        if not os.path.exists(requirements_file):
             self.update_log(f"ПОМИЛКА: Не знайдено файл {requirements_file}")
             self.on_installation_finished(False)
             return

        self.update_log("Запуск процесу встановлення... Будь ласка, зачекайте.")
        
        # Створюємо і запускаємо потік
        self.install_thread = InstallThread(python_exe, requirements_file)
        self.install_thread.progress_update.connect(self.update_log)
        self.install_thread.finished.connect(self.on_installation_finished)
        self.install_thread.start()

    def update_log(self, message):
        self.log_output.append(message)
    
    def on_installation_finished(self, success):
        self.progress_bar.setRange(0, 100)
        
        if success:
            self.progress_bar.setValue(100)
            self.title_label.setText("Встановлення завершено!")
            self.info_label.setText("Перезапустіть програму для продовження.")
            self.accept() # Закриваємо вікно з позитивним результатом
        else:
            self.progress_bar.setStyleSheet("QProgressBar::chunk { background-color: #E81123; }")
            self.progress_bar.setValue(100)
            self.title_label.setText("Помилка встановлення")
            self.info_label.setText("Не вдалося завантажити компоненти. Закрийте це вікно і спробуйте ще раз.")
            # Можна додати кнопку для закриття, але поки що залишимо так
            # self.reject() # В теорії, ми маємо тут викликати reject, але це закриє програму

# --- Цей блок для тестування ---
if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = HeavyInstallerWindow()
    window.show()
    # Для тестування можна викликати встановлення тут
    # window.start_installation() 
    sys.exit(app.exec())