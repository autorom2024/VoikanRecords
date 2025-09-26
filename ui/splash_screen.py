# ui/splash_screen.py
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QProgressBar
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QIcon, QPainter, QLinearGradient, QColor, QFont, QPixmap

def _splash_icon():
    pixmap = QPixmap(128, 128)
    pixmap.fill(Qt.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.Antialiasing, True)
    grad = QLinearGradient(0, 0, 128, 128)
    grad.setColorAt(0.0, QColor("#8A2BE2"))
    grad.setColorAt(1.0, QColor("#4169E1"))
    p.setPen(Qt.NoPen)
    p.setBrush(grad)
    p.drawEllipse(0, 0, 128, 128)
    font = QFont("Segoe UI", -1, QFont.Bold)
    font.setPixelSize(int(128 * 0.6))
    p.setFont(font)
    p.setPen(QColor("white"))
    p.drawText(QRectF(0, 0, 128, 128), Qt.AlignCenter, "V")
    p.end()
    return QIcon(pixmap)

class SplashScreen(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.SplashScreen)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(350, 400)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        logo_label = QLabel()
        logo_label.setPixmap(_splash_icon().pixmap(128, 128))
        logo_label.setAlignment(Qt.AlignCenter)

        title_label = QLabel("VOIKAN RECORDS")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("color: white; font-size: 24px; font-weight: bold;")
        
        self.status_label = QLabel("Підключення до серверів...")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: #AAAAAA; font-size: 14px;")

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar { border: 1px solid #555; border-radius: 5px; background-color: #333; height: 10px; }
            QProgressBar::chunk { background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #8A2BE2, stop:1 #4169E1); width: 20px; margin: 1px; }
        """)

        layout.addStretch()
        layout.addWidget(logo_label)
        layout.addWidget(title_label)
        layout.addStretch()
        layout.addWidget(self.status_label)
        layout.addWidget(self.progress_bar)

        if self.screen():
            screen_geometry = self.screen().geometry()
            self.move(screen_geometry.center() - self.rect().center())

    def update_status_text(self, text):
        self.status_label.setText(text)