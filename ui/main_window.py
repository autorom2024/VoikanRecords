# -*- coding: utf-8 -*-
from __future__ import annotations
from collections import defaultdict
import os
from datetime import datetime
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QStackedWidget,
    QGroupBox, QProgressBar, QTextEdit, QSizePolicy, QListWidgetItem, QTabWidget,
    QFrame, QLabel, QStatusBar, QMessageBox, QPushButton, QGraphicsDropShadowEffect,
    QComboBox
)
from PySide6.QtCore import Qt, QSettings, QSize, QRectF, QEvent, QTimer
from PySide6.QtGui import (
    QCloseEvent, QIcon, QPainter, QPixmap, QPainterPath, QColor, QPen, QFont,
    QLinearGradient, QRadialGradient, QConicalGradient, QFontMetrics
)
from auth_logic import get_license_status, update_hwid_in_sheet, save_local_license, get_machine_id

# --- Імпорти з фолбеками (залишено без змін) ---
try:
    from .custom_title_bar import CustomTitleBar
except ImportError:
    class CustomTitleBar(QWidget):
        def add_widget_to_right(self, widget): pass
        def set_title(self, title): pass
        def update_window_state(self): pass
        def set_main_widget(self, widget): pass
import psutil
try:
    import pynvml
    PYNML_AVAILABLE = True
except ImportError:
    PYNML_AVAILABLE = False
try:
    from ui.pages.audio_page import AudioPage
except ImportError:
    class AudioPage(QWidget):
        def set_host(self, host): pass
try:
    from ui.pages.photo_page import PhotoPage
except ImportError:
    class PhotoPage(QWidget): pass
try:
    from ui.pages.video_page import VideoPage
except ImportError:
    class VideoPage(QWidget):
        def set_host(self, host): pass
try:
    from ui.pages.shorts_page import ShortsPage
except ImportError:
    class ShortsPage(QWidget):
        def set_host(self, host): pass
try:
    from ui.pages.tab_planner import PlannerTab
except ImportError:
    class PlannerTab(QWidget): pass
try:
    from ui.pages.tab_autofill import AutoFillTab
except ImportError:
    class AutoFillTab(QWidget): pass
try:
    from .glass_item_delegate import GlassItemDelegate
except ImportError:
    from PySide6.QtWidgets import QStyledItemDelegate
    class GlassItemDelegate(QStyledItemDelegate): pass
try:
    from .animated_push_button import AnimatedPushButton
except ImportError:
    from PySide6.QtWidgets import QPushButton
    class AnimatedPushButton(QPushButton): pass

# --- Глобальні налаштування ---
APP_VERSION = "1.3.5"
WINDOW_WIDTH, WINDOW_HEIGHT = 1440, 860
REMEMBER_LAST_SIZE, WINDOW_FIXED = True, False
WINDOW_MIN_W, WINDOW_MIN_H = 1100, 720
DESIGN_WIDTH, DESIGN_HEIGHT = 1440, 860
MIN_SCALE, MAX_SCALE = 0.8, 1.5
LEFT_SIDEBAR_BASE_W, RIGHT_PANEL_BASE_W = 260, 320
BASE_APP_POINT_SIZE, MIN_APP_POINT_SIZE = 10.5, 9.0
BTN_H_BASE, PROGRESS_H_BASE = 38, 8
ORG_NAME, APP_NAME = "Voikan", "MultimediaPanel"
os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
os.environ["QT_SCALE_FACTOR"] = "1"
os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"

# --- Допоміжний пошук assets ---
def _asset_path(*parts):
    base = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(base, *parts),
        os.path.join(base, "..", "assets", *parts),
        os.path.join(base, "..", *parts),
    ]
    for p in candidates:
        if os.path.exists(p):
            return os.path.abspath(p)
    return None

