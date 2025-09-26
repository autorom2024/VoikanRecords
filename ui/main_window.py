# ui/main_window.py
# -*- coding: utf-8 -*-
from __future__ import annotations
from collections import defaultdict
import os
from datetime import datetime
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QStackedWidget, QGroupBox, QProgressBar, QTextEdit, QSizePolicy, QListWidgetItem, QTabWidget, QFrame, QLabel, QStatusBar, QMessageBox, QPushButton)
from PySide6.QtCore import Qt, QSettings, QSize, QRectF, QPointF, QEvent, QTimer
from PySide6.QtGui import (QCloseEvent, QIcon, QPainter, QPixmap, QPainterPath, QColor, QPen, QFont, QLinearGradient, QRadialGradient, QConicalGradient)
from auth_logic import get_license_status, update_hwid_in_sheet, save_local_license, get_machine_id

try:
    from .custom_title_bar import CustomTitleBar
except ImportError:
    class CustomTitleBar(QWidget):
        def add_widget_to_right(self, widget): pass
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

APP_VERSION = "1.1.0"
WINDOW_WIDTH, WINDOW_HEIGHT = 1360, 800
REMEMBER_LAST_SIZE, WINDOW_FIXED = True, False
WINDOW_MIN_W, WINDOW_MIN_H = 980, 640
DESIGN_WIDTH, DESIGN_HEIGHT = 1360, 760
MIN_SCALE, MAX_SCALE = 0.85, 1.70
LEFT_SIDEBAR_BASE_W, RIGHT_PANEL_BASE_W = 260, 320
BASE_APP_POINT_SIZE, MIN_APP_POINT_SIZE = 10.0, 12.0
BTN_H_BASE, PROGRESS_H_BASE = 34, 18
ORG_NAME, APP_NAME = "Voikan", "MultimediaPanel"
os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
os.environ["QT_SCALE_FACTOR"] = "1"
os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"

def _mk_pixmap(size: int, paint_fn):
    pm = QPixmap(size, size); pm.fill(Qt.transparent)
    p = QPainter(pm); p.setRenderHint(QPainter.Antialiasing, True); paint_fn(p, size); p.end()
    return pm
def _icon_voikan_logo(size=32):
    def _paint(p: QPainter, s: int):
        grad = QLinearGradient(0, 0, s, s); grad.setColorAt(0.0, QColor("#8A2BE2")); grad.setColorAt(1.0, QColor("#4169E1"))
        p.setPen(Qt.NoPen); p.setBrush(grad); p.drawEllipse(0, 0, s, s)
        font = QFont("Segoe UI", -1, QFont.Bold); font.setPixelSize(int(s * 0.6))
        p.setFont(font); p.setPen(QColor("white")); p.drawText(QRectF(0, 0, s, s), Qt.AlignCenter, "V")
    return QIcon(_mk_pixmap(size, _paint))
def _icon_audio_v2(size=36):
    def _paint(p: QPainter, s: int):
        p.setPen(Qt.NoPen); p.setBrush(QColor(30, 30, 35)); p.drawEllipse(0, 0, s, s)
        grad = QRadialGradient(s/2, s/2, s/3); grad.setColorAt(0, QColor("#B070FF")); grad.setColorAt(1, QColor("#8A2BE2"))
        p.setBrush(grad); p.drawEllipse(s*0.2, s*0.2, s*0.6, s*0.6)
        p.setBrush(QColor(20,20,25)); p.drawEllipse(s*0.4, s*0.4, s*0.2, s*0.2)
        p.setPen(QPen(QColor(255,255,255,40), 1.0)); p.drawArc(QRectF(s*0.1, s*0.1, s*0.8, s*0.8), 45*16, 90*16)
    return QIcon(_mk_pixmap(size, _paint))
