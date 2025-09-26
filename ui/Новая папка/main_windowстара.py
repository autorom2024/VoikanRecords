# -*- coding: utf-8 -*-
from __future__ import annotations
from collections import defaultdict
import os

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QStackedWidget,
    QGroupBox, QRadioButton, QProgressBar, QTextEdit, QSizePolicy,
    QListWidgetItem, QTabWidget, QFrame, QLabel, QGraphicsDropShadowEffect
)
from PySide6.QtCore import Qt, QSettings, QSize, QRectF, QPointF, QEvent
from PySide6.QtGui import (
    QCloseEvent, QIcon, QPainter, QPixmap, QPainterPath, QColor, QPen, QFont
)

from ui.pages.audio_page import AudioPage
from ui.pages.photo_page import PhotoPage
from ui.pages.video_page import VideoPage
from ui.pages.shorts_page import ShortsPage
from ui.pages.tab_planner import PlannerTab
from ui.pages.tab_autofill import AutoFillTab

from .glass_item_delegate import GlassItemDelegate
from .animated_push_button import AnimatedPushButton

# Налаштування масштабування
WINDOW_WIDTH = 1360
WINDOW_HEIGHT = 800
REMEMBER_LAST_SIZE = True
WINDOW_FIXED = False
WINDOW_MIN_W = 980
WINDOW_MIN_H = 640
DESIGN_WIDTH = 1360
DESIGN_HEIGHT = 760
MIN_SCALE = 0.85
MAX_SCALE = 1.70
LEFT_SIDEBAR_BASE_W = 260
RIGHT_PANEL_BASE_W = 320
BASE_APP_POINT_SIZE = 10.0
MIN_APP_POINT_SIZE = 12.0
BTN_H_BASE = 34
PROGRESS_H_BASE = 18
ORG_NAME = "Voikan"
APP_NAME = "MultimediaPanel"

# Включити підтримку High DPI
os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
os.environ["QT_SCALE_FACTOR"] = "1"
os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"

def _mk_pixmap(size: int, paint_fn):
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm); p.setRenderHint(QPainter.Antialiasing, True)
    p.setPen(Qt.NoPen); p.setBrush(QColor(255,255,255))
    paint_fn(p, size)
    p.end()
    return pm

def _icon_headphones(size=36):
    def _paint(p: QPainter, S: int):
        path = QPainterPath()
        path.moveTo(QPointF(S*0.15, S*0.55))
        path.arcTo(QRectF(S*0.15, S*0.15, S*0.70, S*0.70), 180, -180)
        p.drawPath(path)
        p.drawRoundedRect(QRectF(S*0.12, S*0.48, S*0.18, S*0.28), 4, 4)
        p.drawRoundedRect(QRectF(S*0.70, S*0.48, S*0.18, S*0.28), 4, 4)
        p.setBrush(QColor(255,255,255,220))
        p.drawRoundedRect(QRectF(S*0.20, S*0.50, S*0.12, S*0.24), 3, 3)
        p.drawRoundedRect(QRectF(S*0.68, S*0.50, S*0.12, S*0.24), 3, 3)
    return QIcon(_mk_pixmap(size, _paint))

def _icon_camera(size=36):
    def _paint(p: QPainter, S: int):
        body = QRectF(S*0.10, S*0.22, S*0.80, S*0.56)
        p.drawRoundedRect(body, 6, 6)
        p.drawRoundedRect(QRectF(S*0.18, S*0.16, S*0.28, S*0.10), 3, 3)
        p.setBrush(QColor(255,255,255,230))
        p.drawEllipse(QPointF(S*0.50, S*0.50), S*0.18, S*0.18)
        p.setBrush(Qt.NoBrush)
    return QIcon(_mk_pixmap(size, _paint))

