# -*- coding: utf-8 -*-
from __future__ import annotations
"""
VideoPage — оптимізована версія з правильною пропорційністю
"""

import os
import json
import queue
import shutil
import hashlib
import threading
from typing import Dict, Tuple, Optional

from PySide6.QtCore import Qt, QTimer, Signal, Slot, QRectF, QPoint, QSize
from PySide6.QtGui import (
    QPixmap, QColor, QPainter, QFont, QPolygon, QPainterPath,
    QRadialGradient, QLinearGradient, QPen, QFontDatabase
)
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QLineEdit, QFileDialog, QComboBox,
    QCheckBox, QSpinBox, QDoubleSpinBox, QSlider,
    QHBoxLayout, QVBoxLayout, QGridLayout, QGroupBox, QFormLayout,
    QProgressBar, QMessageBox, QInputDialog,
    QFrame, QSplitter, QPlainTextEdit, QSizePolicy, QScrollArea
)

# ==== Імпорт бекенду ====
try:
    from video_backend import start_video_jobs, stop_all_jobs, reset_processing_state
    from effects_render import (
        make_eq_overlay, make_stars_overlay, make_rain_overlay, make_smoke_overlay,
        draw_motion_indicator,
    )
except ImportError:
    # Резервний імпорт
    try:
        from logic.video_backend import start_video_jobs, stop_all_jobs, reset_processing_state
        from logic.effects_render import (
            make_eq_overlay, make_stars_overlay, make_rain_overlay, make_smoke_overlay,
            draw_motion_indicator,
        )
    except ImportError:
        # Заглушки для тестування
        def start_video_jobs(cfg, queue, event): pass
        def stop_all_jobs(): pass
        def reset_processing_state(): pass
        def make_eq_overlay(eq, w, h): return QPixmap(w, h)
        def make_stars_overlay(st, w, h): return QPixmap(w, h)
        def make_rain_overlay(rn, w, h): return QPixmap(w, h)
        def make_smoke_overlay(sm, w, h): return QPixmap(w, h)
        def draw_motion_indicator(p, rect, mv): pass

CACHE_DIR = os.path.join("_cache", "video_ui")
STAGE_DIR = os.path.join(CACHE_DIR, "playlist_stage")
os.makedirs(CACHE_DIR, exist_ok=True)

CONFIG_FILE = os.path.join(CACHE_DIR, "video_qt_config.json")
USER_PRESETS_FILE = os.path.join(CACHE_DIR, "video_user_presets.json")

# ------------------------ ТЕМНО-СИНЯ ТЕМА ------------------------
THEME_CSS = """
QWidget { 
    background: #0A0A2A; 
    color: #E0E0FF; 
    font-size: 12px; 
    font-family: "Segoe UI", "Arial", sans-serif;
}

QGroupBox {
    border: 2px solid #1E1E5A; 
    border-radius: 12px; 
    margin-top: 8px;
    padding: 8px; 
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #151540,
        stop:1 #0F0F30
    );
}

QGroupBox::title { 
    subcontrol-origin: margin;
    left: 12px; 
    padding: 0 6px; 
    color: #8CB5FF; 
    font-weight: bold;
    font-size: 13px;
}

QPushButton {
    color: #FFFFFF;
    padding: 6px 12px;
    border-radius: 16px;
    border: 1px solid rgba(100, 150, 255, 0.4);
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 rgba(70, 130, 255, 0.25),
        stop:0.45 rgba(50, 100, 220, 0.15),
        stop:0.46 rgba(40, 90, 200, 0.10),
        stop:1 rgba(20, 50, 120, 0.25)
    );
    font-weight: bold;
    min-height: 28px;
    font-size: 11px;
}

QPushButton:hover {
    border: 1px solid rgba(120, 180, 255, 0.6);
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 rgba(90, 150, 255, 0.35),
        stop:0.45 rgba(70, 130, 240, 0.20),
        stop:0.46 rgba(60, 120, 220, 0.15),
        stop:1 rgba(30, 70, 150, 0.30)
    );
}

QPushButton:pressed {
    border: 1px solid rgba(80, 140, 255, 0.5);
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 rgba(50, 110, 220, 0.20),
        stop:0.50 rgba(30, 70, 150, 0.35),
        stop:1 rgba(20, 50, 120, 0.40)
    );
}

QPushButton:disabled {
    color: #8888AA;
    border: 1px solid rgba(100, 150, 255, 0.2);
    background: rgba(70, 130, 255, 0.08);
}

QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background: rgba(25, 25, 60, 0.9);
    border: 1px solid #2D2D7A; 
    border-radius: 8px; 
    padding: 4px 8px;
    selection-background-color: #3D75FF;
    color: #E0E0FF;
    min-height: 26px;
    font-size: 11px;
}

QComboBox::drop-down {
    border: none;
    width: 20px;
    background: transparent;
}

QComboBox QAbstractItemView { 
    background: #1A1A4A; 
    border: 1px solid #2D2D7A;
    border-radius: 6px;
    selection-background-color: #3D75FF;
    color: #E0E0FF;
    font-size: 11px;
}

QCheckBox {
    spacing: 6px;
    color: #C0C0FF;
    font-size: 11px;
}

QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #3D75FF;
    border-radius: 3px;
    background: #151540;
}

QCheckBox::indicator:checked {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 #6CA0FF,
        stop:1 #3D75FF
    );
}

QCheckBox::indicator:checked:hover {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 #8CB5FF,
        stop:1 #5D8AFF
    );
}

QSlider::groove:horizontal { 
    height: 6px; 
    background: #1D1D5A; 
    border-radius: 4px; 
    margin: 3px 0;
}

QSlider::handle:horizontal {
    width: 16px; 
    height: 16px; 
    margin: -5px 0; 
    border-radius: 8px;
    background: qradialgradient(cx:0.3, cy:0.3, radius:0.8,
        fx:0.3, fy:0.3, stop:0 #A0C6FF, stop:0.6 #6CA0FF, stop:1 #3D75FF);
    border: 1px solid #3D75FF;
}

QProgressBar { 
    background: rgba(20, 20, 50, 0.9); 
    border: 1px solid #2D2D7A; 
    border-radius: 8px; 
    text-align: center; 
    padding: 2px; 
    color: #E0E0FF;
    font-size: 11px;
    height: 20px;
}

QProgressBar::chunk {
    border-radius: 6px;
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #8CB5FF, stop:1 #3D75FF);
}

QPlainTextEdit {
    background: #0F0F25;
    border: 1px solid #1E1E5A;
    border-radius: 8px;
    padding: 6px;
    color: #C0C0FF;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 10px;
    selection-background-color: #3D75FF;
}

QLabel {
    color: #D0D0FF;
    background: transparent;
    font-size: 11px;
}

QScrollBar:vertical {
    background: #151540;
    width: 12px;
    border-radius: 6px;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #3D75FF, stop:1 #2D5DCC);
    border-radius: 6px;
    min-height: 20px;
}

QScrollBar::handle:vertical:hover {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #5D95FF, stop:1 #4D7DE0);
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    border: none;
    background: none;
}
"""

# ------------------------ ДОПОМІЖНІ ФУНКЦІЇ ------------------------
def _ensure_dir(path: str) -> str:
    return path if path and os.path.isdir(path) else ""

def _pct(slider: QSlider) -> int:
    return max(0, min(100, int(slider.value())))

def _hex(qc: QColor) -> str:
    return qc.name().upper()