def _icon_photo_v2(size=36):
    def _paint(p: QPainter, s: int):
        p.setPen(Qt.NoPen); p.setBrush(QColor(30, 35, 35)); p.drawRoundedRect(QRectF(s*0.05, s*0.2, s*0.9, s*0.6), 5, 5)
        grad = QConicalGradient(s/2, s/2, 90); grad.setColorAt(0, Qt.cyan); grad.setColorAt(0.5, Qt.magenta); grad.setColorAt(1, Qt.cyan)
        p.setBrush(grad); p.drawEllipse(s*0.25, s*0.25, s*0.5, s*0.5)
        p.setBrush(QColor(20,20,20)); p.drawEllipse(s*0.4, s*0.4, s*0.2, s*0.2)
    return QIcon(_mk_pixmap(size, _paint))
def _icon_video_v2(size=36):
    def _paint(p: QPainter, s: int):
        p.setPen(Qt.NoPen); p.setBrush(QColor("#FF4848")); p.drawRoundedRect(QRectF(s*0.1, s*0.2, s*0.8, s*0.6), s*0.15, s*0.15)
        path = QPainterPath(); path.moveTo(s*0.4, s*0.35); path.lineTo(s*0.7, s*0.5); path.lineTo(s*0.4, s*0.65); path.closeSubpath()
        p.setBrush(QColor("white")); p.drawPath(path)
    return QIcon(_mk_pixmap(size, _paint))
def _icon_planner_v2(size=36):
    def _paint(p: QPainter, s: int):
        p.setPen(Qt.NoPen); p.setBrush(QColor(60, 60, 90)); p.drawRoundedRect(QRectF(s*0.1, s*0.15, s*0.8, s*0.7), 4, 4)
        p.setBrush(QColor(200, 210, 255)); p.drawRect(s*0.25, s*0.4, s*0.5, s*0.35)
        p.setPen(QPen(QColor(60, 60, 90), 2.0)); p.drawLine(s*0.25, s*0.58, s*0.75, s*0.58)
    return QIcon(_mk_pixmap(size, _paint))
def _icon_autofill_v2(size=36):
    def _paint(p: QPainter, s: int):
        p.setPen(QPen(QColor(168, 85, 247), 3)); p.setBrush(Qt.NoBrush); p.drawRoundedRect(QRectF(s*0.15, s*0.25, s*0.7, s*0.5), 6, 6)
        p.setPen(QPen(QColor(255,255,255,200), 2.5)); p.drawLine(s*0.3, s*0.4, s*0.5, s*0.4)
        p.drawLine(s*0.3, s*0.6, s*0.7, s*0.6)
    return QIcon(_mk_pixmap(size, _paint))
def _load_icon_with_fallback(label: str, path: str) -> QIcon:
    if path and os.path.exists(path): return QIcon(path)
    t = (label or "").lower()
    if "suno" in t or "аудіо" in t: return _icon_audio_v2()
    if "фото" in t or "vertex" in t: return _icon_photo_v2()
    if "youtube" in t or "монтаж" in t: return _icon_video_v2()
    if "планер" in t: return _icon_planner_v2()
    if "autofill" in t: return _icon_autofill_v2()
    return QIcon()
def _create_locked_icon(base_icon: QIcon) -> QIcon:
    pixmap = base_icon.pixmap(QSize(36, 36))
    p = QPainter(pixmap)
    p.setCompositionMode(QPainter.CompositionMode_SourceIn)
    p.fillRect(pixmap.rect(), QColor(128, 128, 128, 180))
    p.setCompositionMode(QPainter.CompositionMode_SourceOver)
    pen = QPen(Qt.white); pen.setWidth(2)
    p.setPen(pen); p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(22, 22, 12, 10, 2, 2) 
    p.drawArc(20, 16, 16, 14, 0 * 16, 180 * 16)
    p.end()
    return QIcon(pixmap)
class SideMenuWidget(QWidget):
    def __init__(self, menu: QListWidget, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0); layout.setSpacing(12)
        title_layout = QHBoxLayout()
        title_layout.setContentsMargins(16, 0, 16, 0)
        title = QLabel("VOIKAN RECORDS")
        title.setObjectName("appTitleLabel")
        title_layout.addWidget(title); title_layout.addStretch(1)
        layout.addLayout(title_layout); layout.addWidget(menu, 1)
        self.setObjectName("SideMenuContainer")
        self.setStyleSheet("QWidget#SideMenuContainer { background: transparent; }")
class SystemMonitorWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("systemMonitor")
        self.gpu_handle = None
        if PYNML_AVAILABLE:
            try:
                pynvml.nvmlInit()
                self.gpu_handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            except Exception as e: print(f"Не вдалося ініціалізувати NVML: {e}"); self.gpu_handle = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5); layout.setSpacing(5)
        self.cpu_layout, self.cpu_val_label, self.cpu_name_label = self._create_stat_layout("CPU")
        self.ram_layout, self.ram_val_label, self.ram_name_label = self._create_stat_layout("RAM")
        self.gpu_layout, self.gpu_val_label, self.gpu_name_label = self._create_stat_layout("GPU")
        layout.addLayout(self.cpu_layout); layout.addLayout(self.ram_layout); layout.addLayout(self.gpu_layout)
        self.timer = QTimer(self); self.timer.timeout.connect(self.update_stats); self.timer.start(2000)
        self.update_stats()
    def _create_stat_layout(self, name: str):
        v_layout = QVBoxLayout(); v_layout.setSpacing(0)
        val_label = QLabel("---"); val_label.setObjectName("statValueLabel"); val_label.setAlignment(Qt.AlignCenter)
        name_label = QLabel(name); name_label.setObjectName("statNameLabel"); name_label.setAlignment(Qt.AlignCenter)
        v_layout.addWidget(val_label); v_layout.addWidget(name_label)
        return v_layout, val_label, name_label
    def update_stats(self):
        self.cpu_val_label.setText(f"{psutil.cpu_percent():.0f}%")
        self.ram_val_label.setText(f"{psutil.virtual_memory().percent:.0f}%")
        if self.gpu_handle:
            try: self.gpu_val_label.setText(f"{pynvml.nvmlDeviceGetUtilizationRates(self.gpu_handle).gpu:.0f}%")
            except Exception: self.gpu_val_label.setText("N/A")
        else: self.gpu_val_label.setText("N/A")
    def cleanup(self):
        if PYNML_AVAILABLE and self.gpu_handle: pynvml.nvmlShutdown()