# --- Великий логотип з літерою V ---
class MenuLogoWidget(QWidget):
    """Велика стильна літера V для меню"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(140)
        self.setObjectName("menuLogoWidget")

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        rect = self.rect()
        w, h = rect.width(), rect.height()
        
        # Кольори в стилі дизайну
        primary_blue = QColor(26, 255, 224)
        accent_purple = QColor(168, 85, 247)
        dark_bg = QColor(15, 25, 35)
        
        # Центруємо логотип
        center_x = w // 2
        logo_size = min(w * 0.85, h * 0.9)
        
        # Створюємо градієнт для літери V
        gradient = QLinearGradient(0, 0, 0, logo_size)
        gradient.setColorAt(0.0, primary_blue)
        gradient.setColorAt(0.7, accent_purple)
        gradient.setColorAt(1.0, QColor(100, 60, 200))
        
        # Малюємо велику літеру V
        font = QFont("Poppins", -1, QFont.Black)
        font.setPixelSize(int(logo_size))
        
        # Створюємо шлях для літери V
        text_path = QPainterPath()
        text_path.addText(0, 0, font, "V")
        
        # Обчислюємо bounding rect для центрування
        text_rect = text_path.boundingRect()
        x_offset = center_x - text_rect.width() / 2
        y_offset = h * 0.78
        
        text_path = QPainterPath()
        text_path.addText(x_offset, y_offset, font, "V")
        
        # Ефект світіння
        glow_layers = [
            (30, 25, QColor(26, 255, 224, 40)),
            (20, 20, QColor(168, 85, 247, 50)),
            (12, 15, QColor(100, 200, 255, 60)),
            (6, 10, QColor(255, 255, 255, 80))
        ]
        
        for width, alpha, color in glow_layers:
            pen = QPen(color, width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawPath(text_path)
        
        # Основний контур з градієнтом
        p.setPen(QPen(gradient, 6))
        p.setBrush(dark_bg)
        p.drawPath(text_path)
        
        # Внутрішнє заповнення з прозорістю
        inner_gradient = QLinearGradient(0, 0, 0, logo_size)
        inner_gradient.setColorAt(0.0, QColor(26, 255, 224, 180))
        inner_gradient.setColorAt(1.0, QColor(168, 85, 247, 180))
        
        p.setPen(Qt.NoPen)
        p.setBrush(inner_gradient)
        p.drawPath(text_path)
        
        p.end()

def _get_logo_pixmap(size=64):
    w = MenuLogoWidget()
    w.resize(int(size * 2.1), size)
    pm = QPixmap(w.size())
    pm.fill(Qt.transparent)
    w.render(pm)
    return pm

# --- ОНОВЛЕНІ ГЕНЕРАТОРИ ІКОНОК ---
def _mk_pixmap(size: int, paint_fn):
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    paint_fn(p, size)
    p.end()
    return pm

def _icon_copyright(size=16):
    def _paint(p: QPainter, s: int):
        p.setPen(QPen(QColor("#8A97A8"), 1.2))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QRectF(1, 1, s - 2, s - 2))
        font = QFont("Segoe UI", -1, QFont.Bold)
        font.setPixelSize(int(s * 0.55))
        p.setFont(font)
        p.setPen(QColor("#8A97A8"))
        p.drawText(QRectF(0, 0, s, s), Qt.AlignCenter, "C")
    return QIcon(_mk_pixmap(size, _paint))

# Нова музична іконка для аудіо
def _icon_audio_v3(size=36):
    def _paint(p: QPainter, s: int):
        # Фон
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(30, 30, 35))
        p.drawEllipse(0, 0, s, s)
        
        # Музичні хвилі
        grad = QLinearGradient(0, s/2, s, s/2)
        grad.setColorAt(0, QColor("#B070FF"))
        grad.setColorAt(0.5, QColor("#8A2BE2"))
        grad.setColorAt(1, QColor("#6A0DAD"))
        
        p.setPen(QPen(grad, 3))
        p.setBrush(Qt.NoBrush)
        
        # Малюємо хвилі
        wave_height = s * 0.15
        center_y = s / 2
        
        # Перша хвиля
        path1 = QPainterPath()
        path1.moveTo(s * 0.2, center_y)
        for i in range(3):
            x = s * (0.2 + 0.2 * i)
            path1.cubicTo(x + s * 0.05, center_y - wave_height,
                         x + s * 0.15, center_y - wave_height,
                         x + s * 0.2, center_y)
        p.drawPath(path1)
        
        # Нота
        p.setBrush(grad)
        p.drawEllipse(s * 0.65, center_y - s * 0.1, s * 0.15, s * 0.15)
        p.drawLine(int(s * 0.8), int(center_y - s * 0.1), int(s * 0.8), int(center_y + s * 0.2))

    return QIcon(_mk_pixmap(size, _paint))

def _icon_photo_v2(size=36):
    def _paint(p: QPainter, s: int):
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(30, 35, 35))
        p.drawRoundedRect(QRectF(s * 0.05, s * 0.2, s * 0.9, s * 0.6), 5, 5)
        grad = QConicalGradient(s / 2, s / 2, 90)
        grad.setColorAt(0, Qt.cyan)
        grad.setColorAt(0.5, Qt.magenta)
        grad.setColorAt(1, Qt.cyan)
        p.setBrush(grad)
        p.drawEllipse(s * 0.25, s * 0.25, s * 0.5, s * 0.5)
        p.setBrush(QColor(20, 20, 20))
        p.drawEllipse(s * 0.4, s * 0.4, s * 0.2, s * 0.2)
    return QIcon(_mk_pixmap(size, _paint))

def _icon_video_v2(size=36):
    def _paint(p: QPainter, s: int):
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#FF4848"))
        p.drawRoundedRect(QRectF(s * 0.1, s * 0.2, s * 0.8, s * 0.6), s * 0.15, s * 0.15)
        path = QPainterPath()
        path.moveTo(s * 0.4, s * 0.35)
        path.lineTo(s * 0.7, s * 0.5)
        path.lineTo(s * 0.4, s * 0.65)
        path.closeSubpath()
        p.setBrush(QColor("white"))
        p.drawPath(path)
    return QIcon(_mk_pixmap(size, _paint))

def _icon_planner_v2(size=36):
    def _paint(p: QPainter, s: int):
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(60, 60, 90))
        p.drawRoundedRect(QRectF(s * 0.1, s * 0.15, s * 0.8, s * 0.7), 4, 4)
        p.setBrush(QColor(200, 210, 255))
        p.drawRect(s * 0.25, s * 0.4, s * 0.5, s * 0.35)
        p.setPen(QPen(QColor(60, 60, 90), 2.0))
        p.drawLine(s * 0.25, s * 0.58, s * 0.75, s * 0.58)
    return QIcon(_mk_pixmap(size, _paint))

def _icon_autofill_v2(size=36):
    def _paint(p: QPainter, s: int):
        p.setPen(QPen(QColor(168, 85, 247), 3))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(s * 0.15, s * 0.25, s * 0.7, s * 0.5), 6, 6)
        p.setPen(QPen(QColor(255, 255, 255, 200), 2.5))
        p.drawLine(s * 0.3, s * 0.4, s * 0.5, s * 0.4)
        p.drawLine(s * 0.3, s * 0.6, s * 0.7, s * 0.6)
    return QIcon(_mk_pixmap(size, _paint))

def _load_icon_with_fallback(label: str, path: str) -> QIcon:
    if path and os.path.exists(path):
        return QIcon(path)
    t = (label or "").lower()
    if "suno" in t or "аудіо" in t:
        return _icon_audio_v3()  # Використовуємо нову музичну іконку
    if "фото" in t or "vertex" in t:
        return _icon_photo_v2()
    if "youtube" in t or "монтаж" in t or "video" in t:
        return _icon_video_v2()
    if "планер" in t:
        return _icon_planner_v2()
    if "autofill" in t:
        return _icon_autofill_v2()
    return QIcon()

def _create_locked_icon(base_icon: QIcon) -> QIcon:
    pixmap = base_icon.pixmap(QSize(36, 36))
    p = QPainter(pixmap)
    p.setCompositionMode(QPainter.CompositionMode_SourceIn)
    p.fillRect(pixmap.rect(), QColor(128, 128, 128, 180))
    p.setCompositionMode(QPainter.CompositionMode_SourceOver)
    pen = QPen(Qt.white)
    pen.setWidth(2)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(22, 22, 12, 10, 2, 2)
    p.drawArc(20, 16, 16, 14, 0 * 16, 180 * 16)
    p.end()
    return QIcon(pixmap)

class SideMenuWidget(QWidget):
    def __init__(self, menu: QListWidget, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Додаємо великий логотип в меню
        self.logo = MenuLogoWidget()
        self.logo.setObjectName("menuLogoWidget")
        layout.addWidget(self.logo)

        layout.addWidget(menu, 1)
        self.setObjectName("SideMenuContainer")

class SystemMonitorWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("systemMonitor")
        self.gpu_handle = None
        if PYNML_AVAILABLE:
            try:
                pynvml.nvmlInit()
                self.gpu_handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            except Exception as e:
                print(f"Не вдалося ініціалізувати NVML: {e}")
                self.gpu_handle = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(5)
        self.cpu_layout, self.cpu_val_label, self.cpu_name_label = self._create_stat_layout("CPU")
        self.ram_layout, self.ram_val_label, self.ram_name_label = self._create_stat_layout("RAM")
        self.gpu_layout, self.gpu_val_label, self.gpu_name_label = self._create_stat_layout("GPU")
        layout.addLayout(self.cpu_layout)
        layout.addLayout(self.ram_layout)
        layout.addLayout(self.gpu_layout)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_stats)
        self.timer.start(2000)
        self.update_stats()

    def _create_stat_layout(self, name: str):
        v_layout = QVBoxLayout()
        v_layout.setSpacing(0)
        val_label = QLabel("---")
        val_label.setObjectName("statValueLabel")
        val_label.setAlignment(Qt.AlignCenter)
        name_label = QLabel(name)
        name_label.setObjectName("statNameLabel")
        name_label.setAlignment(Qt.AlignCenter)
        v_layout.addWidget(val_label)
        v_layout.addWidget(name_label)
        return v_layout, val_label, name_label

    def update_stats(self):
        self.cpu_val_label.setText(f"{psutil.cpu_percent():.0f}%")
        self.ram_val_label.setText(f"{psutil.virtual_memory().percent:.0f}%")
        if self.gpu_handle:
            try:
                self.gpu_val_label.setText(f"{pynvml.nvmlDeviceGetUtilizationRates(self.gpu_handle).gpu:.0f}%")
            except Exception:
                self.gpu_val_label.setText("N/A")
        else:
            self.gpu_val_label.setText("N/A")

    def cleanup(self):
        if PYNML_AVAILABLE and self.gpu_handle:
            pynvml.nvmlShutdown()

# --- ВІДЖЕТ ВИБОРУ МОВИ ---
class LanguageSelectorWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("languageSelector")
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Заголовок
        title_label = QLabel("🌍 Мова програми")
        title_label.setObjectName("languageTitle")
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        # ComboBox для вибору мови
        self.language_combo = QComboBox()
        self.language_combo.setObjectName("languageCombo")
        
        # Список мов з прапорами (емодзі)
        languages = [
            "🇺🇦 Українська",
            "🇺🇸 English", 
            "🇩🇪 Deutsch",
            "🇫🇷 Français",
            "🇪🇸 Español",
            "🇮🇹 Italiano",
            "🇵🇹 Português",
            "🇵🇱 Polski",
            "🇯🇵 日本語",
            "🇨🇳 中文"
        ]
        
        self.language_combo.addItems(languages)
        self.language_combo.currentTextChanged.connect(self.on_language_changed)
        layout.addWidget(self.language_combo)

        # Інформація про вибір
        info_label = QLabel("Мова зміниться після перезапуску")
        info_label.setObjectName("languageInfo")
        info_label.setAlignment(Qt.AlignCenter)
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

    def on_language_changed(self, language):
        print(f"Обрана мова: {language}")

class MainWindow(QMainWindow):
    def __init__(self, app, license_info=None):
        super().__init__()
        self.app = app
        self.license_info = license_info

        self.setWindowIcon(QIcon(_get_logo_pixmap()))
        self.setWindowTitle(f"VOIKAN RECORDS v{APP_VERSION}")
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.screen_dpi = self.screen().logicalDotsPerInch() if self.screen() else 96.0
        self.dpi_scale = max(1.0, self.screen_dpi / 96.0)
        self._apply_initial_geometry()
        self._base_point_size = BASE_APP_POINT_SIZE
        self._ui_scale = 1.0 * self.dpi_scale
        self._running, self._progress_val, self._progress_lbl = defaultdict(bool), defaultdict(int), defaultdict(str)

        self.menu = QListWidget()
        self.menu.setObjectName("SideMenu")
        self.menu.setFrameShape(QFrame.NoFrame)
        self.menu.setIconSize(QSize(36, 36))  # Збільшено розмір іконок
        self.menu.setSpacing(8)  # Збільшено відстань між елементами
        self.menu.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.menu.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.menu.setItemDelegate(GlassItemDelegate(self.menu))
        self.menu.setMouseTracking(True)
        self.sidebar = SideMenuWidget(self.menu)

        self.page_audio = AudioPage()
        self.page_photo = PhotoPage()
        self.page_videos = self._make_video_tabs()
        self.page_planner = PlannerTab()
        self.page_autofill = AutoFillTab()
        if hasattr(self.page_audio, 'set_host'):
            self.page_audio.set_host(self)

        self.original_icons = {}
        menu_items = [
            ("Аудіо", "", self.page_audio),
            ("Фото", "", self.page_photo),
            ("Монтаж", "", self.page_videos),
            ("Планер", "", self.page_planner),
            ("AutoFill", "", self.page_autofill),
        ]

        self.pages = QStackedWidget()
        self.pages.setObjectName("mainContentStack")
        for label, icon_path, widget in menu_items:
            icon = _load_icon_with_fallback(label, icon_path)
            self.original_icons[label] = icon
            item = QListWidgetItem(icon, label)
            item.setSizeHint(QSize(240, 70))  # Збільшено розмір пунктів меню
            self.menu.addItem(item)
            self.pages.addWidget(widget)

        self.menu.currentRowChanged.connect(self._switch_page)
        self.ctrl_panel = self._make_control_panel()

        # --- Структура головного віджета ---
        self.central_container = QWidget()
        self.central_container.setObjectName("centralContainer")
        main_layout = QVBoxLayout(self.central_container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.title_bar = CustomTitleBar(self)
        if hasattr(self.title_bar, 'set_main_widget'):
            self.title_bar.set_main_widget(self.central_container)

        # Виправлення згортання вікна
        if hasattr(self.title_bar, 'minimizeClicked'):
            self.title_bar.minimizeClicked.connect(self.showMinimized)

        # Кнопка "Змінити ПК"
        self.change_pc_button = QPushButton("Змінити ПК")
        self.change_pc_button.setToolTip("Натисніть, якщо ви перенесли програму на новий комп'ютер")
        self.change_pc_button.clicked.connect(self.handle_change_pc)
        self.change_pc_button.setObjectName("changePcButton")
        if hasattr(self.title_bar, 'add_widget_to_right'):
            self.title_bar.add_widget_to_right(self.change_pc_button)

        # Бейдж ліцензії
        self.license_badge = QLabel("")
        self.license_badge.setObjectName("licenseBadge")
        self.license_badge.setAlignment(Qt.AlignCenter)
        self.license_badge.setMinimumHeight(26)
        self.license_badge.setStyleSheet(
            """
            #licenseBadge {
                padding: 3px 10px;
                border-radius: 12px;
                border: 1px solid rgba(255,255,255,0.18);
                background: rgba(255,255,255,0.06);
                color: #EAF8FF;
                font-weight: 700;
                letter-spacing: .3px;
            }
            """
        )
        self._badge_shadow = QGraphicsDropShadowEffect(self)
        self._badge_shadow.setBlurRadius(24)
        self._badge_shadow.setOffset(0, 0)
        self._badge_shadow.setColor(QColor(0, 0, 0, 0))
        self.license_badge.setGraphicsEffect(self._badge_shadow)
        if hasattr(self.title_bar, 'add_widget_to_right'):
            self.title_bar.add_widget_to_right(self.license_badge)

        content_widget = QWidget()
        content_layout = QHBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        content_layout.addWidget(self.sidebar)
        content_layout.addWidget(self.pages, 1)
        content_layout.addWidget(self.ctrl_panel)

        # --- Футер ---
        self.status_bar = QStatusBar()

        footer_widget = QWidget()
        footer_layout = QHBoxLayout(footer_widget)
        footer_layout.setContentsMargins(10, 0, 5, 0)
        footer_layout.setSpacing(6)

        copyright_icon_label = QLabel()
        copyright_icon_label.setPixmap(_icon_copyright().pixmap(QSize(14, 14)))

        current_year = datetime.now().year
        footer_text_label = QLabel(f"VOIKAN RECORDS v{APP_VERSION}    {current_year} All rights reserved.")
        footer_text_label.setObjectName("footerTextLabel")

        footer_layout.addWidget(copyright_icon_label)
        footer_layout.addWidget(footer_text_label)
        self.status_bar.addWidget(footer_widget)

        self.license_status_label = QLabel()
        self.license_status_label.setObjectName("licenseStatusLabel")
        self.status_bar.addPermanentWidget(self.license_status_label)

        main_layout.addWidget(self.title_bar)
        main_layout.addWidget(content_widget, 1)
        main_layout.addWidget(self.status_bar)

        self.setCentralWidget(self.central_container)

        self.menu.setCurrentRow(0)
        self._apply_scale(self._ui_scale)
        if hasattr(self.page_autofill, "sig_log"):
            self.page_autofill.sig_log.connect(lambda text: self.log(self.page_autofill, text))
        if hasattr(self.page_autofill, "sig_progress"):
            self.page_autofill.sig_progress.connect(lambda val, lbl="AutoFill": self.set_progress(self.page_autofill, int(val), lbl))
        if hasattr(self.page_autofill, "sig_running"):
            self.page_autofill.sig_running.connect(lambda running: self.set_running(self.page_autofill, bool(running)))
        if not self._apply_qss_theme("dark_modern.qss"):
            print("ПОПЕРЕДЖЕННЯ: Файл стилів 'dark_modern.qss' не знайдено.")

        self.license_check_timer = QTimer(self)
        self.license_check_timer.timeout.connect(self.update_license_status)
        self.license_check_timer.start(3600 * 1000)
        self.apply_license_restrictions()

    def _make_control_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("controlPanel")
        v_lay = QVBoxLayout(panel)
        v_lay.setContentsMargins(12, 12, 12, 12)
        v_lay.setSpacing(12)

        # Додаємо блок вибору мови вгорі
        self.language_selector = LanguageSelectorWidget()
        v_lay.addWidget(self.language_selector)

        gb_monitor = QGroupBox("Монітор ресурсів")
        v_monitor_layout = QVBoxLayout(gb_monitor)
        self.monitor_widget = SystemMonitorWidget()
        v_monitor_layout.addWidget(self.monitor_widget)

        gb_controls = QGroupBox("Керування процесом")
        v_controls_layout = QVBoxLayout(gb_controls)
        self.btn_start = AnimatedPushButton("РОЗПОЧАТИ")
        self.btn_start.setObjectName("startBtn")
        self.btn_stop = AnimatedPushButton("ЗУПИНИТИ")
        self.btn_stop.setObjectName("stopBtn")
        self.btn_stop.setEnabled(False)
        self.btn_start.clicked.connect(self._on_start_clicked)
        self.btn_stop.clicked.connect(self._on_stop_clicked)
        h_btn_layout = QHBoxLayout()
        h_btn_layout.addWidget(self.btn_start)
        h_btn_layout.addWidget(self.btn_stop)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        v_controls_layout.addWidget(self.progress)
        v_controls_layout.addLayout(h_btn_layout)

        gb_logs = QGroupBox("Логи")
        v_logs_layout = QVBoxLayout(gb_logs)
        self.logs = QTextEdit()
        self.logs.setReadOnly(True)
        self.btn_clear_logs = AnimatedPushButton("Очистити логи")
        self.btn_clear_logs.setObjectName("clearLogsBtn")
        self.btn_clear_logs.clicked.connect(self.logs.clear)
        v_logs_layout.addWidget(self.logs, 1)
        v_logs_layout.addWidget(self.btn_clear_logs)

        v_lay.addWidget(gb_monitor)
        v_lay.addWidget(gb_controls)
        v_lay.addWidget(gb_logs, 1)

        panel.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        return panel

    # Решта методів залишаються без змін
    def handle_change_pc(self):
        reply = QMessageBox.question(
            self,
            'Підтвердження зміни ПК',
            "Ви впевнені, що хочете прив'язати вашу ліцензію до цього комп'ютера?\nСтарий комп'ютер буде деактивовано.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            print("Починаємо процес зміни HWID...")
            user_email = self.license_info.get('email')
            new_hwid = get_machine_id()
            success = update_hwid_in_sheet(user_email, new_hwid)
            if success:
                self.license_info['hwid'] = new_hwid
                save_local_license(self.license_info)
                QMessageBox.information(self, 'Успіх', "Ліцензію успішно прив'язано до цього комп'ютера! Будь ласка, перезапустіть програму.")
                self.close()
            else:
                QMessageBox.critical(self, 'Помилка', 'Не вдалося оновити дані на сервері. Спробуйте пізніше.')

    def update_license_status(self):
        print("Перевірка статусу ліцензії...")
        user_email = self.license_info.get('email') if self.license_info else None
        if not user_email:
            return
        new_license_info = get_license_status(user_email)
        if new_license_info:
            new_license_info['email'] = user_email
            self.license_info = new_license_info
            save_local_license(self.license_info)
            print(f"Статус ліцензії оновлено: {self.license_info.get('plan')}")
            self.apply_license_restrictions()
        else:
            print("Не вдалося оновити статус ліцензії.")

    def apply_license_restrictions(self):
        if not self.license_info:
            return
        plan = self.license_info.get('plan', 'unknown')
        features = self.license_info.get('features', {})
        access_granted = self.license_info.get('access_granted', False)

        feature_map = {
            "Аудіо": features.get("suno", False),
            "Фото": features.get("vertex", False),
            "Монтаж": features.get("montage", False),
            "Планер": features.get("planner", False),
            "AutoFill": features.get("autofill", False),
        }
        for menu_text, is_enabled in feature_map.items():
            try:
                item = self.menu.findItems(menu_text, Qt.MatchExactly)[0]
                original_icon = self.original_icons[menu_text]
                if is_enabled:
                    item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                    item.setIcon(original_icon)
                    item.setToolTip("")
                else:
                    item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
                    item.setIcon(_create_locked_icon(original_icon))
                    item.setToolTip("Ця функція недоступна у вашому тарифі. Придбайте вищий план.")
            except (IndexError, KeyError) as e:
                print(f"Попередження: не вдалося обробити елемент меню '{menu_text}': {e}")

        self.ctrl_panel.setEnabled(access_granted)
        plan_display_name = plan.replace('_', ' ').title()
        status_text = f"Тариф: {plan_display_name}"
        if plan == 'pro':
            status_text = f"✨ Тариф: Pro"
        elif plan == 'trial':
            expires_on = self.license_info.get('expires_on')
            if expires_on and datetime.now() < expires_on:
                time_left = expires_on - datetime.now()
                days, hours = time_left.days, time_left.seconds // 3600
                status_text = f"⚠️ Trial: Залишилось {days} дн."
            else:
                status_text = "❌ Тріал закінчився"
        elif plan == 'trial_expired' or plan == 'blocked' or not access_granted:
            status_text = "❌ Ліцензія неактивна"
        self.license_status_label.setText(status_text)

        self.license_status_label.setProperty("plan", plan)
        self.license_status_label.style().unpolish(self.license_status_label)
        self.license_status_label.style().polish(self.license_status_label)

        def _set_badge(text: str, bg_css: str, glow_color: QColor):
            self.license_badge.setText(text)
            self.license_badge.setStyleSheet(
                f"""
                #licenseBadge {{
                    padding: 3px 10px;
                    border-radius: 12px;
                    border: 1px solid rgba(255,255,255,0.18);
                    background: {bg_css};
                    color: white;
                    font-weight: 800;
                    letter-spacing: .3px;
                }}
                """
            )
            self._badge_shadow.setColor(glow_color)

        if plan == 'pro' and access_granted:
            _set_badge("PRO", "rgba(0, 180, 120, 0.25)", QColor(0, 255, 170, 200))
        elif plan == 'trial' and access_granted:
            _set_badge("TRIAL", "rgba(255, 200, 0, 0.22)", QColor(255, 210, 0, 170))
        else:
            _set_badge("INACTIVE", "rgba(255, 70, 70, 0.22)", QColor(255, 80, 80, 190))

        if hasattr(self.title_bar, 'set_title'):
            self.title_bar.set_title(f"VOIKAN RECORDS - [{plan.upper()}]")

        if plan == 'pro' and access_granted:
            eff = QGraphicsDropShadowEffect(self)
            eff.setBlurRadius(16)
            eff.setOffset(0, 0)
            eff.setColor(QColor(0, 255, 170, 140))
            self.license_status_label.setGraphicsEffect(eff)
        else:
            self.license_status_label.setGraphicsEffect(None)

    def _on_check_for_updates_clicked(self):
        QMessageBox.information(self, "Оновлення", "Наразі ви використовуєте останню версію.")

    def changeEvent(self, event):
        if event.type() == QEvent.WindowStateChange and hasattr(self, 'title_bar'):
            self.title_bar.update_window_state()
        super().changeEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        if hasattr(self, 'monitor_widget'):
            self.monitor_widget.cleanup()
        if REMEMBER_LAST_SIZE and not WINDOW_FIXED:
            s = QSettings(ORG_NAME, APP_NAME)
            s.setValue("win/width", self.width())
            s.setValue("win/height", self.height())
        super().closeEvent(event)

    def _make_video_tabs(self):
        tabs = QTabWidget()
        vp, sp = VideoPage(), ShortsPage()
        if hasattr(vp, "set_host"):
            vp.set_host(self)
        if hasattr(sp, "set_host"):
            sp.set_host(self)
        tabs.addTab(vp, _load_icon_with_fallback("video", ""), "Відео")
        tabs.addTab(sp, _load_icon_with_fallback("video", ""), "Shorts")
        tabs.currentChanged.connect(lambda: self._sync_right_panel_for(self._current_page()))
        return tabs

    def _apply_initial_geometry(self):
        base_w, base_h = int(WINDOW_WIDTH), int(WINDOW_HEIGHT)
        if WINDOW_MIN_W or WINDOW_MIN_H:
            self.setMinimumSize(int(WINDOW_MIN_W), int(WINDOW_MIN_H))
        s = QSettings(ORG_NAME, APP_NAME)
        w, h = (s.value("win/width", type=int), s.value("win/height", type=int)) if REMEMBER_LAST_SIZE else (None, None)
        self.resize(w, h) if w and h else self.resize(base_w, base_h)
        if WINDOW_FIXED:
            self.setFixedSize(self.size())

    def resizeEvent(self, e):
        super().resizeEvent(e)
        sw, sh = self.width() / DESIGN_WIDTH, self.height() / DESIGN_HEIGHT
        scale = max(MIN_SCALE, min(MAX_SCALE, min(sw, sh)))
        if abs(scale - self._ui_scale) >= 0.02:
            self._ui_scale = scale
            self._apply_scale(self._ui_scale)

    def _apply_qss_theme(self, qss_filename: str) -> bool:
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            path = os.path.join(script_dir, qss_filename)
            if not os.path.exists(path):
                path = os.path.join(script_dir, '..', 'assets', qss_filename)

            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    self.setStyleSheet(f.read())
                return True
        except Exception as e:
            print(f"ПОМИЛКА завантаження теми: {e}")
        return False

    def _apply_scale(self, scale: float):
        f = self.font()
        f.setPointSizeF(max(MIN_APP_POINT_SIZE, BASE_APP_POINT_SIZE * scale))
        self.setFont(f)
        self.sidebar.setFixedWidth(int(LEFT_SIDEBAR_BASE_W * scale))
        self.ctrl_panel.setFixedWidth(int(RIGHT_PANEL_BASE_W * scale))
        h = max(32, int(BTN_H_BASE * scale))
        for btn in (self.btn_start, self.btn_stop, self.btn_clear_logs):
            btn.setMinimumHeight(h)
        self.progress.setFixedHeight(max(6, int(PROGRESS_H_BASE * scale)))
        for i in range(self.menu.count()):
            self.menu.item(i).setSizeHint(QSize(240, max(60, int(70 * scale))))  # Оновлені розміри
        for i in range(self.pages.count()):
            page = self.pages.widget(i)
            if hasattr(page, "apply_scale"):
                page.apply_scale(scale)

    def _current_page(self):
        w = self.pages.currentWidget()
        return w.currentWidget() if isinstance(w, QTabWidget) and w.currentWidget() is not None else w

    def _switch_page(self, index: int):
        self.pages.setCurrentIndex(index)
        self._sync_right_panel_for(self._current_page())

    def _sync_right_panel_for(self, page):
        if not page:
            return
        running, val, lbl = self._running[page], self._progress_val[page], self._progress_lbl[page]
        self.btn_start.setEnabled(not running)
        self.btn_stop.setEnabled(running)
        self.progress.setValue(val)
        self.progress.setFormat(f"{lbl}: {val}%" if lbl else f"{val}%")

    def _on_start_clicked(self):
        page = self._current_page()
        if hasattr(page, "handle_start"):
            page.handle_start(True)
        self.set_running(page, True)
        self.log(page, "▶ Процес розпочато")

    def _on_stop_clicked(self):
        page = self._current_page()
        if hasattr(page, "handle_stop"):
            page.handle_stop()
        self.set_running(page, False)
        self.log(page, "■ Процес зупинено")

    def log(self, page, text: str):
        tag = {AudioPage: "Аудіо", PhotoPage: "Фото", VideoPage: "Відео", ShortsPage: "Відео", PlannerTab: "Планер", AutoFillTab: "AutoFill"}.get(type(page), "Система")
        timestamp = datetime.now().strftime('%H:%M:%S')
        self.logs.append(f"<font color='#8A97A8'>[{timestamp} | {tag}]</font> {text}")

    def set_progress(self, page, value: int, label: str = ""):
        self._progress_val[page] = max(0, min(100, value))
        self._progress_lbl[page] = label
        if page == self._current_page():
            self._sync_right_panel_for(page)

    def set_running(self, page, running: bool):
        self._running[page] = running
        if page == self._current_page():
            self._sync_right_panel_for(page)