def _mk_slider(a: int, b: int, v: int) -> QSlider:
    s = QSlider(Qt.Horizontal)
    s.setMinimum(a)
    s.setMaximum(b)
    s.setValue(v)
    s.setTickInterval(max(1, (b - a) // 10))
    s.setSingleStep(max(1, (b - a) // 50))
    return s

def _mmss_to_seconds(text: str) -> int:
    try:
        t = text.strip()
        parts = [int(x) for x in t.split(":")]
        if len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
        if len(parts) == 2:
            return parts[0] * 60 + parts[1]
        return int(t)
    except Exception:
        return 180

def _seconds_to_mmss(sec: int) -> str:
    sec = max(0, int(sec))
    return f"{sec // 60:02d}:{sec % 60:02d}"

def _md5sig(d: dict) -> str:
    try:
        return hashlib.md5(json.dumps(d, sort_keys=True).encode("utf-8")).hexdigest()[:8]
    except Exception:
        return "????????"

# ------------------------ КЛАС КНОПКИ КОЛЬОРУ ------------------------
class ColorButton(QPushButton):
    changed = Signal(QColor)
    
    def __init__(self, hex_color: str = "#FFFFFF", parent=None):
        super().__init__(parent)
        self._color = QColor(hex_color)
        self.setFixedSize(60, 26)
        self._apply_style()
        self.clicked.connect(self._pick_color)
    
    def _apply_style(self):
        color_name = self._color.name().upper()
        text_color = "#000000" if self._color.lightness() > 120 else "#FFFFFF"
        
        self.setText(color_name)
        self.setStyleSheet(f"""
            QPushButton {{
                background: {self._color.name()};
                color: {text_color};
                border: 1px solid #555577;
                border-radius: 6px;
                font-weight: bold;
                font-size: 9px;
                padding: 2px;
            }}
            QPushButton:hover {{
                border: 1px solid #777799;
            }}
        """)
    
    def _pick_color(self):
        from PySide6.QtWidgets import QColorDialog
        new_color = QColorDialog.getColor(self._color, self, "Вибір кольору")
        if new_color.isValid():
            self._color = new_color
            self._apply_style()
            self.changed.emit(self._color)
    
    def color(self) -> QColor:
        return self._color
    
    def setColor(self, color: QColor):
        if color and color.isValid():
            self._color = color
            self._apply_style()
            self.changed.emit(self._color)

# ------------------------ КЛАС ВИБОРУ ШЛЯХУ ------------------------
class PathPicker(QWidget):
    changed = Signal(str)
    
    def __init__(self, placeholder: str = "", default: str = "", is_dir=True, parent=None):
        super().__init__(parent)
        self.is_dir = is_dir
        
        # Створення елементів
        self.editor = QLineEdit(default)
        self.editor.setPlaceholderText(placeholder)
        self.editor.setStyleSheet("""
            QLineEdit {
                background: rgba(30, 30, 70, 0.9);
                border: 1px solid #2D2D7A;
                border-radius: 6px;
                padding: 4px 8px;
                color: #E0E0FF;
                font-size: 10px;
                min-height: 24px;
            }
        """)
        
        self.button = QPushButton("…")
        self.button.setFixedSize(26, 26)
        self.button.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 #3D75FF, stop:1 #2D5DCC);
                border: 1px solid #4D85FF;
                border-radius: 6px;
                font-weight: bold;
                color: white;
                font-size: 12px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 #5D95FF, stop:1 #4D7DE0);
                border: 1px solid #6DA5FF;
            }
        """)
        
        # Макет
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self.editor, 1)
        layout.addWidget(self.button, 0)
        
        # Підключення сигналів
        self.button.clicked.connect(self._pick_path)
        self.editor.textChanged.connect(self._on_text_changed)
    
    def _pick_path(self):
        current_path = self.text()
        if self.is_dir:
            new_path = QFileDialog.getExistingDirectory(
                self, "Вибір папки", current_path or "D:/"
            )
        else:
            new_path, _ = QFileDialog.getOpenFileName(
                self, "Вибір файлу", current_path or "D:/"
            )
        
        if new_path:
            self.editor.setText(new_path)
            self.changed.emit(new_path)
    
    def _on_text_changed(self):
        self.changed.emit(self.text())
    
    def text(self) -> str:
        return self.editor.text().strip()
    
    def setText(self, text: str):
        self.editor.setText(text or "")

# ------------------------ КАРТКИ ФОРМАТІВ ------------------------
BRAND_GRADIENTS = {
    "youtube": (QColor(70, 130, 255), QColor(30, 70, 180)),
    "shorts": (QColor(80, 140, 255), QColor(40, 80, 190)),
    "ig": (QColor(90, 100, 255), QColor(50, 60, 200)),
    "tiktok": (QColor(100, 160, 255), QColor(60, 100, 220)),
    "facebook": (QColor(60, 120, 240), QColor(30, 60, 180)),
}

class FormatCard(QFrame):
    clicked = Signal(str)
    
    def __init__(self, key: str, title: str, subtitle: str, brand: str, parent=None):
        super().__init__(parent)
        self.key = key
        self.brand = brand
        self.title_text = title
        self.subtitle_text = subtitle
        self._checked = False
        
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(50)
        self._logo_size = 36
        
    def sizeHint(self) -> QSize:
        return QSize(200, 50)
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        
        rect = self.rect().adjusted(1, 1, -1, -1)
        radius = 12
        
        # Фоновий градієнт
        color1, color2 = BRAND_GRADIENTS.get(self.brand, (QColor(80, 120, 220), QColor(40, 80, 160)))
        gradient = QLinearGradient(rect.topLeft(), rect.topRight())
        gradient.setColorAt(0.0, color1)
        gradient.setColorAt(1.0, color2)
        
        painter.setBrush(gradient)
        painter.setPen(QColor(255, 255, 255, 80))
        painter.drawRoundedRect(rect, radius, radius)
        
        # Скляний ефект
        gloss = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        gloss.setColorAt(0.0, QColor(255, 255, 255, 120))
        gloss.setColorAt(0.4, QColor(255, 255, 255, 40))
        gloss.setColorAt(0.41, QColor(255, 255, 255, 20))
        gloss.setColorAt(1.0, QColor(0, 0, 0, 60))
        
        painter.setBrush(gloss)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(rect, radius, radius)
        
        # Логотип
        logo_x = rect.left() + 8
        logo_y = rect.center().y() - self._logo_size // 2
        
        # Малювання логотипу
        logo_pixmap = QPixmap(self._logo_size, self._logo_size)
        logo_pixmap.fill(Qt.transparent)
        
        logo_painter = QPainter(logo_pixmap)
        logo_painter.setRenderHint(QPainter.Antialiasing, True)
        
        # Скляний круг
        radial_grad = QRadialGradient(
            self._logo_size * 0.35, self._logo_size * 0.30, self._logo_size * 0.75
        )
        radial_grad.setColorAt(0.0, QColor(255, 255, 255, 80))
        radial_grad.setColorAt(0.6, QColor(255, 255, 255, 40))
        radial_grad.setColorAt(1.0, QColor(0, 0, 0, 80))
        
        logo_painter.setBrush(radial_grad)
        logo_painter.setPen(QColor(255, 255, 255, 120))
        logo_painter.drawEllipse(0, 0, self._logo_size, self._logo_size)
        
        # Малювання іконки в залежності від бренду
        logo_painter.setBrush(Qt.white)
        logo_painter.setPen(Qt.NoPen)
        
        if "youtube" in self.key:
            # Трикутник для YouTube
            triangle = QPolygon([
                QPoint(int(self._logo_size * 0.42), int(self._logo_size * 0.34)),
                QPoint(int(self._logo_size * 0.42), int(self._logo_size * 0.66)),
                QPoint(int(self._logo_size * 0.72), int(self._logo_size * 0.50))
            ])
            logo_painter.drawPolygon(triangle)
        elif "shorts" in self.key:
            # Прямокутник для Shorts
            rect_logo = QRectF(
                self._logo_size * 0.28, self._logo_size * 0.24,
                self._logo_size * 0.44, self._logo_size * 0.52
            )
            logo_painter.drawRoundedRect(rect_logo, self._logo_size * 0.18, self._logo_size * 0.18)
        elif "ig" in self.key:
            # Квадрат для Instagram
            rect_logo = QRectF(
                self._logo_size * 0.24, self._logo_size * 0.24,
                self._logo_size * 0.52, self._logo_size * 0.52
            )
            logo_painter.drawRoundedRect(rect_logo, self._logo_size * 0.18, self._logo_size * 0.18)
        elif "tiktok" in self.key:
            # Буква T для TikTok
            logo_painter.drawRect(
                int(self._logo_size * 0.46), int(self._logo_size * 0.26),
                int(self._logo_size * 0.10), int(self._logo_size * 0.40)
            )
        elif "facebook" in self.key or "fb" in self.key:
            # Буква F для Facebook
            logo_painter.drawRect(
                int(self._logo_size * 0.46), int(self._logo_size * 0.24),
                int(self._logo_size * 0.10), int(self._logo_size * 0.52)
            )
            logo_painter.drawRect(
                int(self._logo_size * 0.38), int(self._logo_size * 0.36),
                int(self._logo_size * 0.26), int(self._logo_size * 0.10)
            )
        
        logo_painter.end()
        painter.drawPixmap(logo_x, logo_y, logo_pixmap)
        
        # Текст
        text_x = logo_x + self._logo_size + 8
        
        painter.setPen(Qt.white)
        font = painter.font()
        font.setPointSize(10)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(text_x, logo_y + 16, self.title_text)
        
        font.setPointSize(8)
        font.setBold(False)
        painter.setFont(font)
        painter.drawText(text_x, logo_y + 32, self.subtitle_text)
        
        # Рамка вибору
        if self._checked:
            selection_pen = QPen(QColor(255, 255, 255, 220), 2)
            painter.setPen(selection_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), radius - 1, radius - 1)
        
        painter.end()
    
    def setChecked(self, checked: bool):
        self._checked = bool(checked)
        self.update()
    
    def apply_scale(self, scale: float):
        new_height = max(45, int(50 * scale))
        new_logo_size = max(32, int(36 * scale))
        
        self.setFixedHeight(new_height)
        self._logo_size = new_logo_size
        self.update()
    
    def mousePressEvent(self, event):
        self.clicked.emit(self.key)
        super().mousePressEvent(event)

# ------------------------ ВЕРТИКАЛЬНИЙ ВИБІР ФОРМАТУ ------------------------
class FormatSelectorVertical(QWidget):
    selected = Signal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        
        # Заголовок
        title = QLabel("Формат відео")
        title_font = QFont()
        title_font.setPointSize(12)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet("color: #B0C5FF; margin-bottom: 6px;")
        layout.addWidget(title)
        
        # Картки форматів
        self.cards: Dict[str, FormatCard] = {}
        
        # Додавання карток
        formats = [
            ("youtube_16_9", "YouTube", "16:9 · 1920×1080", "youtube"),
            ("shorts_9_16", "Shorts", "9:16 · 1080×1920", "shorts"),
            ("ig_reels_9_16", "Instagram Reels", "9:16 · 1080×1920", "ig"),
            ("ig_4_5", "Instagram 4:5", "4:5 · 1080×1350", "ig"),
            ("ig_1_1", "Instagram 1:1", "1:1 · 1080×1080", "ig"),
            ("tiktok_9_16", "TikTok", "9:16 · 1080×1920", "tiktok"),
            ("fb_4_5", "Facebook 4:5", "4:5 · 1080×1350", "facebook"),
            ("fb_1_1", "Facebook 1:1", "1:1 · 1080×1080", "facebook"),
        ]
        
        for key, title, subtitle, brand in formats:
            card = FormatCard(key, title, subtitle, brand, self)
            card.clicked.connect(self._on_card_clicked)
            self.cards[key] = card
            layout.addWidget(card)
        
        layout.addStretch(1)
        
        # Вибір за замовчуванням
        self._on_card_clicked("youtube_16_9")
    
    def _on_card_clicked(self, key: str):
        for card_key, card in self.cards.items():
            card.setChecked(card_key == key)
        self.selected.emit(key)
    
    def apply_scale(self, scale: float):
        for card in self.cards.values():
            card.apply_scale(scale)

# ------------------------ ОСНОВНА СТОРІНКА ------------------------
class VideoPage(QWidget):
    sig_biglog = Signal(str)
    sig_progress = Signal(int, str)
    sig_running = Signal(bool)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(THEME_CSS)
        
        # Стан програми
        self._running = False
        self._songs_total = 0
        self._songs_done = 0
        self.host = None
        
        # Черга статусу та таймери
        self.status_queue = queue.Queue()
        self.cancel_event = threading.Event()
        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(60)
        self.poll_timer.timeout.connect(self._poll_status)
        
        self.live_preview_timer = QTimer(self)
        self.live_preview_timer.setInterval(120)
        self.live_preview_timer.setSingleShot(True)
        self.live_preview_timer.timeout.connect(lambda: self._update_preview(False))
        
        # Ініціалізація UI
        self._setup_ui()
        self._setup_connections()
        
        # Завантаження налаштувань
        self._load_config()
        self._load_presets()
        self._sync_format_resolution()
        self._update_preview(True)
    
    def _setup_ui(self):
        """Налаштування оптимізованого інтерфейсу"""
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(10)
        
        # Основний розділювач
        self.main_splitter = QSplitter(Qt.Horizontal)
        self.main_splitter.setChildrenCollapsible(False)
        main_layout.addWidget(self.main_splitter)
        
        # Ліва панель (зменшена ширина)
        self.left_panel = QWidget()
        self.left_splitter = QSplitter(Qt.Vertical)
        left_layout = QVBoxLayout(self.left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(self.left_splitter)
        self.main_splitter.addWidget(self.left_panel)
        
        # Права панель (збільшена ширина)
        self.right_panel = QWidget()
        self.right_splitter = QSplitter(Qt.Vertical)
        right_layout = QVBoxLayout(self.right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(self.right_splitter)
        self.main_splitter.addWidget(self.right_panel)
        
        # Налаштування лівої панелі
        self._setup_left_panel()
        
        # Налаштування правої панелі
        self._setup_right_panel()
        
        # Налаштування пропорцій
        self._setup_proportions()
    
    def _setup_left_panel(self):
        """Налаштування лівої панелі з налаштуваннями"""
        # Папки (перенесено з правої панелі)
        self._setup_folders_section()
        
        # Пресети
        self._setup_presets_section()
        
        # Еквалайзер (стиснутий)
        self._setup_equalizer_section()
        
        # Ефекти (стиснуті)
        self._setup_effects_section()
        
        # Рух камери
        self._setup_motion_section()
    
    def _setup_folders_section(self):
        """Секція папок (перенесена в ліву колонку)"""
        folders_widget = QWidget()
        folders_layout = QHBoxLayout(folders_widget)
        folders_layout.setContentsMargins(6, 6, 6, 6)
        
        folders_group = QGroupBox("📁 Папки")
        folders_form = QFormLayout(folders_group)
        folders_form.setRowWrapPolicy(QFormLayout.DontWrapRows)
        folders_form.setLabelAlignment(Qt.AlignRight)
        folders_form.setFormAlignment(Qt.AlignHCenter | Qt.AlignTop)
        folders_form.setHorizontalSpacing(10)
        folders_form.setVerticalSpacing(8)
        
        self.music_path = PathPicker("Папка з музикою...", "D:/music", True)
        self.media_path = PathPicker("Папка з медіа...", "D:/media", True)
        self.output_path = PathPicker("Вихідна папка...", "D:/output", True)
        
        folders_form.addRow("🎵 Музика:", self.music_path)
        folders_form.addRow("🖼️ Медіа:", self.media_path)
        folders_form.addRow("📤 Вихід:", self.output_path)
        
        folders_layout.addWidget(folders_group)
        self.left_splitter.addWidget(folders_widget)
    
    def _setup_presets_section(self):
        """Секція пресетів"""
        presets_widget = QWidget()
        presets_layout = QHBoxLayout(presets_widget)
        presets_layout.setContentsMargins(6, 6, 6, 6)
        presets_layout.setSpacing(6)
        
        presets_group = QGroupBox("Пресети налаштувань")
        inner_layout = QHBoxLayout(presets_group)
        inner_layout.setSpacing(6)
        
        inner_layout.addWidget(QLabel("Пресет:"))
        
        self.presets_combo = QComboBox()
        self.presets_combo.setMinimumWidth(120)
        inner_layout.addWidget(self.presets_combo, 1)
        
        self.btn_save_preset = QPushButton("💾 Зберегти")
        self.btn_delete_preset = QPushButton("🗑️ Видалити")
        
        inner_layout.addWidget(self.btn_save_preset)
        inner_layout.addWidget(self.btn_delete_preset)
        
        presets_layout.addWidget(presets_group)
        self.left_splitter.addWidget(presets_widget)
    
    def _setup_equalizer_section(self):
        """Секція еквалайзера (стиснута)"""
        eq_widget = QWidget()
        eq_layout = QVBoxLayout(eq_widget)
        eq_layout.setContentsMargins(0, 0, 0, 0)
        
        eq_group = QGroupBox("🎛️ Еквалайзер")
        eq_grid = QGridLayout(eq_group)
        eq_grid.setVerticalSpacing(4)
        eq_grid.setHorizontalSpacing(6)
        
        # Елементи еквалайзера
        self.eq_enabled = QCheckBox("Увімк. еквалайзер")
        self.eq_engine = QComboBox()
        self.eq_engine.addItems(["Хвилі", "Частоти"])
        self.eq_mode = QComboBox()
        self.eq_mode.addItems(["Стовпці", "Лінії", "Крапки"])
        
        self.eq_bars = QSpinBox()
        self.eq_bars.setRange(8, 256)
        self.eq_bars.setValue(96)
        self.eq_bars.setMaximumWidth(60)
        
        self.eq_thick = QSpinBox()
        self.eq_thick.setRange(1, 12)
        self.eq_thick.setValue(3)
        self.eq_thick.setMaximumWidth(50)
        
        self.eq_height = QSpinBox()
        self.eq_height.setRange(40, 1000)
        self.eq_height.setValue(360)
        self.eq_height.setMaximumWidth(70)
        
        self.eq_fullscr = QCheckBox("Повноекранний")
        self.eq_yoffset = QSpinBox()
        self.eq_yoffset.setRange(-100, 100)
        self.eq_yoffset.setValue(0)
        self.eq_yoffset.setMaximumWidth(60)
        
        self.eq_mirror = QCheckBox("Дзеркало")
        self.eq_mirror.setChecked(True)
        
        self.eq_baseline = QCheckBox("Базова лінія")
        self.eq_color = ColorButton("#4D85FF")
        
        self.eq_opacity = _mk_slider(0, 100, 90)
        
        # Розміщення в сітці (компактніше)
        row = 0
        eq_grid.addWidget(self.eq_enabled, row, 0, 1, 2)
        eq_grid.addWidget(QLabel("Тип:"), row, 2)
        eq_grid.addWidget(self.eq_engine, row, 3)
        eq_grid.addWidget(QLabel("Вид:"), row, 4)
        eq_grid.addWidget(self.eq_mode, row, 5)
        row += 1
        
        eq_grid.addWidget(QLabel("Смуги:"), row, 0)
        eq_grid.addWidget(self.eq_bars, row, 1)
        eq_grid.addWidget(QLabel("Товщ.:"), row, 2)
        eq_grid.addWidget(self.eq_thick, row, 3)
        eq_grid.addWidget(QLabel("Висота:"), row, 4)
        eq_grid.addWidget(self.eq_height, row, 5)
        row += 1
        
        eq_grid.addWidget(self.eq_fullscr, row, 0, 1, 2)
        eq_grid.addWidget(QLabel("Зсув Y:"), row, 2)
        eq_grid.addWidget(self.eq_yoffset, row, 3)
        eq_grid.addWidget(self.eq_mirror, row, 4, 1, 2)
        row += 1
        
        eq_grid.addWidget(QLabel("Колір:"), row, 0)
        eq_grid.addWidget(self.eq_color, row, 1)
        eq_grid.addWidget(QLabel("Прозорість:"), row, 2)
        eq_grid.addWidget(self.eq_opacity, row, 3, 1, 3)
        
        eq_layout.addWidget(eq_group)
        self.left_splitter.addWidget(eq_widget)
    
    def _setup_effects_section(self):
        """Секція ефектів (стиснута)"""
        effects_widget = QWidget()
        effects_layout = QVBoxLayout(effects_widget)
        effects_layout.setContentsMargins(0, 0, 0, 0)
        
        effects_group = QGroupBox("✨ Ефекти")
        effects_grid = QGridLayout(effects_group)
        effects_grid.setVerticalSpacing(4)
        effects_grid.setHorizontalSpacing(6)
        
        # Зірки
        self.st_enabled = QCheckBox("⭐ Зірки")
        self.st_style = QComboBox()
        self.st_style.addItems(["Класичні", "Сучасні", "Анімовані"])
        self.st_count = QSpinBox()
        self.st_count.setRange(0, 5000)
        self.st_count.setValue(200)
        self.st_count.setMaximumWidth(60)
        self.st_intensity = _mk_slider(0, 100, 55)
        self.st_size = QSpinBox()
        self.st_size.setRange(1, 20)
        self.st_size.setValue(2)
        self.st_size.setMaximumWidth(50)
        self.st_pulse = QSpinBox()
        self.st_pulse.setRange(0, 100)
        self.st_pulse.setValue(40)
        self.st_pulse.setMaximumWidth(50)
        self.st_color = ColorButton("#FFFFFF")
        self.st_opacity = _mk_slider(0, 100, 70)
        self.st_time_factor = QDoubleSpinBox()
        self.st_time_factor.setRange(0.1, 5.0)
        self.st_time_factor.setValue(1.0)
        self.st_time_factor.setSingleStep(0.1)
        self.st_time_factor.setMaximumWidth(60)
        
        # Дощ
        self.rn_enabled = QCheckBox("🌧️ Дощ")
        self.rn_count = QSpinBox()
        self.rn_count.setRange(0, 5000)
        self.rn_count.setValue(1200)
        self.rn_count.setMaximumWidth(60)
        self.rn_length = QSpinBox()
        self.rn_length.setRange(5, 200)
        self.rn_length.setValue(40)
        self.rn_length.setMaximumWidth(50)
        self.rn_thick = QSpinBox()
        self.rn_thick.setRange(1, 20)
        self.rn_thick.setValue(2)
        self.rn_thick.setMaximumWidth(40)
        self.rn_angle = QDoubleSpinBox()
        self.rn_angle.setRange(-80, 80)
        self.rn_angle.setValue(15.0)
        self.rn_angle.setMaximumWidth(60)
        self.rn_speed = QDoubleSpinBox()
        self.rn_speed.setRange(10.0, 800.0)
        self.rn_speed.setValue(160.0)
        self.rn_speed.setMaximumWidth(70)
        self.rn_color = ColorButton("#6CA0FF")
        self.rn_opacity = _mk_slider(0, 100, 55)
        
        # Дим
        self.sm_enabled = QCheckBox("🌫️ Дим")
        self.sm_density = QSpinBox()
        self.sm_density.setRange(0, 400)
        self.sm_density.setValue(60)
        self.sm_density.setMaximumWidth(50)
        self.sm_color = ColorButton("#A0A0FF")
        self.sm_opacity = _mk_slider(0, 100, 35)
        self.sm_speed = QDoubleSpinBox()
        self.sm_speed.setRange(-80.0, 80.0)
        self.sm_speed.setValue(12.0)
        self.sm_speed.setMaximumWidth(60)
        
        # Розміщення ефектів у сітці (компактніше)
        row = 0
        effects_grid.addWidget(self.st_enabled, row, 0, 1, 2)
        effects_grid.addWidget(QLabel("Стиль:"), row, 2)
        effects_grid.addWidget(self.st_style, row, 3)
        effects_grid.addWidget(QLabel("К-ть:"), row, 4)
        effects_grid.addWidget(self.st_count, row, 5)
        row += 1
        
        effects_grid.addWidget(QLabel("Інтенс.:"), row, 0)
        effects_grid.addWidget(self.st_intensity, row, 1, 1, 3)
        effects_grid.addWidget(QLabel("Розм.:"), row, 4)
        effects_grid.addWidget(self.st_size, row, 5)
        effects_grid.addWidget(QLabel("Пульс:"), row, 6)
        effects_grid.addWidget(self.st_pulse, row, 7)
        row += 1
        
        effects_grid.addWidget(QLabel("Колір:"), row, 0)
        effects_grid.addWidget(self.st_color, row, 1)
        effects_grid.addWidget(QLabel("Прозор.:"), row, 2)
        effects_grid.addWidget(self.st_opacity, row, 3, 1, 3)
        effects_grid.addWidget(QLabel("Час факт:"), row, 6)
        effects_grid.addWidget(self.st_time_factor, row, 7)
        row += 1
        
        effects_grid.addWidget(self.rn_enabled, row, 0, 1, 2)
        effects_grid.addWidget(QLabel("К-ть:"), row, 2)
        effects_grid.addWidget(self.rn_count, row, 3)
        effects_grid.addWidget(QLabel("Довж.:"), row, 4)
        effects_grid.addWidget(self.rn_length, row, 5)
        row += 1
        
        effects_grid.addWidget(QLabel("Товщ.:"), row, 0)
        effects_grid.addWidget(self.rn_thick, row, 1)
        effects_grid.addWidget(QLabel("Кут:"), row, 2)
        effects_grid.addWidget(self.rn_angle, row, 3)
        effects_grid.addWidget(QLabel("Швидк.:"), row, 4)
        effects_grid.addWidget(self.rn_speed, row, 5)
        row += 1
        
        effects_grid.addWidget(QLabel("Колір:"), row, 0)
        effects_grid.addWidget(self.rn_color, row, 1)
        effects_grid.addWidget(QLabel("Прозор.:"), row, 2)
        effects_grid.addWidget(self.rn_opacity, row, 3, 1, 3)
        row += 1
        
        effects_grid.addWidget(self.sm_enabled, row, 0, 1, 2)
        effects_grid.addWidget(QLabel("Густ.:"), row, 2)
        effects_grid.addWidget(self.sm_density, row, 3)
        effects_grid.addWidget(QLabel("Колір:"), row, 4)
        effects_grid.addWidget(self.sm_color, row, 5)
        row += 1
        
        effects_grid.addWidget(QLabel("Прозор.:"), row, 0)
        effects_grid.addWidget(self.sm_opacity, row, 1, 1, 3)
        effects_grid.addWidget(QLabel("Швидк.:"), row, 4)
        effects_grid.addWidget(self.sm_speed, row, 5, 1, 2)
        
        effects_layout.addWidget(effects_group)
        self.left_splitter.addWidget(effects_widget)
    
    def _setup_motion_section(self):
        """Секція руху камери"""
        motion_widget = QWidget()
        motion_layout = QVBoxLayout(motion_widget)
        motion_layout.setContentsMargins(0, 0, 0, 0)
        
        motion_group = QGroupBox("📷 Рух камери")
        motion_grid = QGridLayout(motion_group)
        motion_grid.setVerticalSpacing(4)
        motion_grid.setHorizontalSpacing(6)
        
        self.mv_enabled = QCheckBox("🎥 Рух камери")
        self.mv_direction = QComboBox()
        self.mv_direction.addItems([
            "Ліво→Право", "Право→Ліво", "Вверх", "Вниз", 
            "Зум IN", "Зум OUT", "Обертання", "Тряска"
        ])
        
        self.mv_speed = QDoubleSpinBox()
        self.mv_speed.setRange(0.0, 400.0)
        self.mv_speed.setValue(10.0)
        self.mv_speed.setMaximumWidth(60)
        
        self.mv_amount = QDoubleSpinBox()
        self.mv_amount.setRange(0.0, 100.0)
        self.mv_amount.setValue(5.0)
        self.mv_amount.setMaximumWidth(60)
        
        self.mv_oscillate = QCheckBox("Коливання")
        self.mv_oscillate.setChecked(True)
        
        self.mv_rotate_deg = QDoubleSpinBox()
        self.mv_rotate_deg.setRange(0.0, 45.0)
        self.mv_rotate_deg.setValue(8.0)
        self.mv_rotate_deg.setMaximumWidth(60)
        
        self.mv_rotate_hz = QDoubleSpinBox()
        self.mv_rotate_hz.setRange(0.01, 2.5)
        self.mv_rotate_hz.setValue(0.10)
        self.mv_rotate_hz.setSingleStep(0.01)
        self.mv_rotate_hz.setMaximumWidth(60)
        
        self.mv_shake_px = QDoubleSpinBox()
        self.mv_shake_px.setRange(0.0, 50.0)
        self.mv_shake_px.setValue(6.0)
        self.mv_shake_px.setMaximumWidth(60)
        
        self.mv_shake_hz = QDoubleSpinBox()
        self.mv_shake_hz.setRange(0.05, 8.0)
        self.mv_shake_hz.setValue(1.2)
        self.mv_shake_hz.setMaximumWidth(60)
        
        # Розміщення в сітці (компактніше)
        row = 0
        motion_grid.addWidget(self.mv_enabled, row, 0, 1, 2)
        motion_grid.addWidget(QLabel("Напрям:"), row, 2)
        motion_grid.addWidget(self.mv_direction, row, 3, 1, 3)
        row += 1
        
        motion_grid.addWidget(QLabel("Швидк.:"), row, 0)
        motion_grid.addWidget(self.mv_speed, row, 1)
        motion_grid.addWidget(QLabel("Сила:"), row, 2)
        motion_grid.addWidget(self.mv_amount, row, 3)
        motion_grid.addWidget(self.mv_oscillate, row, 4, 1, 2)
        row += 1
        
        motion_grid.addWidget(QLabel("Оберт °:"), row, 0)
        motion_grid.addWidget(self.mv_rotate_deg, row, 1)
        motion_grid.addWidget(QLabel("Оберт Гц:"), row, 2)
        motion_grid.addWidget(self.mv_rotate_hz, row, 3)
        motion_grid.addWidget(QLabel("Тряска px:"), row, 4)
        motion_grid.addWidget(self.mv_shake_px, row, 5)
        row += 1
        
        motion_grid.addWidget(QLabel("Тряска Гц:"), row, 0)
        motion_grid.addWidget(self.mv_shake_hz, row, 1)
        
        motion_layout.addWidget(motion_group)
        self.left_splitter.addWidget(motion_widget)
    
    def _setup_right_panel(self):
        """Налаштування правої панелі"""
        # Налаштування рендеру (перенесено в самий верх)
        self._setup_render_section()
        
        # Прев'ю
        self._setup_preview_section()
        
        # Журнал
        self._setup_log_section()
    
    def _setup_render_section(self):
        """Секція налаштувань рендеру (перенесена вверх)"""
        render_widget = QWidget()
        render_layout = QHBoxLayout(render_widget)
        render_layout.setContentsMargins(6, 6, 6, 6)
        
        render_group = QGroupBox("⚙️ Налаштування рендеру")
        render_grid = QGridLayout(render_group)
        render_grid.setVerticalSpacing(4)
        render_grid.setHorizontalSpacing(6)
        
        self.use_gpu = QCheckBox("Використовувати GPU")
        self.use_gpu.setChecked(True)
        
        self.gpu_device = QComboBox()
        self.gpu_device.addItems(["Авто", "NVIDIA", "Intel", "AMD", "CPU"])
        
        self.gpu_preset = QComboBox()
        self.gpu_preset.addItems(["Авто", "Швидкий", "Якісний", "Найкращий"])
        
        self.threads_count = QSpinBox()
        self.threads_count.setRange(0, 64)
        self.threads_count.setValue(16)
        self.threads_count.setMaximumWidth(60)
        
        self.jobs_count = QSpinBox()
        self.jobs_count.setRange(1, 10)
        self.jobs_count.setValue(1)
        self.jobs_count.setMaximumWidth(50)
        
        self.songs_count = QSpinBox()
        self.songs_count.setRange(1, 10)
        self.songs_count.setValue(2)
        self.songs_count.setMaximumWidth(50)
        
        self.gpu_load = _mk_slider(10, 100, 100)
        
        self.use_video_2s = QCheckBox("Відео ≥ 2с")
        self.use_video_2s.setChecked(True)
        
        self.until_material = QCheckBox("До кінця матеріалу")
        
        self.album_mode = QCheckBox("Альбомний режим")
        self.album_duration = QLineEdit("30:00")
        self.album_duration.setEnabled(False)
        self.album_duration.setMaximumWidth(70)
        self.album_mode.toggled.connect(self.album_duration.setEnabled)
        
        self.btn_clear_cache = QPushButton("🧹 Очистити кеш")
        self.btn_reset_session = QPushButton("🔄 Скинути сесію")
        
        # Розміщення в сітці (компактніше)
        row = 0
        render_grid.addWidget(self.use_gpu, row, 0, 1, 2)
        render_grid.addWidget(QLabel("Пристрій:"), row, 2)
        render_grid.addWidget(self.gpu_device, row, 3)
        row += 1
        
        render_grid.addWidget(QLabel("Якість:"), row, 0)
        render_grid.addWidget(self.gpu_preset, row, 1)
        render_grid.addWidget(QLabel("Потоки:"), row, 2)
        render_grid.addWidget(self.threads_count, row, 3)
        row += 1
        
        render_grid.addWidget(QLabel("Завдання:"), row, 0)
        render_grid.addWidget(self.jobs_count, row, 1)
        render_grid.addWidget(QLabel("Пісні:"), row, 2)
        render_grid.addWidget(self.songs_count, row, 3)
        row += 1
        
        render_grid.addWidget(QLabel("Навантаж. GPU:"), row, 0)
        render_grid.addWidget(self.gpu_load, row, 1, 1, 3)
        row += 1
        
        render_grid.addWidget(self.use_video_2s, row, 0)
        render_grid.addWidget(self.until_material, row, 1)
        render_grid.addWidget(self.album_mode, row, 2)
        render_grid.addWidget(self.album_duration, row, 3)
        row += 1
        
        render_grid.addWidget(self.btn_clear_cache, row, 0, 1, 2)
        render_grid.addWidget(self.btn_reset_session, row, 2, 1, 2)
        
        render_layout.addWidget(render_group)
        self.right_splitter.addWidget(render_widget)
    
    def _setup_preview_section(self):
        """Секція прев'ю (оптимізована)"""
        preview_widget = QWidget()
        preview_layout = QVBoxLayout(preview_widget)
        preview_layout.setContentsMargins(6, 6, 6, 6)
        
        preview_group = QGroupBox("👁️ Прев'ю")
        preview_group_layout = QVBoxLayout(preview_group)
        preview_group_layout.setSpacing(8)
        
        # Горизонтальний розділ: вибір формату + прев'ю
        preview_row = QHBoxLayout()
        preview_row.setSpacing(10)
        
        # Вибір формату
        self.format_selector = FormatSelectorVertical(self)
        
        # Прев'ю
        self.preview_label = QLabel("Прев'ю буде тут")
        self.preview_label.setMinimumSize(300, 200)
        self.preview_label.setStyleSheet("""
            QLabel {
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 #1A1A4A, stop:1 #0F0F30);
                border: 2px solid #2D2D7A; 
                border-radius: 12px;
                color: #A0A0FF;
                font-size: 12px;
                font-weight: bold;
                qproperty-alignment: AlignCenter;
            }
        """)
        
        preview_row.addWidget(self.format_selector, 1)
        preview_row.addWidget(self.preview_label, 2)
        
        # Кнопка застосування
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch(1)
        self.btn_apply_settings = QPushButton("💾 Застосувати налаштування")
        buttons_layout.addWidget(self.btn_apply_settings)
        
        preview_group_layout.addLayout(preview_row)
        preview_group_layout.addLayout(buttons_layout)
        preview_layout.addWidget(preview_group)
        
        self.right_splitter.addWidget(preview_widget)
    
    def _setup_log_section(self):
        """Секція журналу (оптимізована)"""
        log_widget = QWidget()
        log_layout = QVBoxLayout(log_widget)
        log_layout.setContentsMargins(6, 6, 6, 6)
        
        log_group = QGroupBox("📊 Журнал виконання")
        log_group_layout = QVBoxLayout(log_group)
        
        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(200)
        self.log_text.setStyleSheet("""
            QPlainTextEdit {
                background: #0A0A1A;
                border: 2px solid #1E1E5A;
                border-radius: 8px;
                padding: 6px;
                color: #C0C0FF;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 10px;
                selection-background-color: #3D75FF;
            }
        """)
        
        log_group_layout.addWidget(self.log_text)
        log_layout.addWidget(log_group)
        
        self.right_splitter.addWidget(log_widget)
    
    def _setup_proportions(self):
        """Налаштування пропорцій розділювачів"""
        # Пропорції головного розділювача
        self.main_splitter.setSizes([400, 600])  # Ліва: 400, Права: 600
        
        # Пропорції лівої панелі
        self.left_splitter.setSizes([100, 80, 180, 120, 80])  # Папки, Пресети, Еквалайзер, Ефекти, Рух
        
        # Пропорції правої панелі
        self.right_splitter.setSizes([120, 300, 280])  # Рендер, Прев'ю, Журнал
    
    def _setup_connections(self):
        """Налаштування з'єднань сигналів"""
        # Кнопки
        self.btn_apply_settings.clicked.connect(self._apply_settings)
        self.btn_clear_cache.clicked.connect(self._clear_cache)
        self.btn_reset_session.clicked.connect(self._reset_session)
        self.btn_save_preset.clicked.connect(self._save_preset)
        self.btn_delete_preset.clicked.connect(self._delete_preset)
        
        # Пресети
        self.presets_combo.currentIndexChanged.connect(self._load_preset)
        
        # Приховані комбо для синхронізації
        self._setup_hidden_combos()
        
        # Живе прев'ю
        self._connect_live_preview()
    
    def _setup_hidden_combos(self):
        """Налаштування прихованих комбобоксів"""
        self.format_combo = QComboBox()
        self.format_combo.addItems(["FHD", "Shorts", "4K"])
        self.format_combo.setVisible(False)
        
        self.resolution_combo = QComboBox()
        self.resolution_combo.addItems([
            "YouTube FHD 1920x1080 30fps",
            "YouTube Shorts 1080x1920 30fps",
            "Instagram 4:5 1080x1350 30fps", 
            "Instagram 1:1 1080x1080 30fps",
            "Facebook 4:5 1080x1350 30fps",
            "Facebook 1:1 1080x1080 30fps",
        ])
        self.resolution_combo.setVisible(False)
        
        # З'єднання вибору формату
        self.format_selector.selected.connect(self._on_format_selected)
    
    def _on_format_selected(self, format_key: str):
        """Обробка вибору формату"""
        format_mapping = {
            "youtube_16_9": ("FHD", "YouTube FHD 1920x1080 30fps"),
            "shorts_9_16": ("Shorts", "YouTube Shorts 1080x1920 30fps"),
            "ig_reels_9_16": ("Shorts", "YouTube Shorts 1080x1920 30fps"),
            "tiktok_9_16": ("Shorts", "YouTube Shorts 1080x1920 30fps"),
            "ig_4_5": ("FHD", "Instagram 4:5 1080x1350 30fps"),
            "ig_1_1": ("FHD", "Instagram 1:1 1080x1080 30fps"),
            "fb_4_5": ("FHD", "Facebook 4:5 1080x1350 30fps"),
            "fb_1_1": ("FHD", "Facebook 1:1 1080x1080 30fps"),
        }
        
        if format_key in format_mapping:
            format_type, resolution = format_mapping[format_key]
            self.format_combo.setCurrentText(format_type)
            
            # Додати роздільну здатність, якщо її немає
            if self.resolution_combo.findText(resolution) == -1:
                self.resolution_combo.addItem(resolution)
            self.resolution_combo.setCurrentText(resolution)
        
        self._update_preview(False)
    
    def _connect_live_preview(self):
        """Підключення сигналів для живого прев'ю"""
        widgets_to_connect = [
            self.eq_enabled, self.eq_engine, self.eq_mode, self.eq_bars,
            self.eq_thick, self.eq_height, self.eq_fullscr, self.eq_yoffset,
            self.eq_mirror, self.eq_baseline, self.eq_opacity,
            self.st_enabled, self.st_style, self.st_count, self.st_intensity,
            self.st_size, self.st_pulse, self.st_opacity, self.st_time_factor,
            self.rn_enabled, self.rn_count, self.rn_length, self.rn_thick,
            self.rn_angle, self.rn_speed, self.rn_opacity,
            self.sm_enabled, self.sm_density, self.sm_opacity, self.sm_speed,
            self.mv_enabled, self.mv_direction, self.mv_speed, self.mv_amount,
            self.mv_oscillate, self.mv_rotate_deg, self.mv_rotate_hz,
            self.mv_shake_px, self.mv_shake_hz,
            self.resolution_combo, self.format_combo
        ]
        
        for widget in widgets_to_connect:
            if hasattr(widget, 'toggled'):
                widget.toggled.connect(self._arm_live_preview)
            if hasattr(widget, 'valueChanged'):
                widget.valueChanged.connect(self._arm_live_preview)
            if hasattr(widget, 'currentIndexChanged'):
                widget.currentIndexChanged.connect(self._arm_live_preview)
            if hasattr(widget, 'currentTextChanged'):
                widget.currentTextChanged.connect(self._arm_live_preview)
            if hasattr(widget, 'textChanged'):
                widget.textChanged.connect(self._arm_live_preview)
    
    def _arm_live_preview(self):
        """Запуск таймера живого прев'ю"""
        if not self.live_preview_timer.isActive():
            self.live_preview_timer.start()
    
    # ------------------------ МЕТОДИ РОБОТИ З ДАНИМИ ------------------------
    def _build_equalizer_dict(self) -> Dict:
        """Побудова словника налаштувань еквалайзера"""
        return {
            "enabled": self.eq_enabled.isChecked(),
            "engine": self.eq_engine.currentText().lower().replace("хвилі", "waves").replace("частоти", "freqs"),
            "mode": self.eq_mode.currentText().lower().replace("стовпці", "bar").replace("лінії", "line").replace("крапки", "dot"),
            "bars": self.eq_bars.value(),
            "thickness": self.eq_thick.value(),
            "height": self.eq_height.value(),
            "fullscreen": self.eq_fullscr.isChecked(),
            "y_offset": self.eq_yoffset.value(),
            "mirror": self.eq_mirror.isChecked(),
            "baseline": self.eq_baseline.isChecked(),
            "color": _hex(self.eq_color.color()),
            "opacity": _pct(self.eq_opacity),
        }
    
    def _build_stars_dict(self) -> Dict:
        """Побудова словника налаштувань зірок"""
        return {
            "enabled": self.st_enabled.isChecked(),
            "style": self.st_style.currentText().lower().replace("класичні", "classic").replace("сучасні", "modern").replace("анімовані", "animated"),
            "count": self.st_count.value(),
            "intensity": _pct(self.st_intensity),
            "size": self.st_size.value(),
            "pulse": self.st_pulse.value(),
            "color": _hex(self.st_color.color()),
            "opacity": _pct(self.st_opacity),
            "time_factor": self.st_time_factor.value(),
        }
    
    def _build_rain_dict(self) -> Dict:
        """Побудова словника налаштувань дощу"""
        return {
            "enabled": self.rn_enabled.isChecked(),
            "count": self.rn_count.value(),
            "length": self.rn_length.value(),
            "thickness": self.rn_thick.value(),
            "angle_deg": self.rn_angle.value(),
            "speed": self.rn_speed.value(),
            "color": _hex(self.rn_color.color()),
            "opacity": _pct(self.rn_opacity),
        }
    
    def _build_smoke_dict(self) -> Dict:
        """Побудова словника налаштувань диму"""
        return {
            "enabled": self.sm_enabled.isChecked(),
            "density": self.sm_density.value(),
            "color": _hex(self.sm_color.color()),
            "opacity": _pct(self.sm_opacity),
            "speed": self.sm_speed.value(),
        }
    
    def _build_motion_dict(self) -> Dict:
        """Побудова словника налаштувань руху"""
        direction_mapping = {
            "Ліво→Право": "lr",
            "Право→Ліво": "rl", 
            "Вверх": "up",
            "Вниз": "down",
            "Зум IN": "zin",
            "Зум OUT": "zout",
            "Обертання": "rotate",
            "Тряска": "shake"
        }
        
        return {
            "enabled": self.mv_enabled.isChecked(),
            "direction": direction_mapping.get(self.mv_direction.currentText(), "lr"),
            "speed": self.mv_speed.value(),
            "amount": self.mv_amount.value(),
            "oscillate": self.mv_oscillate.isChecked(),
            "rot_deg": self.mv_rotate_deg.value(),
            "rot_hz": self.mv_rotate_hz.value(),
            "shake_px": self.mv_shake_px.value(),
            "shake_hz": self.mv_shake_hz.value(),
        }
    
    def _get_resolution_fps(self) -> Tuple[int, int, int]:
        """Отримання роздільності та FPS з комбобоксу"""
        resolution_text = self.resolution_combo.currentText()
        try:
            # Пошук роздільності у форматі "ШиринаxВисота"
            for part in resolution_text.split():
                if 'x' in part:
                    width, height = map(int, part.split('x'))
                    # FPS за замовчуванням 30
                    return width, height, 30
        except Exception:
            pass
        
        return 1920, 1080, 30  # Значення за замовчуванням
    
    def _build_config(self) -> Dict:
        """Побудова повного словника конфігурації"""
        width, height, fps = self._get_resolution_fps()
        
        return {
            "music_dir": _ensure_dir(self.music_path.text()),
            "media_dir": _ensure_dir(self.media_path.text()),
            "out_dir": _ensure_dir(self.output_path.text()),
            "resolution": f"{width}x{height} {fps}fps",
            "gpu": self.gpu_device.currentText().lower() if self.use_gpu.isChecked() else "cpu",
            "use_gpu": self.use_gpu.isChecked(),
            "gpu_preset": self.gpu_preset.currentText(),
            "threads": self.threads_count.value(),
            "jobs": self.jobs_count.value(),
            "songs": self.songs_count.value(),
            "gpu_load": _pct(self.gpu_load),
            "use_video_ge2s": self.use_video_2s.isChecked(),
            "until_material": self.until_material.isChecked(),
            "album_enabled": self.album_mode.isChecked(),
            "album_sec": _mmss_to_seconds(self.album_duration.text()) if self.album_mode.isChecked() else 0,
            "eq_ui": self._build_equalizer_dict(),
            "stars_ui": self._build_stars_dict(),
            "rain_ui": self._build_rain_dict(),
            "smoke_ui": self._build_smoke_dict(),
            "motion_ui": self._build_motion_dict(),
        }
    
    def _update_preview(self, initial: bool = False):
        """Оновлення прев'ю"""
        width, height, fps = self._get_resolution_fps()
        
        # Створення базового зображення з темно-синім фоном
        preview_pixmap = QPixmap(width, height)
        preview_pixmap.fill(QColor("#0A0A2A"))
        
        painter = QPainter(preview_pixmap)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        
        # Застосування ефектів
        try:
            # Еквалайзер
            eq_settings = self._build_equalizer_dict()
            if eq_settings["enabled"]:
                eq_overlay = make_eq_overlay(eq_settings, width, height)
                painter.drawPixmap(0, 0, eq_overlay)
            
            # Зірки
            stars_settings = self._build_stars_dict()
            if stars_settings["enabled"]:
                stars_overlay = make_stars_overlay(stars_settings, width, height)
                painter.drawPixmap(0, 0, stars_overlay)
            
            # Дощ
            rain_settings = self._build_rain_dict()
            if rain_settings["enabled"]:
                rain_overlay = make_rain_overlay(rain_settings, width, height)
                painter.drawPixmap(0, 0, rain_overlay)
            
            # Дим
            smoke_settings = self._build_smoke_dict()
            if smoke_settings["enabled"]:
                smoke_overlay = make_smoke_overlay(smoke_settings, width, height)
                painter.drawPixmap(0, 0, smoke_overlay)
            
            # Рух
            motion_settings = self._build_motion_dict()
            if motion_settings["enabled"]:
                draw_motion_indicator(painter, preview_pixmap.rect(), motion_settings)
                
        except Exception as e:
            # Резервне малювання у разі помилки
            painter.setPen(QColor("#FF6B6B"))
            painter.setFont(QFont("Arial", 20))
            painter.drawText(preview_pixmap.rect(), Qt.AlignCenter, f"Помилка: {str(e)}")
        
        painter.end()
        
        # Масштабування для відображення
        scaled_pixmap = preview_pixmap.scaled(
            self.preview_label.width(),
            self.preview_label.height(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        
        self.preview_label.setPixmap(scaled_pixmap)
    
    def _sync_format_resolution(self):
        """Синхронізація формату та роздільності"""
        current_format = self.format_combo.currentText()
        format_to_resolution = {
            "Shorts": "YouTube Shorts 1080x1920 30fps",
            "FHD": "YouTube FHD 1920x1080 30fps",
            "4K": "4K 3840x2160 30fps"
        }
        
        if current_format in format_to_resolution:
            resolution = format_to_resolution[current_format]
            if self.resolution_combo.findText(resolution) >= 0:
                self.resolution_combo.setCurrentText(resolution)
    
    # ------------------------ МЕТОДИ РОБОТИ З КОНФІГУРАЦІЄЮ ------------------------
    def _save_config(self):
        """Збереження конфігурації у файл"""
        try:
            config = self._build_config()
            with open(CONFIG_FILE, "w", encoding="utf-8") as file:
                json.dump(config, file, ensure_ascii=False, indent=2)
        except Exception as e:
            self._log_message(f"Помилка збереження конфігурації: {str(e)}")
    
    def _load_config(self):
        """Завантаження конфігурації з файлу"""
        try:
            if not os.path.isfile(CONFIG_FILE):
                return
            
            with open(CONFIG_FILE, "r", encoding="utf-8") as file:
                config = json.load(file)
            
            # Завантаження основних налаштувань
            self.music_path.setText(config.get("music_dir", ""))
            self.media_path.setText(config.get("media_dir", ""))
            self.output_path.setText(config.get("out_dir", ""))
            
            resolution = config.get("resolution", "YouTube FHD 1920x1080 30fps")
            if self.resolution_combo.findText(resolution) >= 0:
                self.resolution_combo.setCurrentText(resolution)
            
            self.use_gpu.setChecked(config.get("use_gpu", True))
            self.gpu_device.setCurrentText(config.get("gpu", "Авто").capitalize())
            self.gpu_preset.setCurrentText(config.get("gpu_preset", "Авто"))
            self.threads_count.setValue(config.get("threads", 16))
            self.jobs_count.setValue(config.get("jobs", 1))
            self.songs_count.setValue(config.get("songs", 2))
            self.gpu_load.setValue(config.get("gpu_load", 100))
            self.use_video_2s.setChecked(config.get("use_video_ge2s", True))
            self.until_material.setChecked(config.get("until_material", False))
            
            album_enabled = config.get("album_enabled", False)
            self.album_mode.setChecked(album_enabled)
            if album_enabled:
                album_seconds = config.get("album_sec", 0)
                self.album_duration.setText(_seconds_to_mmss(album_seconds))
            
            # Завантаження налаштувань ефектів
            self._load_effects_config(config)
            
        except Exception as e:
            self._log_message(f"Помилка завантаження конфігурації: {str(e)}")
    
    def _load_effects_config(self, config: Dict):
        """Завантаження налаштувань ефектів з конфігурації"""
        # Еквалайзер
        if "eq_ui" in config:
            eq = config["eq_ui"]
            self.eq_enabled.setChecked(eq.get("enabled", False))
            self.eq_engine.setCurrentText("Хвилі" if eq.get("engine") == "waves" else "Частоти")
            self.eq_mode.setCurrentText({
                "bar": "Стовпці", "line": "Лінії", "dot": "Крапки"
            }.get(eq.get("mode", "bar"), "Стовпці"))
            self.eq_bars.setValue(eq.get("bars", 96))
            self.eq_thick.setValue(eq.get("thickness", 3))
            self.eq_height.setValue(eq.get("height", 360))
            self.eq_fullscr.setChecked(eq.get("fullscreen", False))
            self.eq_yoffset.setValue(eq.get("y_offset", 0))
            self.eq_mirror.setChecked(eq.get("mirror", True))
            self.eq_baseline.setChecked(eq.get("baseline", False))
            self.eq_color.setColor(QColor(eq.get("color", "#FFFFFF")))
            self.eq_opacity.setValue(eq.get("opacity", 90))
        
        # Зірки
        if "stars_ui" in config:
            st = config["stars_ui"]
            self.st_enabled.setChecked(st.get("enabled", False))
            self.st_style.setCurrentText({
                "classic": "Класичні", "modern": "Сучасні", "animated": "Анімовані"
            }.get(st.get("style", "classic"), "Класичні"))
            self.st_count.setValue(st.get("count", 200))
            self.st_intensity.setValue(st.get("intensity", 55))
            self.st_size.setValue(st.get("size", 2))
            self.st_pulse.setValue(st.get("pulse", 40))
            self.st_color.setColor(QColor(st.get("color", "#FFFFFF")))
            self.st_opacity.setValue(st.get("opacity", 70))
            self.st_time_factor.setValue(st.get("time_factor", 1.0))
        
        # Дощ
        if "rain_ui" in config:
            rn = config["rain_ui"]
            self.rn_enabled.setChecked(rn.get("enabled", False))
            self.rn_count.setValue(rn.get("count", 1200))
            self.rn_length.setValue(rn.get("length", 40))
            self.rn_thick.setValue(rn.get("thickness", 2))
            self.rn_angle.setValue(rn.get("angle_deg", 15.0))
            self.rn_speed.setValue(rn.get("speed", 160.0))
            self.rn_color.setColor(QColor(rn.get("color", "#9BE2FF")))
            self.rn_opacity.setValue(rn.get("opacity", 55))
        
        # Дим
        if "smoke_ui" in config:
            sm = config["smoke_ui"]
            self.sm_enabled.setChecked(sm.get("enabled", False))
            self.sm_density.setValue(sm.get("density", 60))
            self.sm_color.setColor(QColor(sm.get("color", "#A0A0A0")))
            self.sm_opacity.setValue(sm.get("opacity", 35))
            self.sm_speed.setValue(sm.get("speed", 12.0))
        
        # Рух
        if "motion_ui" in config:
            mv = config["motion_ui"]
            self.mv_enabled.setChecked(mv.get("enabled", False))
            
            direction_map = {
                "lr": "Ліво→Право", "rl": "Право→Ліво", "up": "Вверх",
                "down": "Вниз", "zin": "Зум IN", "zout": "Зум OUT",
                "rotate": "Обертання", "shake": "Тряска"
            }
            direction = direction_map.get(mv.get("direction", "lr"), "Ліво→Право")
            self.mv_direction.setCurrentText(direction)
            
            self.mv_speed.setValue(mv.get("speed", 10.0))
            self.mv_amount.setValue(mv.get("amount", 5.0))
            self.mv_oscillate.setChecked(mv.get("oscillate", True))
            self.mv_rotate_deg.setValue(mv.get("rot_deg", 8.0))
            self.mv_rotate_hz.setValue(mv.get("rot_hz", 0.10))
            self.mv_shake_px.setValue(mv.get("shake_px", 6.0))
            self.mv_shake_hz.setValue(mv.get("shake_hz", 1.2))
    
    # ------------------------ МЕТОДИ РОБОТИ З ПРЕСЕТАМИ ------------------------
    def _load_presets(self):
        """Завантаження списку пресетів"""
        try:
            self.presets_combo.clear()
            
            if os.path.isfile(USER_PRESETS_FILE):
                with open(USER_PRESETS_FILE, "r", encoding="utf-8") as file:
                    presets = json.load(file)
                
                for preset_name in sorted(presets.keys()):
                    self.presets_combo.addItem(preset_name)
        except Exception as e:
            self._log_message(f"Помилка завантаження пресетів: {str(e)}")
    
    def _save_preset(self):
        """Збереження поточних налаштувань як пресет"""
        preset_name, ok = QInputDialog.getText(
            self, "Збереження пресету", "Введіть назву пресету:"
        )
        
        if not ok or not preset_name.strip():
            return
        
        try:
            # Завантаження існуючих пресетів
            presets = {}
            if os.path.isfile(USER_PRESETS_FILE):
                with open(USER_PRESETS_FILE, "r", encoding="utf-8") as file:
                    presets = json.load(file)
            
            # Додавання нового пресету
            presets[preset_name] = self._build_config()
            
            # Обмеження кількості пресетів
            if len(presets) > 20:
                # Видалення найстарішого пресету
                oldest_key = next(iter(presets))
                del presets[oldest_key]
            
            # Збереження у файл
            with open(USER_PRESETS_FILE, "w", encoding="utf-8") as file:
                json.dump(presets, file, ensure_ascii=False, indent=2)
            
            # Оновлення списку
            self._load_presets()
            self.presets_combo.setCurrentText(preset_name)
            
            self._log_message(f"✅ Пресет '{preset_name}' збережено")
            
        except Exception as e:
            self._log_message(f"❌ Помилка збереження пресету: {str(e)}")
    
    def _delete_preset(self):
        """Видалення вибраного пресету"""
        current_preset = self.presets_combo.currentText()
        if not current_preset:
            return
        
        reply = QMessageBox.question(
            self, "Підтвердження видалення",
            f"Видалити пресет '{current_preset}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.No:
            return
        
        try:
            # Завантаження пресетів
            presets = {}
            if os.path.isfile(USER_PRESETS_FILE):
                with open(USER_PRESETS_FILE, "r", encoding="utf-8") as file:
                    presets = json.load(file)
            
            # Видалення пресету
            if current_preset in presets:
                del presets[current_preset]
                
                # Збереження оновленого списку
                with open(USER_PRESETS_FILE, "w", encoding="utf-8") as file:
                    json.dump(presets, file, ensure_ascii=False, indent=2)
                
                # Оновлення комбобоксу
                self._load_presets()
                self._log_message(f"✅ Пресет '{current_preset}' видалено")
            else:
                self._log_message(f"❌ Пресет '{current_preset}' не знайдено")
                
        except Exception as e:
            self._log_message(f"❌ Помилка видалення пресету: {str(e)}")
    
    def _load_preset(self):
        """Завантаження вибраного пресету"""
        preset_name = self.presets_combo.currentText()
        if not preset_name:
            return
        
        try:
            # Завантаження пресетів
            if not os.path.isfile(USER_PRESETS_FILE):
                self._log_message("❌ Файл пресетів не знайдено")
                return
            
            with open(USER_PRESETS_FILE, "r", encoding="utf-8") as file:
                presets = json.load(file)
            
            # Перевірка наявності пресету
            if preset_name not in presets:
                self._log_message(f"❌ Пресет '{preset_name}' не знайдено")
                return
            
            config = presets[preset_name]
            
            # Застосування налаштувань
            self._apply_preset_config(config)
            self._log_message(f"✅ Пресет '{preset_name}' завантажено")
            
        except Exception as e:
            self._log_message(f"❌ Помилка завантаження пресету: {str(e)}")
    
    def _apply_preset_config(self, config: Dict):
        """Застосування конфігурації пресету"""
        # Основні налаштування
        self.music_path.setText(config.get("music_dir", ""))
        self.media_path.setText(config.get("media_dir", ""))
        self.output_path.setText(config.get("out_dir", ""))
        
        resolution = config.get("resolution", "YouTube FHD 1920x1080 30fps")
        if self.resolution_combo.findText(resolution) >= 0:
            self.resolution_combo.setCurrentText(resolution)
        
        self.use_gpu.setChecked(config.get("use_gpu", True))
        
        gpu_device = config.get("gpu", "auto").capitalize()
        if self.gpu_device.findText(gpu_device) >= 0:
            self.gpu_device.setCurrentText(gpu_device)
        
        self.gpu_preset.setCurrentText(config.get("gpu_preset", "Авто"))
        self.threads_count.setValue(config.get("threads", 16))
        self.jobs_count.setValue(config.get("jobs", 1))
        self.songs_count.setValue(config.get("songs", 2))
        self.gpu_load.setValue(config.get("gpu_load", 100))
        self.use_video_2s.setChecked(config.get("use_video_ge2s", True))
        self.until_material.setChecked(config.get("until_material", False))
        
        album_enabled = config.get("album_enabled", False)
        self.album_mode.setChecked(album_enabled)
        if album_enabled:
            album_seconds = config.get("album_sec", 0)
            self.album_duration.setText(_seconds_to_mmss(album_seconds))
        
        # Налаштування ефектів
        self._load_effects_config(config)
        
        # Оновлення прев'ю
        self._update_preview()
    
    # ------------------------ МЕТОДИ ІНТЕРФЕЙСУ ------------------------
    def _apply_settings(self):
        """Застосування налаштувань"""
        self._update_preview()
        self._save_config()
        self._log_message("✅ Налаштування застосовано та збережено")
    
    def _clear_cache(self):
        """Очищення кешу"""
        try:
            if os.path.isdir(CACHE_DIR):
                shutil.rmtree(CACHE_DIR, ignore_errors=True)
            os.makedirs(CACHE_DIR, exist_ok=True)
            self._log_message("✅ Кеш очищено")
        except Exception as e:
            self._log_message(f"❌ Помилка очищення кешу: {str(e)}")
    
    def _reset_session(self):
        """Скидання сесії"""
        try:
            self._stop_processing()
            self._reset_session_state()
            reset_processing_state()
            self._log_message("✅ Сесію скинуто")
        except Exception as e:
            self._log_message(f"❌ Помилка скидання сесії: {str(e)}")
    
    def _reset_session_state(self):
        """Скидання стану сесії"""
        try:
            # Очищення черги
            while True:
                try:
                    self.status_queue.get_nowait()
                except queue.Empty:
                    break
            
            # Видалення тимчасових файлів
            if os.path.isdir(STAGE_DIR):
                shutil.rmtree(STAGE_DIR, ignore_errors=True)
        except Exception:
            pass
    
    def _log_message(self, message: str):
        """Додавання повідомлення до журналу"""
        try:
            self.log_text.appendPlainText(message)
            # Прокрутка до низу
            cursor = self.log_text.textCursor()
            cursor.movePosition(cursor.End)
            self.log_text.setTextCursor(cursor)
        except Exception:
            pass
    
    def _start_processing(self):
        """Запуск обробки"""
        if self._running:
            return
        
        # Перевірка обов'язкових полів
        config = self._build_config()
        if not config["music_dir"] or not config["out_dir"]:
            QMessageBox.warning(self, "Помилка", "Заповніть обов'язкові папки: Музика та Вихід")
            return
        
        # Очищення журналу
        self.log_text.clear()
        
        # Збереження конфігурації
        self._save_config()
        
        try:
            # Збереження конфігурації для налагодження
            debug_config_path = os.path.join(CACHE_DIR, "debug_config.json")
            with open(debug_config_path, "w", encoding="utf-8") as file:
                json.dump(config, file, ensure_ascii=False, indent=2)
        except Exception:
            pass
        
        # Запуск обробки
        try:
            self.cancel_event.clear()
            self._running = True
            self.sig_running.emit(True)
            
            self._songs_total = config.get("songs", 1)
            self._songs_done = 0
            
            start_video_jobs(config, self.status_queue, self.cancel_event)
            self.poll_timer.start()
            
            self._log_message("▶ Початок обробки відео...")
            
        except Exception as e:
            self._running = False
            self.sig_running.emit(False)
            self._log_message(f"❌ Помилка запуску: {str(e)}")
    
    def _stop_processing(self):
        """Зупинка обробки"""
        try:
            self.cancel_event.set()
            stop_all_jobs()
            self.poll_timer.stop()
            
            # Очищення черги
            while True:
                try:
                    self.status_queue.get_nowait()
                except queue.Empty:
                    break
                    
        finally:
            self.cancel_event.clear()
            self._running = False
            self.sig_running.emit(False)
            self._log_message("⏹ Обробку зупинено")
    
    def _poll_status(self):
        """Перевірка статусу обробки"""
        while True:
            try:
                message = self.status_queue.get_nowait()
            except queue.Empty:
                break
            
            message_type = message.get("type")
            
            if message_type == "start":
                self._log_message("▶ Старт рендерингу")
                
            elif message_type == "log":
                log_message = message.get("msg", "")
                self._log_message(log_message)
                
            elif message_type == "progress":
                progress_value = message.get("value", 0)
                try:
                    self.sig_progress.emit(int(progress_value), "Рендеринг")
                except Exception:
                    pass
                    
            elif message_type == "done":
                output_path = message.get("output", "")
                self._songs_done += 1
                
                success_message = f"✅ Готово: {output_path}"
                self._log_message(success_message)
                self.sig_biglog.emit(success_message)
                
                # Перевірка завершення всіх завдань
                if self._songs_done >= max(1, self._songs_total):
                    self.poll_timer.stop()
                    self._running = False
                    self.sig_running.emit(False)
                    self._log_message("🎉 Вся обробка завершена!")
                    
            elif message_type == "error":
                error_message = message.get("msg", "")
                error_display = f"❌ {error_message}"
                self._log_message(error_display)
                self.sig_biglog.emit(error_display)
                
                self.poll_timer.stop()
                self._running = False
                self.sig_running.emit(False)
    
    # ------------------------ МЕТОДИ ІНТЕГРАЦІЇ ------------------------
    def handle_start(self, auto_mode: bool = False):
        """Обробка команди старту"""
        self._start_processing()
    
    def handle_stop(self):
        """Обробка команди зупинки"""
        self._stop_processing()
    
    def set_host(self, host):
        """Встановлення батьківського вікна"""
        self.host = host
        try:
            self.sig_progress.connect(
                lambda value, label="Відео": host.set_progress(self, int(value), label)
            )
            self.sig_running.connect(
                lambda running: host.set_running(self, bool(running))
            )
        except Exception:
            pass
    
    def apply_scale(self, scale: float):
        """Застосування масштабування"""
        # Масштабування шрифтів
        base_font = self.font()
        base_font.setPointSize(max(8, int(10 * scale)))
        self.setFont(base_font)
        
        # Масштабування прев'ю
        self.preview_label.setFixedHeight(max(180, int(200 * scale)))
        self.preview_label.setMinimumWidth(max(250, int(300 * scale)))
        
        # Масштабування кнопок
        button_height = max(22, int(28 * scale))
        buttons = [
            self.btn_apply_settings, self.btn_clear_cache, self.btn_reset_session,
            self.btn_save_preset, self.btn_delete_preset
        ]
        for button in buttons:
            button.setMinimumHeight(button_height)
        
        # Масштабування журналу
        log_font = self.log_text.font()
        log_font.setPointSize(max(7, int(10 * scale)))
        self.log_text.setFont(log_font)
        
        # Масштабування карток форматів
        self.format_selector.apply_scale(scale)


# ------------------------ ТЕСТУВАННЯ ------------------------
if __name__ == "__main__":
    import sys
    
    app = QApplication(sys.argv)
    
    # Завантаження шрифтів
    if hasattr(QFontDatabase, 'addApplicationFont'):
        # Спроба завантажити кращі шрифти, якщо вони є
        pass
    
    window = VideoPage()
    window.setWindowTitle("Video Processor - Оптимізована версія")
    window.resize(1200, 800)
    window.show()
    
    sys.exit(app.exec())