def _icon_youtube(size=36):
    def _paint(p: QPainter, S: int):
        rect = QRectF(S*0.12, S*0.24, S*0.76, S*0.52)
        p.drawRoundedRect(rect, S*0.18, S*0.18)
        tri = QPainterPath()
        tri.moveTo(QPointF(S*0.46, S*0.36))
        tri.lineTo(QPointF(S*0.46, S*0.64))
        tri.lineTo(QPointF(S*0.68, S*0.50))
        tri.closeSubpath()
        p.setBrush(QColor(255,255,255,240))
        p.drawPath(tri)
    return QIcon(_mk_pixmap(size, _paint))

def _icon_calendar_play(size=36):
    def _paint(p: QPainter, S: int):
        p.drawRoundedRect(QRectF(S*0.12, S*0.20, S*0.76, S*0.60), 6, 6)
        p.drawRoundedRect(QRectF(S*0.22, S*0.12, S*0.10, S*0.14), 2, 2)
        p.drawRoundedRect(QRectF(S*0.68, S*0.12, S*0.10, S*0.14), 2, 2)
        tri = QPainterPath()
        tri.moveTo(QPointF(S*0.46, S*0.42))
        tri.lineTo(QPointF(S*0.46, S*0.62))
        tri.lineTo(QPointF(S*0.62, S*0.52))
        tri.closeSubpath()
        p.setBrush(QColor(255,255,255,240))
        p.drawPath(tri)
    return QIcon(_mk_pixmap(size, _paint))

def _icon_chat(size=36):
    def _paint(p: QPainter, S: int):
        bubble = QPainterPath()
        bubble.addRoundedRect(QRectF(S*0.12, S*0.20, S*0.76, S*0.56), 8, 8)
        bubble.moveTo(QPointF(S*0.28, S*0.76))
        bubble.lineTo(QPointF(S*0.40, S*0.76))
        bubble.lineTo(QPointF(S*0.26, S*0.90))
        bubble.closeSubpath()
        p.drawPath(bubble)
        p.setBrush(QColor(255,255,255,230))
        r = S*0.06
        p.drawEllipse(QPointF(S*0.40, S*0.48), r, r)
        p.drawEllipse(QPointF(S*0.50, S*0.48), r, r)
        p.drawEllipse(QPointF(S*0.60, S*0.48), r, r)
    return QIcon(_mk_pixmap(size, _paint))

def _load_icon_with_fallback(label: str, path: str) -> QIcon:
    if path and os.path.exists(path):
        return QIcon(path)
    t = (label or '').lower()
    if "suno" in t or "аудіо" in t or "audio" in t:
        return _icon_headphones()
    if "фото" in t or "photo" in t or "vertex" in t:
        return _icon_camera()
    if "youtube" in t or "монтаж" in t or "video" in t:
        return _icon_youtube()
    if "планер" in t or "planner" in t:
        return _icon_calendar_play()
    return _icon_chat()