class MainWindow(QMainWindow):
    def __init__(self, app, license_info=None):
        super().__init__()
        self.app = app
        self.license_info = license_info
        
        self.setWindowIcon(_icon_voikan_logo())
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.screen_dpi = self.screen().logicalDotsPerInch() if self.screen() else 96.0
        self.dpi_scale = max(1.0, self.screen_dpi / 96.0)
        self._apply_initial_geometry()
        self._base_point_size = BASE_APP_POINT_SIZE
        self._ui_scale = 1.0 * self.dpi_scale
        self._running, self._progress_val, self._progress_lbl = defaultdict(bool), defaultdict(int), defaultdict(str)

        self.menu = QListWidget()
        self.menu.setObjectName("SideMenu"); self.menu.setFrameShape(QFrame.NoFrame)
        self.menu.setUniformItemSizes(True); self.menu.setIconSize(QSize(36, 36)); self.menu.setSpacing(6)
        self.menu.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff); self.menu.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.menu.setItemDelegate(GlassItemDelegate(self.menu)); self.menu.setMouseTracking(True)
        self.sidebar = SideMenuWidget(self.menu)

        self.page_audio = AudioPage(); self.page_photo = PhotoPage(); self.page_videos = self._make_video_tabs()
        self.page_planner = PlannerTab(); self.page_autofill = AutoFillTab()
        if hasattr(self.page_audio, 'set_host'): self.page_audio.set_host(self)

        self.original_icons = {}
        menu_items = [("Аудіо Suno", "", self.page_audio), ("Фото Vertex", "", self.page_photo),
                      ("Монтаж YouTube", "", self.page_videos), ("YT Планер", "", self.page_planner),
                      ("YT AutoFill", "", self.page_autofill)]
        
        self.pages = QStackedWidget()
        for label, icon_path, widget in menu_items:
            icon = _load_icon_with_fallback(label, icon_path)
            self.original_icons[label] = icon
            item = QListWidgetItem(icon, label); item.setSizeHint(QSize(220, 68))
            self.menu.addItem(item); self.pages.addWidget(widget)

        self.menu.currentRowChanged.connect(self._switch_page)
        self.ctrl_panel = self._make_control_panel()

        main_widget = QWidget(); main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0); main_layout.setSpacing(0)
        
        self.title_bar = CustomTitleBar(self)
        self.change_pc_button = QPushButton("Змінити ПК")
        self.change_pc_button.setToolTip("Натисніть, якщо ви перенесли програму на новий комп'ютер")
        self.change_pc_button.clicked.connect(self.handle_change_pc)
        if hasattr(self.title_bar, 'add_widget_to_right'):
            self.title_bar.add_widget_to_right(self.change_pc_button)
        main_layout.addWidget(self.title_bar)
        
        content_widget = QWidget(); content_layout = QHBoxLayout(content_widget)
        content_layout.setContentsMargins(12, 12, 12, 12); content_layout.setSpacing(12)
        content_layout.addWidget(self.sidebar); content_layout.addWidget(self.pages, 1); content_layout.addWidget(self.ctrl_panel)
        main_layout.addWidget(content_widget)
        self.setCentralWidget(main_widget)
        
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.license_status_label = QLabel()
        self.status_bar.addPermanentWidget(self.license_status_label)

        self.menu.setCurrentRow(0)
        self._apply_scale(self._ui_scale)
        if hasattr(self.page_autofill, "sig_log"): self.page_autofill.sig_log.connect(lambda text: self.log(self.page_autofill, text))
        if hasattr(self.page_autofill, "sig_progress"): self.page_autofill.sig_progress.connect(lambda val, lbl="AutoFill": self.set_progress(self.page_autofill, int(val), lbl))
        if hasattr(self.page_autofill, "sig_running"): self.page_autofill.sig_running.connect(lambda running: self.set_running(self.page_autofill, bool(running)))
        if not self._apply_qss_theme("dark_modern.qss"): print("ПОПЕРЕДЖЕННЯ: Файл стилів 'dark_modern.qss' не знайдено.")

        self.license_check_timer = QTimer(self)
        self.license_check_timer.timeout.connect(self.update_license_status)
        self.license_check_timer.start(3600 * 1000)
        self.apply_license_restrictions()

    def handle_change_pc(self):
        reply = QMessageBox.question(self, 'Підтвердження зміни ПК', "Ви впевнені, що хочете прив'язати вашу ліцензію до цього комп'ютера?\nСтарий комп'ютер буде деактивовано.", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            print("Починаємо процес зміни HWID...")
            user_email = self.license_info.get('email')
            new_hwid = get_machine_id()
            success = update_hwid_in_sheet(user_email, new_hwid)
            if success:
                self.license_info['hwid'] = new_hwid
                save_local_license(self.license_info)
                QMessageBox.information(self, 'Успіх', 'Ліцензію успішно прив\'язано до цього комп\'ютера! Будь ласка, перезапустіть програму.')
                self.close()
            else:
                QMessageBox.critical(self, 'Помилка', 'Не вдалося оновити дані на сервері. Спробуйте пізніше.')

    def update_license_status(self):
        print("Перевірка статусу ліцензії...")
        user_email = self.license_info.get('email') if self.license_info else None
        if not user_email: return
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
        if not self.license_info: return
        plan = self.license_info.get('plan', 'unknown')
        features = self.license_info.get('features', {})
        access_granted = self.license_info.get('access_granted', False)

        feature_map = {
            "Аудіо Suno": features.get("suno", False),
            "Фото Vertex": features.get("vertex", False),
            "Монтаж YouTube": features.get("montage", False),
            "YT Планер": features.get("planner", False),
            "YT AutoFill": features.get("autofill", False)
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
        
        status_text = ""
        plan_display_name = plan.replace('_', ' ').title()
        if plan == 'pro':
            status_text = f"✨ Тариф: Pro. Усі функції доступні."
            self.license_status_label.setStyleSheet("color: #00E676;")
        elif plan == 'trial':
            expires_on = self.license_info.get('expires_on')
            if expires_on and datetime.now() < expires_on:
                time_left = expires_on - datetime.now()
                days, hours = time_left.days, time_left.seconds // 3600
                status_text = f"⚠️ Тариф: Trial. Залишилось: {days} дн. {hours} год."
                self.license_status_label.setStyleSheet("color: #FFC107;")
            else:
                 status_text = "❌ Тріал закінчився. Будь ласка, оберіть тариф."
                 self.license_status_label.setStyleSheet("color: #F44336;")
        elif plan == 'trial_expired':
            status_text = "❌ Тріал закінчився. Будь ласка, оберіть тариф."
            self.license_status_label.setStyleSheet("color: #F44336;")
        elif plan == 'blocked' or not access_granted:
            status_text = "❌ Ліцензія неактивна або заблокована."
            self.license_status_label.setStyleSheet("color: #F44336;")
        else:
            status_text = f"Тариф: {plan_display_name}"
            self.license_status_label.setStyleSheet("color: #FFFFFF;")
            
        self.license_status_label.setText(status_text)
        self.setWindowTitle(f"VOIKAN RECORDS v{APP_VERSION} - [{plan.upper()}]")

    def _on_check_for_updates_clicked(self):
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(self, "Оновлення", "Наразі ви використовуєте останню версію.")

    def changeEvent(self, event):
        if event.type() == QEvent.WindowStateChange and hasattr(self, 'title_bar'): self.title_bar.update_window_state()
        super().changeEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        if hasattr(self, 'monitor_widget'): self.monitor_widget.cleanup()
        if REMEMBER_LAST_SIZE and not WINDOW_FIXED:
            s = QSettings(ORG_NAME, APP_NAME)
            s.setValue("win/width", self.width()); s.setValue("win/height", self.height())
        super().closeEvent(event)

    def _make_control_panel(self) -> QWidget:
        panel = QWidget(); v_lay = QVBoxLayout(panel); v_lay.setContentsMargins(10, 10, 10, 10); v_lay.setSpacing(12)
        gb1 = QGroupBox("Керування"); v1 = QVBoxLayout(gb1)
        self.monitor_widget = SystemMonitorWidget(); v1.addWidget(self.monitor_widget)
        self.btn_start = AnimatedPushButton("старт"); self.btn_start.setObjectName("startBtn")
        self.btn_stop = AnimatedPushButton("стоп"); self.btn_stop.setObjectName("stopBtn"); self.btn_stop.setEnabled(False)
        self.btn_start.clicked.connect(self._on_start_clicked); self.btn_stop.clicked.connect(self._on_stop_clicked)
        v1.addWidget(self.btn_start); v1.addWidget(self.btn_stop)
        self.progress = QProgressBar(); self.progress.setRange(0, 100); v1.addWidget(self.progress)
        v_lay.addWidget(gb1)
        gb2 = QGroupBox("Логи"); v2 = QVBoxLayout(gb2)
        self.logs = QTextEdit(); self.logs.setReadOnly(True)
        self.btn_clear_logs = AnimatedPushButton("Очистити логи"); self.btn_clear_logs.setObjectName("clearLogsBtn")
        self.btn_clear_logs.clicked.connect(self.logs.clear)
        v2.addWidget(self.logs, 1); v2.addWidget(self.btn_clear_logs)
        v_lay.addWidget(gb2, 1)
        panel.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        return panel

    def _make_video_tabs(self):
        tabs = QTabWidget(); vp, sp = VideoPage(), ShortsPage()
        if hasattr(vp, "set_host"): vp.set_host(self)
        if hasattr(sp, "set_host"): sp.set_host(self)
        tabs.addTab(vp, _load_icon_with_fallback("video", ""), "Відео")
        tabs.addTab(sp, _load_icon_with_fallback("video", ""), "Shorts")
        tabs.currentChanged.connect(lambda: self._sync_right_panel_for(self._current_page()))
        return tabs
    
    def _apply_initial_geometry(self):
        base_w, base_h = int(WINDOW_WIDTH * self.dpi_scale), int(WINDOW_HEIGHT * self.dpi_scale)
        if WINDOW_MIN_W or WINDOW_MIN_H: self.setMinimumSize(int(WINDOW_MIN_W * self.dpi_scale), int(WINDOW_MIN_H * self.dpi_scale))
        s = QSettings(ORG_NAME, APP_NAME)
        w, h = (s.value("win/width", type=int), s.value("win/height", type=int)) if REMEMBER_LAST_SIZE else (None, None)
        self.resize(w, h) if w and h else self.resize(base_w, base_h)
        if WINDOW_FIXED: self.setFixedSize(self.size())
        
    def resizeEvent(self, e):
        super().resizeEvent(e)
        sw, sh = self.width() / max(1, DESIGN_WIDTH * self.dpi_scale), self.height() / max(1, DESIGN_HEIGHT * self.dpi_scale)
        scale = max(MIN_SCALE, min(MAX_SCALE, min(sw, sh) * self.dpi_scale))
        if abs(scale - self._ui_scale) >= 0.02: self._ui_scale = scale; self._apply_scale(self._ui_scale)
        
    def _apply_qss_theme(self, qss_filename: str) -> bool:
        try:
            path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), qss_filename)
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f: self.app.setStyleSheet(f.read())
                return True
            else:
                 path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets', qss_filename)
                 if os.path.exists(path):
                    with open(path, "r", encoding="utf-8") as f: self.app.setStyleSheet(f.read())
                    return True
        except Exception as e: print(f"ПОМИЛКА завантаження теми: {e}")
        return False
        
    def _apply_scale(self, scale: float):
        f = self.app.font(); f.setPointSizeF(max(MIN_APP_POINT_SIZE, BASE_APP_POINT_SIZE * scale)); self.app.setFont(f)
        self.menu.setFixedWidth(int(LEFT_SIDEBAR_BASE_W * scale))
        self.ctrl_panel.setFixedWidth(int(RIGHT_PANEL_BASE_W * scale))
        h = max(28, int(BTN_H_BASE * scale))
        for btn in (self.btn_start, self.btn_stop, self.btn_clear_logs): btn.setMinimumHeight(h)
        self.progress.setFixedHeight(max(12, int(PROGRESS_H_BASE * scale)))
        for i in range(self.menu.count()): self.menu.item(i).setSizeHint(QSize(220, max(56, int(68 * scale))))
        for i in range(self.pages.count()):
            page = self.pages.widget(i)
            if hasattr(page, "apply_scale"): page.apply_scale(scale)
            
    def _current_page(self): 
        w = self.pages.currentWidget()
        return w.currentWidget() if isinstance(w, QTabWidget) and w.currentWidget() is not None else w
        
    def _switch_page(self, index: int): 
        self.pages.setCurrentIndex(index)
        self._sync_right_panel_for(self._current_page())
        
    def _sync_right_panel_for(self, page):
        if not page: return
        running, val, lbl = self._running[page], self._progress_val[page], self._progress_lbl[page]
        self.btn_start.setEnabled(not running); self.btn_stop.setEnabled(running)
        self.progress.setValue(val); self.progress.setFormat(f"{lbl} — {val}%" if lbl else "%p%")
        
    def _on_start_clicked(self): 
        page = self._current_page()
        if hasattr(page, "handle_start"): page.handle_start(True)
        self.set_running(page, True); self.log(page, "▶ старт")
        
    def _on_stop_clicked(self): 
        page = self._current_page()
        if hasattr(page, "handle_stop"): page.handle_stop()
        self.set_running(page, False); self.log(page, "■ стоп")
        
    def log(self, page, text: str):
        tag = {AudioPage: "Аудіо", PhotoPage: "Фото", VideoPage: "Відео", ShortsPage: "Відео", PlannerTab: "Планер", AutoFillTab: "AutoFill"}.get(type(page), "Інше")
        self.logs.append(f"[{tag}] {text}")
        
    def set_progress(self, page, value: int, label: str = ""): 
        self._progress_val[page] = max(0, min(100, value)); self._progress_lbl[page] = label
        self._sync_right_panel_for(page)
        
    def set_running(self, page, running: bool): 
        self._running[page] = running
        self._sync_right_panel_for(page)