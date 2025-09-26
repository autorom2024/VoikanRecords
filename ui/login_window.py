# ui/login_window.py
from PySide6.QtWidgets import QDialog, QVBoxLayout, QPushButton, QLabel, QMessageBox, QApplication
from PySide6.QtCore import Qt
from auth_logic import get_google_auth_credentials, get_user_info

class LoginWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Авторизація Voikan Records")
        self.setFixedSize(400, 220)
        self.user_data = None
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        welcome_label = QLabel("Вітаємо у Voikan Records!")
        welcome_label.setAlignment(Qt.AlignCenter)
        
        info_label = QLabel("Для початку роботи, будь ласка, увійдіть за допомогою вашого Google акаунта.")
        info_label.setWordWrap(True)
        info_label.setAlignment(Qt.AlignCenter)
        
        self.login_button = QPushButton("Увійти через Google")
        self.login_button.clicked.connect(self.handle_login)
        
        layout.addWidget(welcome_label)
        layout.addStretch(1)
        layout.addWidget(info_label)
        layout.addStretch(1)
        layout.addWidget(self.login_button)
        
        welcome_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #E0E0E0;")
        info_label.setStyleSheet("font-size: 13px; color: #B0B0B0;")
        self.login_button.setStyleSheet("""
            QPushButton { padding: 10px; font-size: 14px; background-color: #4285F4; color: white; border: none; border-radius: 5px; }
            QPushButton:hover { background-color: #5395F5; }
            QPushButton:disabled { background-color: #333; }
        """)
        self.setStyleSheet("background-color: #2D2D2D;")
        
    def handle_login(self):
        self.login_button.setText("Очікуємо на браузер...")
        self.login_button.setEnabled(False)
        QApplication.processEvents()
        
        try:
            creds = get_google_auth_credentials()
            self.user_data = get_user_info(creds)
            if self.user_data and self.user_data.get('email'): self.accept()
            else: raise Exception("Не вдалося отримати дані користувача.")
        except Exception as e:
            QMessageBox.critical(self, "Помилка авторизації", f"Не вдалося виконати вхід.\n\nДеталі: {str(e)}")
            self.login_button.setText("Увійти через Google")
            self.login_button.setEnabled(True)