class SideMenuWidget(QWidget):
    def __init__(self, menu: QListWidget, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        title = QLabel("VOIKAN RECORDS")
        title.setStyleSheet("""
            color: rgba(255,255,255,160);
            font-weight: 700;
            letter-spacing: 1.5px;
            padding-left: 16px;
        """)
        layout.addWidget(title)
        layout.addWidget(menu, 1)

        self.setObjectName("SideMenuContainer")
        self.setStyleSheet("""
            QWidget#SideMenuContainer {
                background: rgba(16,20,26,220);
                border-radius: 18px;
                padding: 12px 0;
            }
        """)

class MainWindow(QMainWindow):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.setWindowTitle("VOIKAN RECORDS")

        # Отримати DPI екрану
        self.screen_dpi = self.screen().logicalDotsPerInch()
        self.dpi_scale = max(1.0, self.screen_dpi / 96.0)

        self._apply_initial_geometry()
        self._base_point_size = BASE_APP_POINT_SIZE or (self.app.font().pointSizeF() or 10.0)
        self._ui_scale = 1.0 * self.dpi_scale  # Початковий масштаб з урахуванням DPI

        self._running = defaultdict(bool)
        self._progress_val = defaultdict(int)
        self._progress_lbl = defaultdict(str)

        self.menu = QListWidget()
        self.menu.setObjectName("SideMenu")
        self.menu.setFrameShape(QFrame.NoFrame)
        self.menu.setUniformItemSizes(True)
        self.menu.setIconSize(QSize(36, 36))
        self.menu.setSpacing(6)
        self.menu.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.menu.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.menu.setItemDelegate(GlassItemDelegate(self.menu))
        self.menu.setMouseTracking(True)
        self.menu.setStyleSheet("QListWidget{outline:0;} QListWidget::item{background:transparent;} QListWidget::item:selected{background:transparent;}")

        self.sidebar = SideMenuWidget(self.menu)

        self.page_audio    = AudioPage(); self.page_audio.set_host(self)
        self.page_photo    = PhotoPage()
        self.page_videos   = self._make_video_tabs()  # містить VideoPage/ShortsPage
        self.page_planner  = PlannerTab()
        self.page_autofill = AutoFillTab()

        menu_items = [
            ("Аудіо Suno",      "assets/icons/audio.svg",     self.page_audio),
            ("Фото Vertex",     "assets/icons/photo.svg",     self.page_photo),
            ("Монтаж YouTube",  "assets/icons/video.svg",     self.page_videos),
            ("YT Планер",       "assets/icons/planner.svg",   self.page_planner),
            ("YT AutoFill",     "assets/icons/autofill.svg",  self.page_autofill),
        ]

        self.pages = QStackedWidget()
        for label, icon_path, widget in menu_items:
            icon = _load_icon_with_fallback(label, icon_path)
            item = QListWidgetItem(icon, label)
            item.setSizeHint(QSize(220, 68))
            self.menu.addItem(item)
            self.pages.addWidget(widget)

        self.menu.currentRowChanged.connect(self._switch_page)

        self.ctrl_panel = self._make_control_panel()

        root = QWidget()
        self.setCentralWidget(root)
        lay = QHBoxLayout(root)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(12)
        lay.addWidget(self.sidebar)
        lay.addWidget(self.pages, 1)
        lay.addWidget(self.ctrl_panel)

        self.menu.setCurrentRow(0)
        self._apply_scale(self._ui_scale)

        if hasattr(self.page_autofill, "sig_log"):
            self.page_autofill.sig_log.connect(lambda text: self.log(self.page_autofill, text))
        if hasattr(self.page_autofill, "sig_progress"):
            self.page_autofill.sig_progress.connect(
                lambda val, lbl="AutoFill": self.set_progress(self.page_autofill, int(val), lbl)
            )
        if hasattr(self.page_autofill, "sig_running"):
            self.page_autofill.sig_running.connect(
                lambda running: self.set_running(self.page_autofill, bool(running))
            )

        self._apply_qss_theme("dark_modern.qss")
        self._apply_extra_styles()

        # --- неонове світіння під кнопками ---
        self._neon_effects = {}
        self._install_neon(self.btn_start, QColor(24,227,127))
        self._install_neon(self.btn_stop,  QColor(255,75,75))
        self.btn_start.installEventFilter(self)
        self.btn_stop.installEventFilter(self)

    def _make_video_tabs(self):
        tabs = QTabWidget()

        # створюємо сторінки
        vp = VideoPage()
        sp = ShortsPage()

        # важливо: прив'язати до універсальної панелі (хост — головне вікно)
        if hasattr(vp, "set_host"):
            try: vp.set_host(self)
            except Exception: pass
        if hasattr(sp, "set_host"):
            try: sp.set_host(self)
            except Exception: pass

        tabs.addTab(vp, QIcon("assets/icons/video.svg"),  "Відео")
        tabs.addTab(sp, QIcon("assets/icons/video.svg"), "Shorts")

        # коли перемикається вкладка всередині — оновлюємо праву панель під активну внутрішню сторінку
        tabs.currentChanged.connect(lambda _i: self._sync_right_panel_for(self._current_page()))
        return tabs

    def _apply_initial_geometry(self):
        # Розміри з урахуванням DPI
        base_width = int(WINDOW_WIDTH * self.dpi_scale)
        base_height = int(WINDOW_HEIGHT * self.dpi_scale)
        
        if WINDOW_MIN_W or WINDOW_MIN_H:
            min_w = int((WINDOW_MIN_W or 0) * self.dpi_scale)
            min_h = int((WINDOW_MIN_H or 0) * self.dpi_scale)
            self.setMinimumSize(max(0, min_w), max(0, min_h))
            
        if REMEMBER_LAST_SIZE:
            s = QSettings(ORG_NAME, APP_NAME)
            w = s.value("win/width", type=int)
            h = s.value("win/height", type=int)
            if w and h:
                self.resize(w, h)
            else:
                self.resize(base_width, base_height)
        else:
            self.resize(base_width, base_height)
            
        if WINDOW_FIXED:
            self.setFixedSize(self.size())

    def closeEvent(self, event: QCloseEvent) -> None:
        if REMEMBER_LAST_SIZE and not WINDOW_FIXED:
            s = QSettings(ORG_NAME, APP_NAME)
            s.setValue("win/width", self.width())
            s.setValue("win/height", self.height())
        super().closeEvent(event)

    def _make_control_panel(self) -> QWidget:
        panel = QWidget()
        v = QVBoxLayout(panel)
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(12)

        gb = QGroupBox("Керування (активна вкладка)")
        lv = QVBoxLayout(gb)

        self.rb_auto = QRadioButton("авто")
        self.rb_auto.setChecked(True)
        self.rb_manual = QRadioButton("ручн")
        lv.addWidget(self.rb_auto)
        lv.addWidget(self.rb_manual)

        self.btn_start = AnimatedPushButton("старт"); self.btn_start.setObjectName("startBtn")
        self.btn_stop  = AnimatedPushButton("стоп");  self.btn_stop.setObjectName("stopBtn")
        self.btn_stop.setEnabled(False)
        self.btn_start.clicked.connect(self._on_start_clicked)
        self.btn_stop.clicked.connect(self._on_stop_clicked)
        lv.addWidget(self.btn_start)
        lv.addWidget(self.btn_stop)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        lv.addWidget(self.progress)

        v.addWidget(gb)

        gb2 = QGroupBox("Логи (усі вкладки)")
        lv2 = QVBoxLayout(gb2)
        self.logs = QTextEdit(); self.logs.setReadOnly(True)
        self.btn_clear_logs = AnimatedPushButton("Очистити логи")
        self.btn_clear_logs.clicked.connect(self.logs.clear)
        lv2.addWidget(self.logs, 1)
        lv2.addWidget(self.btn_clear_logs)

        v.addWidget(gb2, 1)
        panel.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        return panel

    def resizeEvent(self, e):
        super().resizeEvent(e)
        
        # Масштабування на основі розміру вікна та DPI
        sw = self.width() / max(1, DESIGN_WIDTH * self.dpi_scale)
        sh = self.height() / max(1, DESIGN_HEIGHT * self.dpi_scale)
        scale = max(MIN_SCALE, min(MAX_SCALE, min(sw, sh) * self.dpi_scale))
        
        if abs(scale - self._ui_scale) >= 0.02:
            self._ui_scale = scale
            self._apply_scale(scale)

    def _apply_qss_theme(self, qss_filename: str = "dark_modern.qss") -> bool:
        candidates = [
            qss_filename,
            os.path.join(os.getcwd(), qss_filename),
            os.path.join(os.path.dirname(__file__), qss_filename),
        ]
        for p in candidates:
            try:
                if os.path.exists(p):
                    with open(p, "r", encoding="utf-8") as f:
                        self.app.setStyleSheet(f.read())
                    return True
            except Exception:
                pass
        return False

    # --- неонове світіння під кнопками без зміни логіки ---
    def _install_neon(self, btn, color: QColor):
        eff = QGraphicsDropShadowEffect(btn)
        eff.setColor(QColor(color.red(), color.green(), color.blue(), 140))
        eff.setBlurRadius(36)
        eff.setOffset(0, 6)
        btn.setGraphicsEffect(eff)
        self._neon_effects[btn] = (eff, color)

    def eventFilter(self, obj, ev):
        if obj in getattr(self, "_neon_effects", {}):
            eff, base = self._neon_effects[obj]
            if ev.type() == QEvent.Enter:
                eff.setColor(QColor(base.red(), base.green(), base.blue(), 170))
                eff.setBlurRadius(40); eff.setOffset(0, 7)
            elif ev.type() == QEvent.Leave:
                eff.setColor(QColor(base.red(), base.green(), base.blue(), 130))
                eff.setBlurRadius(34); eff.setOffset(0, 5)
            elif ev.type() == QEvent.MouseButtonPress:
                eff.setColor(QColor(base.red(), base.green(), base.blue(), 230))
                eff.setBlurRadius(48); eff.setOffset(0, 9)
            elif ev.type() == QEvent.MouseButtonRelease:
                if obj.rect().contains(obj.mapFromGlobal(obj.cursor().pos())):
                    eff.setColor(QColor(base.red(), base.green(), base.blue(), 170))
                    eff.setBlurRadius(40); eff.setOffset(0, 7)
                else:
                    eff.setColor(QColor(base.red(), base.green(), base.blue(), 130))
                    eff.setBlurRadius(34); eff.setOffset(0, 5)
        return super().eventFilter(obj, ev)

    def _apply_extra_styles(self):
        EXTRA_QSS = """
        QGroupBox {
            background: rgba(16,20,26,140);
            border: 1px solid rgba(255,255,255,36);
            border-radius: 14px;
            margin-top: 10px;
            color: #8A97A8;
            font-weight: 600;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 12px;
            padding: 0 6px;
        }

        QPushButton#startBtn {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                        stop:0 #18e37f, stop:1 #0da965);
            border: 1px solid rgba(24,227,127,160);
            color: white;
            border-radius: 14px;
            padding: 8px 16px;
            font-weight: 600;
        }
        QPushButton#startBtn:hover {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                        stop:0 #1ff090, stop:1 #11be74);
            border-color: rgba(31,240,144,200);
        }
        QPushButton#startBtn:pressed {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                        stop:0 #0fb86a, stop:1 #0a8e52);
        }
        QPushButton#startBtn:disabled {
            background: rgba(50,70,60,120);
            color: rgba(255,255,255,110);
            border-color: rgba(255,255,255,40);
        }

        QPushButton#stopBtn {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                        stop:0 #ff4b4b, stop:1 #b81414);
            border: 1px solid rgba(255,75,75,160);
            color: white;
            border-radius: 14px;
            padding: 8px 16px;
            font-weight: 600;
        }
        QPushButton#stopBtn:hover {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                        stop:0 #ff5f5f, stop:1 #d31d1d);
            border-color: rgba(255,95,95,200);
        }
        QPushButton#stopBtn:pressed {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                        stop:0 #d63131, stop:1 #991111);
        }
        QPushButton#stopBtn:disabled {
            background: rgba(70,50,50,120);
            color: rgba(255,255,255,110);
            border-color: rgba(255,255,255,40);
        }

        QTextEdit {
            background: rgba(20, 24, 30, 180);
            border: 1px solid rgba(255,255,255,40);
            border-radius: 12px;
            padding: 8px;
            color: #E7EBF1;
            selection-background-color: rgba(56,130,246,140);
            selection-color: white;
            font-family: Consolas, "JetBrains Mono", monospace;
            font-size: 12pt;
        }

        QProgressBar {
            background: rgba(20,24,30,150);
            border: 1px solid rgba(255,255,255,40);
            border-radius: 10px;
            text-align: center;
            color: #C7D0DC;
        }
        QProgressBar::chunk {
            border-radius: 9px;
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                        stop:0 #2da8ff, stop:1 #7cc9ff);
        }
        """
        self.app.setStyleSheet(self.app.styleSheet() + "\n" + EXTRA_QSS)

    def _apply_scale(self, scale: float):
        f = self.app.font()
        base = (BASE_APP_POINT_SIZE or f.pointSizeF() or 10.0)
        size = max(MIN_APP_POINT_SIZE, base * scale)
        f.setPointSizeF(size)
        self.app.setFont(f)

        self.menu.setFixedWidth(int(LEFT_SIDEBAR_BASE_W * scale))
        self.ctrl_panel.setFixedWidth(int(RIGHT_PANEL_BASE_W * scale))

        h_btn = max(28, int(BTN_H_BASE * scale))
        h_prog = max(12, int(PROGRESS_H_BASE * scale))
        for b in (self.btn_start, self.btn_stop, self.btn_clear_logs):
            b.setMinimumHeight(h_btn)
        self.progress.setFixedHeight(h_prog)

        for i in range(self.menu.count()):
            it = self.menu.item(i)
            it.setSizeHint(QSize(it.sizeHint().width(), max(56, int(68 * scale))))

        for i in range(self.pages.count()):
            page = self.pages.widget(i)
            if hasattr(page, "apply_scale"):
                page.apply_scale(scale)

    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    # ВАЖЛИВО: повертаємо "глибоку" активну сторінку (для QTabWidget — її currentWidget)
    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    def _current_page(self):
        w = self.pages.currentWidget()
        if isinstance(w, QTabWidget):
            inner = w.currentWidget()
            return inner if inner is not None else w
        return w

    def _switch_page(self, index: int):
        self.pages.setCurrentIndex(index)
        # синхронізувати праву панель під нову активну (може бути внутрішня у вкладках)
        self._sync_right_panel_for(self._current_page())

    def _sync_right_panel_for(self, page):
        if page is None:
            return
        running = self._running[page]
        self.btn_start.setEnabled(not running)
        self.btn_stop.setEnabled(running)
        self.progress.setValue(self._progress_val[page])
        label = self._progress_lbl[page]
        self.progress.setFormat(f"{label} — {self._progress_val[page]}%" if label else "%p%")

    def _on_start_clicked(self):
        page = self._current_page()
        if hasattr(page, "handle_start"):
            auto_mode = self.rb_auto.isChecked()
            page.handle_start(auto_mode)
        self.set_running(page, True)
        self.log(page, "▶ старт")

    def _on_stop_clicked(self):
        page = self._current_page()
        if hasattr(page, "handle_stop"):
            page.handle_stop()
        self.set_running(page, False)
        self.log(page, "■ стоп")

    def log(self, page, text: str):
        tag = "Аудіо" if isinstance(page, AudioPage) else \
              "Фото"  if isinstance(page, PhotoPage) else \
              "Відео" if isinstance(page, (VideoPage, ShortsPage)) else \
              "Планер" if isinstance(page, PlannerTab) else \
              "AutoFill" if isinstance(page, AutoFillTab) else "Інше"
        self.logs.append(f"[{tag}] {text}")

    def set_progress(self, page, value: int, label: str = ""):
        self._progress_val[page] = max(0, min(100, int(value)))
        self._progress_lbl[page] = label or ""
        if page is self._current_page():
            self.progress.setValue(self._progress_val[page])
            self.progress.setFormat(f"{label} — {self._progress_val[page]}%" if label else "%p%")

    def set_running(self, page, running: bool):
        self._running[page] = bool(running)
        if page is self._current_page():
            self.btn_start.setEnabled(not running)
            self.btn_stop.setEnabled(running)
