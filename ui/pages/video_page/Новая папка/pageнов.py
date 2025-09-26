# -*- coding: utf-8 -*-
from __future__ import annotations
"""
VideoPage — UI без скролів, скляні кнопки форматів, вертикальний селектор у Прев'ю.
Ліва колонка: Пресети → Еквалайзер → Ефекти → Рух/Камера.
Права колонка: Папки → Параметри рендеру → Прев'ю(ліворуч формати, праворуч прев'ю) → Звіт → ЛОГИ технічні → Прогрес.
Правий зовнішній лог (із головного вікна) — лише '✅ Готово' / '❌ Помилка'.
"""

import os, json, queue, shutil, hashlib, threading
from typing import Dict, Tuple

from PySide6.QtCore import Qt, QTimer, Signal, Slot, QRectF, QPoint, QSize
from PySide6.QtGui import (
    QPixmap, QColor, QPainter, QFont, QPolygon, QPainterPath,
    QRadialGradient, QLinearGradient, QPen
)
from PySide6.QtWidgets import (
    QWidget, QLabel, QPushButton, QLineEdit, QFileDialog, QComboBox,
    QCheckBox, QSpinBox, QDoubleSpinBox, QSlider,
    QHBoxLayout, QVBoxLayout, QGridLayout, QGroupBox, QFormLayout,
    QProgressBar, QMessageBox, QInputDialog,
    QFrame, QSplitter, QPlainTextEdit, QSizePolicy, QScrollArea
)

# ==== бекенд/рендер (твоя логіка; не змінюю) ====
try:
    from video_backend import start_video_jobs, stop_all_jobs, reset_processing_state
    from effects_render import (
        make_eq_overlay, make_stars_overlay, make_rain_overlay, make_smoke_overlay,
        draw_motion_indicator,
    )
except Exception:
    # якщо структура інша — лишив сумісний імпорт
    from logic.video_backend import start_video_jobs, stop_all_jobs, reset_processing_state
    from logic.effects_render import (
        make_eq_overlay, make_stars_overlay, make_rain_overlay, make_smoke_overlay,
        draw_motion_indicator,
    )

CACHE_DIR   = os.path.join("_cache", "video_ui")
STAGE_DIR   = os.path.join(CACHE_DIR, "playlist_stage")
os.makedirs(CACHE_DIR, exist_ok=True)

CONFIG_FILE       = os.path.join(CACHE_DIR, "video_qt_config.json")
USER_PRESETS_FILE = os.path.join(CACHE_DIR, "video_user_presets.json")

# ------------------------ ТЕМА (скляні пілюлі) ------------------------
THEME_CSS = """
QWidget { background: #0B0B0B; color: #EAEAEA; font-size: 13px; }
QGroupBox {
    border: 1px solid #1E1E1E; border-radius: 14px; margin-top: 10px;
    padding: 10px; background: #101010;
}
QGroupBox::title { left: 10px; padding: 0 6px; color: #BDBDBD; }

/* Скляні кнопки */
QPushButton {
    color: #FFFFFF;
    padding: 8px 16px;
    border-radius: 20px;
    border: 1px solid rgba(255,255,255,0.25);
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 rgba(255,255,255,0.18),
        stop:0.45 rgba(255,255,255,0.10),
        stop:0.46 rgba(255,255,255,0.06),
        stop:1 rgba(0,0,0,0.18)
    );
}
QPushButton:hover {
    border: 1px solid rgba(255,255,255,0.40);
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 rgba(255,255,255,0.24),
        stop:0.45 rgba(255,255,255,0.12),
        stop:0.46 rgba(255,255,255,0.08),
        stop:1 rgba(0,0,0,0.22)
    );
}
QPushButton:pressed {
    border: 1px solid rgba(255,255,255,0.30);
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 rgba(255,255,255,0.12),
        stop:0.50 rgba(0,0,0,0.22),
        stop:1 rgba(0,0,0,0.28)
    );
}
QPushButton:disabled {
    color: #888;
    border: 1px solid rgba(255,255,255,0.15);
    background: rgba(255,255,255,0.04);
}

/* Поля/спіни/комбо */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background: rgba(20,20,20,0.9);
    border: 1px solid #262626; border-radius: 10px; padding: 6px 10px;
    selection-background-color: #2D65F3;
}
QComboBox QAbstractItemView { background: #141414; }

/* Слайдери */
QSlider::groove:horizontal { height: 6px; background: #1D1D1D; border-radius: 4px; }
QSlider::handle:horizontal {
    width: 16px; height: 16px; margin: -5px 0; border-radius: 8px;
    background: qradialgradient(cx:0.3, cy:0.3, radius:0.8,
        fx:0.3, fy:0.3, stop:0 #8EC2FF, stop:0.6 #4C9EFF, stop:1 #2D65F3);
    border: 1px solid #2D65F3;
}

/* Прогресбар */
QProgressBar { background: rgba(19,19,19,0.8); border: 1px solid #262626; border-radius: 10px; text-align: center; padding: 3px; }
QProgressBar::chunk {
    border-radius: 8px;
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #7FB6FF, stop:1 #2D65F3);
}

/* Картки форматів малюються кастомно у paintEvent */
"""

# ------------------------ Дрібні віджети ------------------------
class ColorButton(QPushButton):
    changed = Signal(QColor)
    def __init__(self, hex_color: str = "#FFFFFF", parent=None):
        super().__init__(parent)
        self._c = QColor(hex_color)
        self.setFixedWidth(72)
        self._apply_style()
        self.clicked.connect(self._pick)
    def _apply_style(self):
        txt = self._c.name().upper()
        self.setText(txt)
        text_color = "#000" if self._c.lightness() > 120 else "#FFF"
        self.setStyleSheet(
            f"background:{self._c.name()}; color:{text_color}; border:1px solid #444; border-radius:10px;"
        )
    def _pick(self):
        from PySide6.QtWidgets import QColorDialog
        c = QColorDialog.getColor(self._c, self, "Колір")
        if c.isValid():
            self._c = c; self._apply_style(); self.changed.emit(self._c)
    def color(self) -> QColor: return self._c
    def setColor(self, c: QColor):
        if c and c.isValid(): self._c = c; self._apply_style(); self.changed.emit(self._c)

class PathPicker(QWidget):
    changed = Signal(str)
    def __init__(self, placeholder: str = "", default: str = "", is_dir=True, parent=None):
        super().__init__(parent)
        self.is_dir = is_dir
        self.ed = QLineEdit(default); self.ed.setPlaceholderText(placeholder)
        self.btn = QPushButton("…"); self.btn.setFixedWidth(30)
        lay = QHBoxLayout(self); lay.setContentsMargins(0,0,0,0); lay.setSpacing(6)
        lay.addWidget(self.ed, 1); lay.addWidget(self.btn, 0)
        self.btn.clicked.connect(self._pick)
        self.ed.textChanged.connect(lambda _: self.changed.emit(self.text()))
    def _pick(self):
        if self.is_dir:
            d = QFileDialog.getExistingDirectory(self, "Обрати папку", self.text() or "D:/")
        else:
            d, _ = QFileDialog.getOpenFileName(self, "Обрати файл", self.text() or "D:/")
        if d: self.ed.setText(d); self.changed.emit(self.text())
    def text(self) -> str: return self.ed.text().strip()
    def setText(self, s: str): self.ed.setText(s or "")

# ------------------------ HELPERS ------------------------
def _ensure_dir(path: str) -> str: return path if path and os.path.isdir(path) else ""
def _pct(slider: QSlider) -> int:   return max(0, min(100, int(slider.value())))
def _hex(qc: QColor) -> str:       return qc.name().upper()
def _mk_slider(a: int, b: int, v: int) -> QSlider:
    s = QSlider(Qt.Horizontal); s.setMinimum(a); s.setMaximum(b); s.setValue(v)
    s.setTickInterval(max(1, (b - a) // 10)); s.setSingleStep(max(1, (b - a) // 50)); return s
def _mmss_to_seconds(text: str) -> int:
    try:
        t = text.strip(); parts = [int(x) for x in t.split(":")]
        if len(parts) == 3: return parts[0]*3600 + parts[1]*60 + parts[2]
        if len(parts) == 2: return parts[0]*60 + parts[1]
        return int(t)
    except Exception: return 180
def _seconds_to_mmss(sec: int) -> str: sec = max(0, int(sec)); return f"{sec//60:02d}:{sec%60:02d}"
def _md5sig(d: dict) -> str:
    try: return hashlib.md5(json.dumps(d, sort_keys=True).encode("utf-8")).hexdigest()[:8]
    except Exception: return "????????"

# =================================================================
#  Пілюлі форматів (градієнтні, скляні, іконка без чорного фону)
# =================================================================
BRAND_GRAD = {
    "youtube":  (QColor(210,22,22), QColor(110,0,0)),
    "shorts":   (QColor(220,22,22), QColor(110,0,0)),
    "ig":       (QColor(146,52,235), QColor(255,118,48)),   # purple → orange
    "tiktok":   (QColor(37,244,238), QColor(237,58,110)),   # cyan → magenta
    "facebook": (QColor(45,136,255), QColor(15,52,120)),    # blue
}

class FormatCard(QFrame):
    clicked = Signal(str)
    def __init__(self, key: str, title: str, subtitle: str, brand: str, parent=None):
        super().__init__(parent)
        self.key = key
        self.brand = brand
        self.title_text = title
        self.subtitle_text = subtitle
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._h = 64
        self._logo = 44
        self._checked = False

    def sizeHint(self) -> QSize:
        return QSize(260, self._h)

    # —————— малювання пілюлі
    def paintEvent(self, e):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing, True)
        r = self.rect().adjusted(2,2,-2,-2)
        rad = 16

        # фоновий градієнт пілюлі
        c1, c2 = BRAND_GRAD.get(self.brand, (QColor(90,90,90), QColor(40,40,40)))
        grad = QLinearGradient(r.topLeft(), r.topRight())
        grad.setColorAt(0.0, c1); grad.setColorAt(1.0, c2)
        p.setBrush(grad); p.setPen(QColor(255,255,255,55))
        p.drawRoundedRect(r, rad, rad)

        # легкий верхній глянець
        gloss = QLinearGradient(r.topLeft(), r.bottomLeft())
        gloss.setColorAt(0.0, QColor(255,255,255,70))
        gloss.setColorAt(0.45, QColor(255,255,255,22))
        gloss.setColorAt(0.46, QColor(255,255,255,8))
        gloss.setColorAt(1.0, QColor(0,0,0,38))
        p.setBrush(gloss); p.setPen(Qt.NoPen)
        p.drawRoundedRect(r, rad, rad)

        # circular glass logo (ПРОЗОРИЙ задній фон!)
        S = self._logo
        x = r.left() + 10; y = r.center().y() - S//2
        pm = QPixmap(S, S); pm.fill(Qt.transparent)
        pi = QPainter(pm); pi.setRenderHint(QPainter.Antialiasing, True)

        # скляний диск
        gradc = QRadialGradient(S*0.35, S*0.30, S*0.75)
        gradc.setColorAt(0.0, QColor(255,255,255,32))
        gradc.setColorAt(0.6, QColor(255,255,255,18))
        gradc.setColorAt(1.0, QColor(0,0,0,40))
        pi.setBrush(gradc); pi.setPen(QColor(255,255,255,60)); pi.drawEllipse(0,0,S,S)
        pi.setPen(Qt.NoPen); pi.setBrush(QColor(c1.red(), c1.green(), c1.blue(), 36)); pi.drawEllipse(1,1,S-2,S-2)
        gloss = QPainterPath(); gloss.addEllipse(QRectF(S*0.10, S*0.06, S*0.80, S*0.48))
        pi.setBrush(QColor(255,255,255,100)); pi.drawPath(gloss)
        pi.setBrush(Qt.NoBrush); pi.setPen(QColor(255,255,255,110)); pi.drawEllipse(0,0,S,S)

        # гліф (білий, без підкладки)
        pi.setBrush(Qt.white); pi.setPen(Qt.NoPen)
        if "youtube" in self.key:
            tri = QPolygon([QPoint(int(S*0.42), int(S*0.34)),
                            QPoint(int(S*0.42), int(S*0.66)),
                            QPoint(int(S*0.72), int(S*0.50))])
            pi.drawPolygon(tri)
        elif "shorts" in self.key:
            rct = QRectF(S*0.28, S*0.24, S*0.44, S*0.52); pi.drawRoundedRect(rct, S*0.18, S*0.18)
            pi.setBrush(c1); pi.drawEllipse(QRectF(S*0.44, S*0.42, S*0.18, S*0.18))
        elif "ig" in self.key:
            pi.setBrush(Qt.white)
            pi.drawRoundedRect(QRectF(S*0.24,S*0.24,S*0.52,S*0.52), S*0.18, S*0.18)
            pi.setBrush(c1); pi.drawEllipse(QRectF(S*0.40,S*0.40,S*0.24,S*0.24))
            pi.setBrush(Qt.white); pi.drawEllipse(QRectF(S*0.68,S*0.27,S*0.10,S*0.10))
        elif "tiktok" in self.key or "tt" in self.key:
            pi.drawRect(int(S*0.46), int(S*0.26), int(S*0.10), int(S*0.40))
            pi.drawEllipse(QRectF(S*0.32,S*0.56,S*0.20,S*0.16))
            pi.drawRect(int(S*0.56), int(S*0.26), int(S*0.10), int(S*0.10))
            pi.drawEllipse(QRectF(S*0.55,S*0.18,S*0.18,S*0.12))
        elif "facebook" in self.key or "fb" in self.key:
            stem = QRectF(S*0.46, S*0.24, S*0.10, S*0.52); pi.drawRect(stem)
            arm  = QRectF(S*0.38, S*0.36, S*0.26, S*0.10); pi.drawRect(arm)

        pi.end(); p.drawPixmap(x, y, pm)

        # текст (без чорного прямокутника)
        p.setPen(Qt.white)
        f = p.font(); f.setPointSize(12); f.setBold(True); p.setFont(f)
        p.drawText(x + S + 12, y + 20, self.title_text)
        f.setPointSize(10); f.setBold(False); p.setFont(f)
        p.drawText(x + S + 12, y + 40, self.subtitle_text)

        # бордер вибору
        if self._checked:
            sel = QPen(QColor(255,255,255,180), 2)
            p.setPen(sel); p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(r.adjusted(1,1,-1,-1), rad-2, rad-2)

        p.end()

    def setChecked(self, v: bool):
        self._checked = bool(v)
        self.update()

    def apply_scale(self, scale: float):
        self._h = max(52, int(64 * scale))
        self._logo = max(36, int(44 * scale))
        self.updateGeometry(); self.update()

    def mousePressEvent(self, e):
        self.clicked.emit(self.key)
        super().mousePressEvent(e)

class FormatSelectorVertical(QWidget):
    selected = Signal(str)
    """
    Вертикальний список карток форматів (без скролів, підіймає висоту карток під масштаб).
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        wrap = QVBoxLayout(self); wrap.setContentsMargins(0,0,0,0); wrap.setSpacing(8)

        title = QLabel("Модель формату")
        f = QFont(); f.setPointSize(14); f.setBold(True); title.setFont(f); title.setStyleSheet("color:#E0E0E0;")
        wrap.addWidget(title)

        self.cards: Dict[str, FormatCard] = {}
        def add(key, title, sub, brand):
            c = FormatCard(key, title, sub, brand, self)
            c.clicked.connect(self._on_click); self.cards[key] = c; wrap.addWidget(c)

        add("youtube_16_9", "YouTube",          "16:9 · 1920×1080", "youtube")
        add("shorts_9_16",  "Shorts",           "9:16 · 1080×1920", "shorts")
        add("ig_reels_9_16","Instagram Reels",  "9:16 · 1080×1920", "ig")
        add("ig_4_5",       "Instagram 4:5",    "4:5 · 1080×1350",  "ig")
        add("ig_1_1",       "Instagram 1:1",    "1:1 · 1080×1080",  "ig")
        add("tiktok_9_16",  "TikTok",           "9:16 · 1080×1920", "tiktok")
        add("fb_4_5",       "Facebook 4:5",     "4:5 · 1080×1350",  "facebook")
        add("fb_1_1",       "Facebook 1:1",     "1:1 · 1080×1080",  "facebook")

        wrap.addStretch(1)
        self._on_click("youtube_16_9")

    def _on_click(self, key: str):
        for k, c in self.cards.items():
            c.setChecked(k == key)
        self.selected.emit(key)

    def apply_scale(self, scale: float):
        for c in self.cards.values(): c.apply_scale(scale)
        self.updateGeometry(); self.update()

# =================================================================
#                           VIDEO PAGE
# =================================================================

class VideoPage(QWidget):
    # у головне вікно
    sig_biglog = Signal(str)          # глобальний лог (тільки готово/помилка)
    sig_progress = Signal(int, str)   # для головного прогресу
    sig_running = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(THEME_CSS)

        self._running = False
        self._songs_total = 0
        self._songs_done = 0

        self.status_q: "queue.Queue[dict]" = queue.Queue()
        self.cancel_event = threading.Event()
        self.poll_timer = QTimer(self); self.poll_timer.setInterval(60); self.poll_timer.timeout.connect(self._poll)

        # === Каркас без скролів
        root = QHBoxLayout(self); root.setContentsMargins(8,8,8,8); root.setSpacing(12)
        self.main_split = QSplitter(Qt.Horizontal); self.main_split.setChildrenCollapsible(False)
        root.addWidget(self.main_split)

        # ЛІВА колона
        self.left_panel = QWidget(); self.left_split = QSplitter(Qt.Vertical)
        left_box = QVBoxLayout(self.left_panel); left_box.setContentsMargins(0,0,0,0); left_box.addWidget(self.left_split)
        self.main_split.addWidget(self.left_panel)

        # ПРАВА колона
        self.right_panel = QWidget(); self.right_split = QSplitter(Qt.Vertical)
        right_box = QVBoxLayout(self.right_panel); right_box.setContentsMargins(0,0,0,0); right_box.addWidget(self.right_split)
        self.main_split.addWidget(self.right_panel)

        # ---- ЛІВА КОЛОНА ----
        # 0) Пресети (зліва нагорі)
        presets_w = QWidget(); gp = QHBoxLayout(presets_w); gp.setContentsMargins(10,10,10,10); gp.setSpacing(8)
        g_presets = QGroupBox("Пресети"); inner = QHBoxLayout(g_presets); inner.setSpacing(8)
        self.presets_combo = QComboBox(); self.presets_combo.setMinimumWidth(160)
        self.btn_save_preset = QPushButton("Зберегти")
        self.btn_delete_preset = QPushButton("Видалити")
        inner.addWidget(QLabel("Пресет:")); inner.addWidget(self.presets_combo, 1)
        inner.addWidget(self.btn_save_preset); inner.addWidget(self.btn_delete_preset)
        gp.addWidget(g_presets)
        self.left_split.addWidget(presets_w)

        # 1) Еквалайзер
        eq_w = QWidget(); eqv = QVBoxLayout(eq_w); eqv.setContentsMargins(0,0,0,0)
        self.eq_enabled = QCheckBox("Увімк.")
        self.eq_engine  = QComboBox(); self.eq_engine.addItems(["waves", "freqs"])
        self.eq_mode    = QComboBox(); self.eq_mode.addItems(["bar", "line", "dot"])
        self.eq_bars    = QSpinBox();  self.eq_bars.setRange(8, 256); self.eq_bars.setValue(96)
        self.eq_thick   = QSpinBox();  self.eq_thick.setRange(1, 12); self.eq_thick.setValue(3)
        self.eq_height  = QSpinBox();  self.eq_height.setRange(40, 1000); self.eq_height.setValue(360)
        self.eq_fullscr = QCheckBox("Повноекранний")
        self.eq_yoffset = QSpinBox();  self.eq_yoffset.setRange(-100, 100); self.eq_yoffset.setValue(0)
        self.eq_mirror  = QCheckBox("Дзеркало"); self.eq_mirror.setChecked(True)
        self.eq_baseline= QCheckBox("Базова лінія")
        self.eq_color   = ColorButton("#FFFFFF"); self.eq_opacity = _mk_slider(0,100,90)

        g_eq = QGroupBox("Еквалайзер"); gl = QGridLayout(g_eq); r=0
        gl.addWidget(self.eq_enabled, r,0); gl.addWidget(QLabel("Двигун:"), r,1); gl.addWidget(self.eq_engine, r,2)
        gl.addWidget(QLabel("Режим:"), r,3); gl.addWidget(self.eq_mode, r,4); gl.addWidget(QLabel("Смуг:"), r,5); gl.addWidget(self.eq_bars, r,6); r+=1
        gl.addWidget(QLabel("Товщина:"), r,1); gl.addWidget(self.eq_thick, r,2); gl.addWidget(QLabel("Висота:"), r,3); gl.addWidget(self.eq_height, r,4)
        gl.addWidget(self.eq_fullscr, r,5); gl.addWidget(QLabel("Y (%):"), r,6); gl.addWidget(self.eq_yoffset, r,7); r+=1
        gl.addWidget(self.eq_mirror, r,1); gl.addWidget(self.eq_baseline, r,2); gl.addWidget(QLabel("Колір:"), r,3); gl.addWidget(self.eq_color, r,4)
        gl.addWidget(QLabel("Прозорість:"), r,5); gl.addWidget(self.eq_opacity, r,6)
        eqv.addWidget(g_eq)
        self.left_split.addWidget(eq_w)

        # 2) Ефекти
        fx_w = QWidget(); fxv = QVBoxLayout(fx_w); fxv.setContentsMargins(0,0,0,0)
        self.st_enabled = QCheckBox("⭐ Зірки")
        self.st_style   = QComboBox(); self.st_style.addItems(["classic", "modern", "animated"])
        self.st_count   = QSpinBox(); self.st_count.setRange(0, 5000); self.st_count.setValue(200)
        self.st_int     = _mk_slider(0,100,55)
        self.st_size    = QSpinBox(); self.st_size.setRange(1, 20); self.st_size.setValue(2)
        self.st_pulse   = QSpinBox(); self.st_pulse.setRange(0,100); self.st_pulse.setValue(40)
        self.st_color   = ColorButton("#FFFFFF")
        self.st_opacity = _mk_slider(0,100,70)
        self.st_time_factor = QDoubleSpinBox(); self.st_time_factor.setRange(0.1, 5.0); self.st_time_factor.setValue(1.0); self.st_time_factor.setSingleStep(0.1)

        self.rn_enabled = QCheckBox("🌧 Дощ")
        self.rn_count   = QSpinBox(); self.rn_count.setRange(0, 5000); self.rn_count.setValue(1200)
        self.rn_length  = QSpinBox(); self.rn_length.setRange(5,200); self.rn_length.setValue(40)
        self.rn_thick   = QSpinBox(); self.rn_thick.setRange(1,20); self.rn_thick.setValue(2)
        self.rn_angle   = QDoubleSpinBox(); self.rn_angle.setRange(-80, 80); self.rn_angle.setValue(15.0)
        self.rn_speed   = QDoubleSpinBox(); self.rn_speed.setRange(10.0, 800.0); self.rn_speed.setValue(160.0)
        self.rn_color   = ColorButton("#9BE2FF")
        self.rn_opacity = _mk_slider(0,100,55)

        self.sm_enabled = QCheckBox("🌫 Дим")
        self.sm_density = QSpinBox(); self.sm_density.setRange(0,400); self.sm_density.setValue(60)
        self.sm_color   = ColorButton("#A0A0A0")
        self.sm_opacity = _mk_slider(0,100,35)
        self.sm_speed   = QDoubleSpinBox(); self.sm_speed.setRange(-80.0, 80.0); self.sm_speed.setValue(12.0)

        g_fx = QGroupBox("Ефекти"); gf = QGridLayout(g_fx); r=0
        gf.addWidget(self.st_enabled, r,0); gf.addWidget(QLabel("Стиль:"), r,1); gf.addWidget(self.st_style, r,2)
        gf.addWidget(QLabel("К-ть:"), r,3); gf.addWidget(self.st_count, r,4)
        gf.addWidget(QLabel("Інтенс (%):"), r,5); gf.addWidget(self.st_int, r,6)
        gf.addWidget(QLabel("Розмір:"), r,7); gf.addWidget(self.st_size, r,8); r+=1
        gf.addWidget(QLabel("Пульс:"), r,1); gf.addWidget(self.st_pulse, r,2)
        gf.addWidget(QLabel("Колір:"), r,3); gf.addWidget(self.st_color, r,4)
        gf.addWidget(QLabel("Прозорість:"), r,5); gf.addWidget(self.st_opacity, r,6)
        gf.addWidget(QLabel("Час. фактор:"), r,7); gf.addWidget(self.st_time_factor, r,8); r+=1

        gf.addWidget(self.rn_enabled, r,0); gf.addWidget(QLabel("К-ть:"), r,1); gf.addWidget(self.rn_count, r,2)
        gf.addWidget(QLabel("Довжина:"), r,3); gf.addWidget(self.rn_length, r,4)
        gf.addWidget(QLabel("Товщина:"), r,5); gf.addWidget(self.rn_thick, r,6)
        gf.addWidget(QLabel("Кут:"), r,7); gf.addWidget(self.rn_angle, r,8); r+=1
        gf.addWidget(QLabel("Швидк. (px/s):"), r,1); gf.addWidget(self.rn_speed, r,2)
        gf.addWidget(QLabel("Колір:"), r,3); gf.addWidget(self.rn_color, r,4)
        gf.addWidget(QLabel("Прозорість:"), r,5); gf.addWidget(self.rn_opacity, r,6); r+=1

        gf.addWidget(self.sm_enabled, r,0); gf.addWidget(QLabel("Густина:"), r,1); gf.addWidget(self.sm_density, r,2)
        gf.addWidget(QLabel("Колір:"), r,3); gf.addWidget(self.sm_color, r,4)
        gf.addWidget(QLabel("Прозорість:"), r,5); gf.addWidget(self.sm_opacity, r,6)
        gf.addWidget(QLabel("Дрейф (px/s):"), r,7); gf.addWidget(self.sm_speed, r,8)
        fxv.addWidget(g_fx)
        self.left_split.addWidget(fx_w)

        # 3) Рух / Камера
        mv_w = QWidget(); mvv = QVBoxLayout(mv_w); mvv.setContentsMargins(0,0,0,0)
        self.mv_enabled = QCheckBox("Увімкнути рух кадра")
        self.mv_dir     = QComboBox(); self.mv_dir.addItems(["lr","rl","up","down","zin","zout","rotate","shake"])
        self.mv_speed   = QDoubleSpinBox(); self.mv_speed.setRange(0.0, 400.0); self.mv_speed.setValue(10.0)
        self.mv_amount  = QDoubleSpinBox(); self.mv_amount.setRange(0.0, 100.0); self.mv_amount.setValue(5.0)
        self.mv_osc     = QCheckBox("Oscillate"); self.mv_osc.setChecked(True)
        self.mv_rotdeg  = QDoubleSpinBox(); self.mv_rotdeg.setRange(0.0, 45.0); self.mv_rotdeg.setValue(8.0)
        self.mv_rothz   = QDoubleSpinBox(); self.mv_rothz.setRange(0.01, 2.5); self.mv_rothz.setSingleStep(0.01); self.mv_rothz.setValue(0.10)
        self.mv_shpx    = QDoubleSpinBox(); self.mv_shpx.setRange(0.0, 50.0); self.mv_shpx.setValue(6.0)
        self.mv_shz     = QDoubleSpinBox(); self.mv_shz.setRange(0.05, 8.0); self.mv_shz.setValue(1.2)

        g_mv = QGroupBox("Рух кадра / Камера"); gm = QGridLayout(g_mv); r=0
        gm.addWidget(self.mv_enabled, r,0); gm.addWidget(QLabel("Напрям:"), r,1); gm.addWidget(self.mv_dir, r,2)
        gm.addWidget(QLabel("Швидкість:"), r,3); gm.addWidget(self.mv_speed, r,4)
        gm.addWidget(QLabel("Міра (%):"), r,5); gm.addWidget(self.mv_amount, r,6); r+=1
        gm.addWidget(self.mv_osc, r,0)
        gm.addWidget(QLabel("Rotate °:"), r,3); gm.addWidget(self.mv_rotdeg, r,4)
        gm.addWidget(QLabel("Rotate Гц:"), r,5); gm.addWidget(self.mv_rothz, r,6); r+=1
        gm.addWidget(QLabel("Shake px:"), r,3); gm.addWidget(self.mv_shpx, r,4)
        gm.addWidget(QLabel("Shake Гц:"), r,5); gm.addWidget(self.mv_shz, r,6)
        mvv.addWidget(g_mv)
        self.left_split.addWidget(mv_w)

        # ---- ПРАВА КОЛОНА ----
        # 1) Папки
        folders_w = QWidget(); fwrap = QHBoxLayout(folders_w); fwrap.setContentsMargins(10,10,10,0)
        g_paths = QGroupBox("Папки"); ff = QFormLayout(g_paths)
        self.p_music = PathPicker("Музика:", "D:/music", True)
        self.p_media = PathPicker("Фото/Відео:", "D:/media", True)
        self.p_out   = PathPicker("Вихід:", "D:/", True)
        ff.addRow("🎵 Музика:", self.p_music)
        ff.addRow("🖼 Фото/Відео:", self.p_media)
        ff.addRow("📤 Вихід:", self.p_out)
        fwrap.addWidget(g_paths)
        self.right_split.addWidget(folders_w)

        # 2) Параметри рендеру
        render_w = QWidget(); rwl = QHBoxLayout(render_w); rwl.setContentsMargins(10,0,10,0)
        g_r = QGroupBox("Параметри рендеру"); gr = QGridLayout(g_r); r=0
        self.chk_gpu = QCheckBox("Використовувати GPU"); self.chk_gpu.setChecked(True)
        self.cmb_gpu    = QComboBox(); self.cmb_gpu.addItems(["auto","nvidia","intel","amd","cpu"])
        self.cmb_preset = QComboBox(); self.cmb_preset.addItems(["auto/balanced","p1","p2","p3","p4","p5","p6","p7(quality)"])
        self.sp_threads = QSpinBox(); self.sp_threads.setRange(0,64); self.sp_threads.setValue(16)
        self.sp_jobs    = QSpinBox(); self.sp_jobs.setRange(1,10); self.sp_jobs.setValue(1)
        self.sp_songs   = QSpinBox(); self.sp_songs.setRange(1,10); self.sp_songs.setValue(2)
        self.sld_gpu    = _mk_slider(10,100,100)
        self.chk_2s     = QCheckBox("Використовувати відео ≥ 2с"); self.chk_2s.setChecked(True)
        self.chk_until  = QCheckBox("Поки є матеріал"); self.chk_until.setChecked(False)
        self.chk_album  = QCheckBox("Альбом-режим")
        self.ed_album   = QLineEdit("00:30:00"); self.ed_album.setToolTip("hh:mm:ss (час альбому)")
        self.ed_album.setEnabled(False); self.chk_album.toggled.connect(self.ed_album.setEnabled)
        self.btn_clear_cache = QPushButton("Очистити кеш")
        self.btn_reset_session = QPushButton("Reset сесії")

        gr.addWidget(self.chk_gpu, r,0); gr.addWidget(self.cmb_gpu, r,1)
        gr.addWidget(QLabel("GPU Preset:"), r,2); gr.addWidget(self.cmb_preset, r,3); r+=1
        gr.addWidget(QLabel("Threads:"), r,0); gr.addWidget(self.sp_threads, r,1)
        gr.addWidget(QLabel("Паралельно (jobs):"), r,2); gr.addWidget(self.sp_jobs, r,3); r+=1
        gr.addWidget(QLabel("К-ть пісень:"), r,0); gr.addWidget(self.sp_songs, r,1)
        gr.addWidget(QLabel("Max GPU load (%):"), r,2); gr.addWidget(self.sld_gpu, r,3); r+=1
        gr.addWidget(self.chk_2s, r,0); gr.addWidget(self.chk_until, r,1)
        gr.addWidget(self.chk_album, r,2); gr.addWidget(self.ed_album, r,3); r+=1
        gr.addWidget(self.btn_clear_cache, r,0,1,2); gr.addWidget(self.btn_reset_session, r,2,1,2)
        rwl.addWidget(g_r)
        self.right_split.addWidget(render_w)

        # 3) Превʼю: ліворуч вертикальні формати, праворуч превʼю
        preview_w = QWidget(); pv = QVBoxLayout(preview_w); pv.setContentsMargins(10,0,10,0)
        g_pv = QGroupBox("Превʼю (онлайн)"); pvl = QVBoxLayout(g_pv)

        row = QHBoxLayout(); row.setSpacing(10)
        self.fmt_selector = FormatSelectorVertical(self)

        # превʼю
        self.preview = QLabel(" "); self.preview.setMinimumHeight(240)
        self.preview.setStyleSheet("background:#141414;border:1px solid #333; border-radius:12px;")
        self.preview.setAlignment(Qt.AlignCenter)

        row.addWidget(self.fmt_selector, 1)
        row.addWidget(self.preview, 2)

        btns = QHBoxLayout(); btns.addStretch(1)
        self.btn_apply = QPushButton("Застосувати"); btns.addWidget(self.btn_apply)

        pvl.addLayout(row)
        pvl.addLayout(btns)
        pv.addWidget(g_pv)
        self.right_split.addWidget(preview_w)

        # 4) Звіт (готові треки)
        report_w = QWidget(); rp = QVBoxLayout(report_w); rp.setContentsMargins(10,0,10,0)
        g_rep = QGroupBox("Звіт (готові треки)"); rpl = QVBoxLayout(g_rep)
        self.report = QPlainTextEdit(); self.report.setReadOnly(True)
        self.report.setMaximumBlockCount(500)
        self.report.setStyleSheet("background:#141414; border:1px solid #262626; border-radius:10px;")
        rpl.addWidget(self.report)
        rp.addWidget(g_rep)
        self.right_split.addWidget(report_w)

        # 5) ЛОГИ технічні (всередині сторінки)
        tech_w = QWidget(); tl = QVBoxLayout(tech_w); tl.setContentsMargins(10,0,10,0)
        g_tech = QGroupBox("ЛОГИ технічні"); gt = QVBoxLayout(g_tech)
        self.techlog = QPlainTextEdit(); self.techlog.setReadOnly(True)
        self.techlog.setMaximumBlockCount(2000)
        self.techlog.setStyleSheet("background:#0F0F0F; border:1px solid #202020; border-radius:10px;")
        gt.addWidget(self.techlog); tl.addWidget(g_tech)
        self.right_split.addWidget(tech_w)

        # 6) Прогрес
        progress_w = QWidget(); pr = QVBoxLayout(progress_w); pr.setContentsMargins(10,0,10,10)
        g_prog = QGroupBox("Прогрес"); prl = QVBoxLayout(g_prog)
        self.progress = QProgressBar(); self.progress.setValue(0)
        prl.addWidget(self.progress); pr.addWidget(g_prog)
        self.right_split.addWidget(progress_w)

        # Пропорції
        self.main_split.setStretchFactor(0, 3)
        self.main_split.setStretchFactor(1, 2)
        self.left_split.setStretchFactor(0, 1)  # пресети
        self.left_split.setStretchFactor(1, 4)  # еквалайзер
        self.left_split.setStretchFactor(2, 3)  # ефекти
        self.left_split.setStretchFactor(3, 2)  # рух
        self.right_split.setStretchFactor(0, 2)  # папки
        self.right_split.setStretchFactor(1, 3)  # рендер
        self.right_split.setStretchFactor(2, 5)  # превʼю (з форматами)
        self.right_split.setStretchFactor(3, 2)  # звіт
        self.right_split.setStretchFactor(4, 3)  # технічні логи
        self.right_split.setStretchFactor(5, 1)  # прогрес
        
        # ---- Події/звʼязки ----
        self.btn_apply.clicked.connect(self._on_apply)
        self.btn_clear_cache.clicked.connect(self._clear_cache)
        self.btn_reset_session.clicked.connect(self._reset_session)
        self.btn_save_preset.clicked.connect(self._save_preset)
        self.btn_delete_preset.clicked.connect(self._delete_preset)
        self.presets_combo.currentIndexChanged.connect(self._load_preset)

        # Приховані системні комбо (логіку не чіпаємо)
        self.cmb_format = QComboBox()
        self.cmb_format.addItems(["FHD", "Shorts", "4K"])
        self.cmb_format.setVisible(False)

        self.cmb_res = QComboBox()
        self.cmb_res.addItems([
            "YouTube FHD 1920x1080 30fps",
            "YouTube Shorts 1080x1920 30fps",
            "Instagram 4:5 1080x1350 30fps",
            "Instagram 1:1 1080x1080 30fps",
            "Facebook 4:5 1080x1350 30fps",
            "Facebook 1:1 1080x1080 30fps",
            "4K 3840x2160 30fps",
        ])
        self.cmb_res.setVisible(False)

        # Вибір картки формату → синхронізуємо приховані комбо
        def _apply_fmt_from_card(key: str):
            def ensure_res(text: str):
                if self.cmb_res.findText(text) == -1:
                    self.cmb_res.addItem(text)
                self.cmb_res.setCurrentText(text)

            if key == "youtube_16_9":
                self.cmb_format.setCurrentText("FHD")
                ensure_res("YouTube FHD 1920x1080 30fps")
            elif key in ("shorts_9_16", "ig_reels_9_16", "tiktok_9_16"):
                self.cmb_format.setCurrentText("Shorts")
                ensure_res("YouTube Shorts 1080x1920 30fps")
            elif key in ("ig_4_5", "fb_4_5"):
                self.cmb_format.setCurrentText("FHD")
                ensure_res("Instagram 4:5 1080x1350 30fps")
            elif key in ("ig_1_1", "fb_1_1"):
                self.cmb_format.setCurrentText("FHD")
                ensure_res("Instagram 1:1 1080x1080 30fps")

            self._update_preview(initial=False)

        self.fmt_selector.selected.connect(_apply_fmt_from_card)

        # Живе превʼю (дебаунс) — ПОВʼЯЗАНО з еквалайзером/ефектами
        self._live_timer = QTimer(self)
        self._live_timer.setInterval(120)
        self._live_timer.setSingleShot(True)

        def _arm():
            if not self._live_timer.isActive():
                self._live_timer.start()

        self._live_timer.timeout.connect(lambda: self._update_preview(initial=False))

        for w in (
            self.eq_enabled, self.eq_engine, self.eq_mode, self.eq_bars, self.eq_thick, self.eq_height,
            self.eq_fullscr, self.eq_yoffset, self.eq_mirror, self.eq_baseline, self.eq_opacity,
            self.st_enabled, self.st_style, self.st_count, self.st_int, self.st_size, self.st_pulse,
            self.st_opacity, self.st_time_factor,
            self.rn_enabled, self.rn_count, self.rn_length, self.rn_thick, self.rn_angle, self.rn_speed, self.rn_opacity,
            self.sm_enabled, self.sm_density, self.sm_opacity, self.sm_speed,
            self.mv_enabled, self.mv_dir, self.mv_speed, self.mv_amount, self.mv_osc, self.mv_rotdeg, self.mv_rothz,
            self.mv_shpx, self.mv_shz, self.cmb_res, self.cmb_format
        ):
            if hasattr(w, "toggled"):
                w.toggled.connect(_arm)
            if hasattr(w, "valueChanged"):
                w.valueChanged.connect(_arm)
            if hasattr(w, "currentIndexChanged"):
                w.currentIndexChanged.connect(_arm)
            if hasattr(w, "currentTextChanged"):
                w.currentTextChanged.connect(_arm)

        # --- ІНІТ / ФІКСИ ПІД ТЗ ---
        self._load_config()
        self._load_presets()
        self._sync_format_res()
        self._update_preview(initial=True)

        # 1) Локальні логи об'єднані: звіт + технічні → в self.report
        self._log_target = self.report
        if hasattr(self, "techlog") and self.techlog:
            try:
                self.techlog.hide()
            except Exception:
                pass

        # 2) Прибрати локальний прогрес-бар, віддати місце під логове вікно
        try:
            pg = self.progress.parentWidget().parentWidget()
            pg.hide()
        except Exception:
            try:
                self.progress.hide()
            except Exception:
                pass
        try:
            self.right_split.setStretchFactor(3, 5)  # логи більше
            self.right_split.setStretchFactor(4, 0)  # прихований прогрес
        except Exception:
            pass

        # 3) Превʼю ФІКСОВАНЕ — не «стрибає» при змінах
        self.preview.setFixedHeight(260)          # піджени якщо треба
        self.preview.setMinimumWidth(520)
        self.preview.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    # -------------------- СТАТУС / ГЛОБАЛЬНИЙ ЛОГ --------------------
    def _status(self, msg: str):
        """
        У ПРАВИЙ глобальний лог пускаємо тільки підсумок та помилки.
        """
        if msg.startswith("✅ Готово:") or msg.startswith("❌"):
            self.sig_biglog.emit(msg)

    # -------------------- ХЕЛПЕРИ --------------------
    def _append_log(self, text: str):
        """Єдине велике логове вікно під превʼю."""
        try:
            self._log_target.appendPlainText(text)
        except Exception:
            self.report.appendPlainText(text)

    def _get_WH_fps(self) -> Tuple[int, int, int]:
        txt = self.cmb_res.currentText()
        try:
            wh = [p for p in txt.split() if "x" in p][0]
            w, h = map(int, wh.split("x"))
            fps = int([p for p in txt.split() if "fps" in p][0].replace("fps", ""))
            return w, h, fps
        except Exception:
            return 1920, 1080, 30

    def _sync_format_res(self):
        m = self.cmb_format.currentText()
        mapping = {
            "Shorts": "YouTube Shorts 1080x1920 30fps",
            "FHD":    "YouTube FHD 1920x1080 30fps",
            "4K":     "4K 3840x2160 30fps",
        }
        self.cmb_res.setCurrentText(mapping.get(m, "YouTube FHD 1920x1080 30fps"))
        self._update_preview(initial=False)

    # -------------------- ЗБІР UI → DICT --------------------
    def _build_eq_dict(self) -> Dict:
        return {
            "enabled": self.eq_enabled.isChecked(),
            "engine": self.eq_engine.currentText(),
            "mode": self.eq_mode.currentText(),
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
        return {
            "enabled": self.st_enabled.isChecked(),
            "style": self.st_style.currentText(),
            "count": self.st_count.value(),
            "intensity": _pct(self.st_int),
            "size": self.st_size.value(),
            "pulse": int(self.st_pulse.value()),
            "color": _hex(self.st_color.color()),
            "opacity": _pct(self.st_opacity),
            "time_factor": float(self.st_time_factor.value()),
        }

    def _build_rain_dict(self) -> Dict:
        return {
            "enabled": self.rn_enabled.isChecked(),
            "count": self.rn_count.value(),
            "length": self.rn_length.value(),
            "thickness": self.rn_thick.value(),
            "angle_deg": float(self.rn_angle.value()),
            "speed": float(self.rn_speed.value()),
            "color": _hex(self.rn_color.color()),
            "opacity": _pct(self.rn_opacity),
        }

    def _build_smoke_dict(self) -> Dict:
        return {
            "enabled": self.sm_enabled.isChecked(),
            "density": self.sm_density.value(),
            "color": _hex(self.sm_color.color()),
            "opacity": _pct(self.sm_opacity),
            "speed": float(self.sm_speed.value()),
        }

    def _build_motion_dict(self) -> Dict:
        return {
            "enabled": self.mv_enabled.isChecked(),
            "direction": self.mv_dir.currentText(),
            "speed": float(self.mv_speed.value()),
            "amount": float(self.mv_amount.value()),
            "oscillate": self.mv_osc.isChecked(),
            "rot_deg": float(self.mv_rotdeg.value()),
            "rot_hz": float(self.mv_rothz.value()),
            "shake_px": float(self.mv_shpx.value()),
            "shake_hz": float(self.mv_shz.value()),
        }

    # -------------------- ПРЕВʼЮ --------------------
    def _base_pm(self, W: int, H: int) -> QPixmap:
        pm = QPixmap(W, H)
        pm.fill(QColor("#000"))
        return pm

    def _update_preview(self, initial: bool = False):
        """
        Фіксоване вікно превʼю: змінюється лише картинка, не геометрія QLabel.
        """
        W, H, _ = self._get_WH_fps()
        pm = QPixmap(self._base_pm(W, H))
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)

        eq = self._build_eq_dict()
        if eq["enabled"]:
            p.drawPixmap(0, 0, make_eq_overlay(eq, W, H))
        st = self._build_stars_dict()
        if st["enabled"]:
            p.drawPixmap(0, 0, make_stars_overlay(st, W, H))
        rn = self._build_rain_dict()
        if rn["enabled"]:
            p.drawPixmap(0, 0, make_rain_overlay(rn, W, H))
        sm = self._build_smoke_dict()
        if sm["enabled"]:
            p.drawPixmap(0, 0, make_smoke_overlay(sm, W, H))
        mv = self._build_motion_dict()
        if mv["enabled"]:
            draw_motion_indicator(p, pm.rect(), mv)

        p.end()

        self.preview.setPixmap(pm.scaled(
            self.preview.width(), self.preview.height(),
            Qt.KeepAspectRatio, Qt.SmoothTransformation
        ))

    # -------------------- КОНФІГ --------------------
    def _build_cfg(self) -> Dict:
        W, H, fps = self._get_WH_fps()
        return {
            "music_dir": _ensure_dir(self.p_music.text()),
            "media_dir": _ensure_dir(self.p_media.text()),
            "out_dir":   _ensure_dir(self.p_out.text()),
            "resolution": f"{W}x{H} {fps}fps",
            "gpu": self.cmb_gpu.currentText() if self.chk_gpu.isChecked() else "cpu",
            "use_gpu": self.chk_gpu.isChecked(),
            "gpu_preset": self.cmb_preset.currentText(),
            "threads": int(self.sp_threads.value()),
            "jobs": int(self.sp_jobs.value()),
            "songs": int(self.sp_songs.value()),
            "gpu_load": _pct(self.sld_gpu),
            "use_video_ge2s": bool(self.chk_2s.isChecked()),
            "until_material": bool(self.chk_until.isChecked()),
            "album_enabled": bool(self.chk_album.isChecked()),
            "album_sec": _mmss_to_seconds(self.ed_album.text()) if self.chk_album.isChecked() else 0,
            "eq_ui": self._build_eq_dict(),
            "stars_ui": self._build_stars_dict(),
            "rain_ui": self._build_rain_dict(),
            "smoke_ui": self._build_smoke_dict(),
            "motion_ui": self._build_motion_dict(),
        }

    def _save_config(self):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self._build_cfg(), f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load_config(self):
        try:
            if not os.path.isfile(CONFIG_FILE):
                return
            cfg = json.load(open(CONFIG_FILE, "r", encoding="utf-8"))

            self.p_music.setText(cfg.get("music_dir", ""))
            self.p_media.setText(cfg.get("media_dir", ""))
            self.p_out.setText(cfg.get("out_dir", ""))
            self.cmb_res.setCurrentText(cfg.get("resolution", "YouTube FHD 1920x1080 30fps"))

            self.chk_gpu.setChecked(cfg.get("use_gpu", True))
            self.cmb_gpu.setCurrentText(cfg.get("gpu", "auto"))
            self.cmb_preset.setCurrentText(cfg.get("gpu_preset", "auto/balanced"))
            self.sp_threads.setValue(int(cfg.get("threads", 16)))
            self.sp_jobs.setValue(int(cfg.get("jobs", 1)))
            self.sp_songs.setValue(int(cfg.get("songs", 1)))
            self.sld_gpu.setValue(int(cfg.get("gpu_load", 100)))
            self.chk_2s.setChecked(bool(cfg.get("use_video_ge2s", True)))
            self.chk_until.setChecked(bool(cfg.get("until_material", False)))
            self.chk_album.setChecked(bool(cfg.get("album_enabled", False)))
            if cfg.get("album_enabled", False):
                self.ed_album.setText(_seconds_to_mmss(int(cfg.get("album_sec", 0))))
                self.ed_album.setEnabled(True)

            if "eq_ui" in cfg:
                eq = cfg["eq_ui"]
                self.eq_enabled.setChecked(eq.get("enabled", False))
                self.eq_engine.setCurrentText(eq.get("engine", "waves"))
                self.eq_mode.setCurrentText(eq.get("mode", "bar"))
                self.eq_bars.setValue(eq.get("bars", 96))
                self.eq_thick.setValue(eq.get("thickness", 3))
                self.eq_height.setValue(eq.get("height", 360))
                self.eq_fullscr.setChecked(eq.get("fullscreen", False))
                self.eq_yoffset.setValue(eq.get("y_offset", 0))
                self.eq_mirror.setChecked(eq.get("mirror", True))
                self.eq_baseline.setChecked(eq.get("baseline", False))
                self.eq_color.setColor(QColor(eq.get("color", "#FFFFFF")))
                self.eq_opacity.setValue(eq.get("opacity", 90))

            if "stars_ui" in cfg:
                st = cfg["stars_ui"]
                self.st_enabled.setChecked(st.get("enabled", False))
                self.st_style.setCurrentText(st.get("style", "classic"))
                self.st_count.setValue(st.get("count", 200))
                self.st_int.setValue(st.get("intensity", 55))
                self.st_size.setValue(st.get("size", 2))
                self.st_pulse.setValue(st.get("pulse", 40))
                self.st_color.setColor(QColor(st.get("color", "#FFFFFF")))
                self.st_opacity.setValue(st.get("opacity", 70))
                self.st_time_factor.setValue(st.get("time_factor", 1.0))

            if "rain_ui" in cfg:
                rn = cfg["rain_ui"]
                self.rn_enabled.setChecked(rn.get("enabled", False))
                self.rn_count.setValue(rn.get("count", 1200))
                self.rn_length.setValue(rn.get("length", 40))
                self.rn_thick.setValue(rn.get("thickness", 2))
                self.rn_angle.setValue(rn.get("angle_deg", 15.0))
                self.rn_speed.setValue(rn.get("speed", 160.0))
                self.rn_color.setColor(QColor(rn.get("color", "#9BE2FF")))
                self.rn_opacity.setValue(rn.get("opacity", 55))

            if "smoke_ui" in cfg:
                sm = cfg["smoke_ui"]
                self.sm_enabled.setChecked(sm.get("enabled", False))
                self.sm_density.setValue(sm.get("density", 60))
                self.sm_color.setColor(QColor(sm.get("color", "#A0A0A0")))
                self.sm_opacity.setValue(sm.get("opacity", 35))
                self.sm_speed.setValue(sm.get("speed", 12.0))

            if "motion_ui" in cfg:
                mv = cfg["motion_ui"]
                self.mv_enabled.setChecked(mv.get("enabled", False))
                self.mv_dir.setCurrentText(mv.get("direction", "lr"))
                self.mv_speed.setValue(mv.get("speed", 10.0))
                self.mv_amount.setValue(mv.get("amount", 5.0))
                self.mv_osc.setChecked(mv.get("oscillate", True))
                self.mv_rotdeg.setValue(mv.get("rot_deg", 8.0))
                self.mv_rothz.setValue(mv.get("rot_hz", 0.10))
                self.mv_shpx.setValue(mv.get("shake_px", 6.0))
                self.mv_shz.setValue(mv.get("shake_hz", 1.2))
        except Exception:
            pass

    # -------------------- ПРЕСЕТИ --------------------
    def _load_presets(self):
        try:
            if os.path.isfile(USER_PRESETS_FILE):
                with open(USER_PRESETS_FILE, "r", encoding="utf-8") as f:
                    presets = json.load(f)
                self.presets_combo.clear()
                for name in presets.keys():
                    self.presets_combo.addItem(name)
        except Exception:
            pass

    def _save_preset(self):
        name, ok = QInputDialog.getText(self, "Збереження пресету", "Введіть назву пресету:")
        if not ok or not name:
            return
        try:
            presets = {}
            if os.path.isfile(USER_PRESETS_FILE):
                with open(USER_PRESETS_FILE, "r", encoding="utf-8") as f:
                    presets = json.load(f)
            presets[name] = self._build_cfg()
            if len(presets) > 20:
                presets.pop(next(iter(presets)))
            with open(USER_PRESETS_FILE, "w", encoding="utf-8") as f:
                json.dump(presets, f, ensure_ascii=False, indent=2)
            self._load_presets()
            self.presets_combo.setCurrentText(name)
        except Exception:
            pass

    def _delete_preset(self):
        name = self.presets_combo.currentText()
        if not name:
            return
        try:
            presets = {}
            if os.path.isfile(USER_PRESETS_FILE):
                with open(USER_PRESETS_FILE, "r", encoding="utf-8") as f:
                    presets = json.load(f)
            if name in presets:
                del presets[name]
                with open(USER_PRESETS_FILE, "w", encoding="utf-8") as f:
                    json.dump(presets, f, ensure_ascii=False, indent=2)
                self._load_presets()
        except Exception:
            pass

    def _load_preset(self):
        name = self.presets_combo.currentText()
        if not name:
            return
        try:
            if not os.path.isfile(USER_PRESETS_FILE):
                return
            with open(USER_PRESETS_FILE, "r", encoding="utf-8") as f:
                presets = json.load(f)
            cfg = presets.get(name)
            if not cfg:
                return

            self.p_music.setText(cfg.get("music_dir", ""))
            self.p_media.setText(cfg.get("media_dir", ""))
            self.p_out.setText(cfg.get("out_dir", ""))
            self.cmb_res.setCurrentText(cfg.get("resolution", "YouTube FHD 1920x1080 30fps"))
            self.chk_gpu.setChecked(cfg.get("use_gpu", True))
            self.cmb_gpu.setCurrentText(cfg.get("gpu", "auto"))
            self.cmb_preset.setCurrentText(cfg.get("gpu_preset", "auto/balanced"))
            self.sp_threads.setValue(int(cfg.get("threads", 16)))
            self.sp_jobs.setValue(int(cfg.get("jobs", 1)))
            self.sp_songs.setValue(int(cfg.get("songs", 1)))
            self.sld_gpu.setValue(int(cfg.get("gpu_load", 100)))
            self.chk_2s.setChecked(bool(cfg.get("use_video_ge2s", True)))
            self.chk_until.setChecked(bool(cfg.get("until_material", False)))
            self.chk_album.setChecked(bool(cfg.get("album_enabled", False)))
            if cfg.get("album_enabled", False):
                self.ed_album.setText(_seconds_to_mmss(int(cfg.get("album_sec", 0))))
                self.ed_album.setEnabled(True)
            else:
                self.ed_album.setEnabled(False)

            # підсекції як у _load_config()
            if "eq_ui" in cfg:
                eq = cfg["eq_ui"]
                self.eq_enabled.setChecked(eq.get("enabled", False))
                self.eq_engine.setCurrentText(eq.get("engine", "waves"))
                self.eq_mode.setCurrentText(eq.get("mode", "bar"))
                self.eq_bars.setValue(eq.get("bars", 96))
                self.eq_thick.setValue(eq.get("thickness", 3))
                self.eq_height.setValue(eq.get("height", 360))
                self.eq_fullscr.setChecked(eq.get("fullscreen", False))
                self.eq_yoffset.setValue(eq.get("y_offset", 0))
                self.eq_mirror.setChecked(eq.get("mirror", True))
                self.eq_baseline.setChecked(eq.get("baseline", False))
                self.eq_color.setColor(QColor(eq.get("color", "#FFFFFF")))
                self.eq_opacity.setValue(eq.get("opacity", 90))

            if "stars_ui" in cfg:
                st = cfg["stars_ui"]
                self.st_enabled.setChecked(st.get("enabled", False))
                self.st_style.setCurrentText(st.get("style", "classic"))
                self.st_count.setValue(st.get("count", 200))
                self.st_int.setValue(st.get("intensity", 55))
                self.st_size.setValue(st.get("size", 2))
                self.st_pulse.setValue(st.get("pulse", 40))
                self.st_color.setColor(QColor(st.get("color", "#FFFFFF")))
                self.st_opacity.setValue(st.get("opacity", 70))
                self.st_time_factor.setValue(st.get("time_factor", 1.0))

            if "rain_ui" in cfg:
                rn = cfg["rain_ui"]
                self.rn_enabled.setChecked(rn.get("enabled", False))
                self.rn_count.setValue(rn.get("count", 1200))
                self.rn_length.setValue(rn.get("length", 40))
                self.rn_thick.setValue(rn.get("thickness", 2))
                self.rn_angle.setValue(rn.get("angle_deg", 15.0))
                self.rn_speed.setValue(rn.get("speed", 160.0))
                self.rn_color.setColor(QColor(rn.get("color", "#9BE2FF")))
                self.rn_opacity.setValue(rn.get("opacity", 55))

            if "smoke_ui" in cfg:
                sm = cfg["smoke_ui"]
                self.sm_enabled.setChecked(sm.get("enabled", False))
                self.sm_density.setValue(sm.get("density", 60))
                self.sm_color.setColor(QColor(sm.get("color", "#A0A0A0")))
                self.sm_opacity.setValue(sm.get("opacity", 35))
                self.sm_speed.setValue(sm.get("speed", 12.0))

            if "motion_ui" in cfg:
                mv = cfg["motion_ui"]
                self.mv_enabled.setChecked(mv.get("enabled", False))
                self.mv_dir.setCurrentText(mv.get("direction", "lr"))
                self.mv_speed.setValue(mv.get("speed", 10.0))
                self.mv_amount.setValue(mv.get("amount", 5.0))
                self.mv_osc.setChecked(mv.get("oscillate", True))
                self.mv_rotdeg.setValue(mv.get("rot_deg", 8.0))
                self.mv_rothz.setValue(mv.get("rot_hz", 0.10))
                self.mv_shpx.setValue(mv.get("shake_px", 6.0))
                self.mv_shz.setValue(mv.get("shake_hz", 1.2))

            self._update_preview()
        except Exception:
            pass

    # -------------------- СТАРТ/СТОП --------------------
    def _clear_report(self):
        self.report.setPlainText("")

    def _append_report(self, text: str):
        # тепер звіт також пишемо в єдине логове вікно
        self._append_log(text)

    def _on_apply(self):
        self._update_preview()
        self._save_config()

    def _start(self):
        if self._running:
            return

        # Новий запуск → чисті логи
        self._clear_report()
        try:
            if hasattr(self, "host") and hasattr(self.host, "clear_logs"):
                self.host.clear_logs()  # чистимо правий глобальний лог
        except Exception:
            pass

        cfg = self._build_cfg()
        self._songs_total = int(cfg.get("songs", 1))
        self._songs_done = 0

        if not cfg["music_dir"] or not cfg["out_dir"]:
            QMessageBox.warning(self, "Помилка", "Заповніть папки Музика та Вихід.")
            return

        try:
            with open(os.path.join(CACHE_DIR, "cfg_dump.json"), "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

        self._save_config()
        try:
            self.cancel_event.clear()
            self._running = True
            self.sig_running.emit(True)
            start_video_jobs(cfg, self.status_q, self.cancel_event)
            self.poll_timer.start()
        except Exception:
            self._running = False
            self.sig_running.emit(False)

    def _stop(self):
        try:
            self.cancel_event.set()
            stop_all_jobs()
            self.poll_timer.stop()
            while True:
                try:
                    self.status_q.get_nowait()
                except queue.Empty:
                    break
        finally:
            self.cancel_event.clear()
            self._running = False
            self.sig_running.emit(False)

    # --- кеш / сесія ---
    def _clear_cache(self):
        try:
            if os.path.isdir(CACHE_DIR):
                shutil.rmtree(CACHE_DIR, ignore_errors=True)
            os.makedirs(CACHE_DIR, exist_ok=True)
        except Exception:
            pass

    def _reset_session_state(self):
        try:
            while True:
                self.status_q.get_nowait()
        except queue.Empty:
            pass
        try:
            if os.path.isdir(STAGE_DIR):
                shutil.rmtree(STAGE_DIR, ignore_errors=True)
        except Exception:
            pass

    def _reset_session(self):
        try:
            self._stop()
        except Exception:
            pass
        self._reset_session_state()
        try:
            reset_processing_state()
        except Exception:
            pass

    # -------------------- ПОЛІНГ ВОРКЕРА --------------------
    @Slot()
    def _poll(self):
        while True:
            try:
                msg = self.status_q.get_nowait()
            except queue.Empty:
                break

            t = msg.get("type")
            if t == "start":
                self._append_log("▶ Старт рендеру")
            elif t == "log":
                # Тільки в локальне велике вікно
                s = msg.get("msg", "")
                self._append_log(s)
            elif t == "progress":
                # Глобальний прогрес (у Main), локального прогрес-бару нема
                try:
                    v = int(msg.get("value", 0))
                    self.sig_progress.emit(v, "Рендеринг")
                except Exception:
                    pass
            elif t == "done":
                outp = msg.get("output", "")
                self._songs_done += 1
                self._append_log(f"✅ Готово: {outp}")   # локально
                self._status(f"✅ Готово: {outp}")       # у правий глобальний лог
                if self._songs_done >= max(1, self._songs_total):
                    self.poll_timer.stop()
                    self._running = False
                    self.sig_running.emit(False)
            elif t == "error":
                em = msg.get("msg", "")
                self._append_log(f"❌ {em}")
                self._status(f"❌ {em}")
                self.poll_timer.stop()
                self._running = False
                self.sig_running.emit(False)

    # -------------------- ІНТЕГРАЦІЯ З ХОСТОМ --------------------
    def handle_start(self, auto_mode: bool):
        self._start()

    def handle_stop(self):
        self._stop()

    def set_host(self, host):
        self.host = host
        try:
            # глобальний правий лог — керуємо через _status()
            self.sig_progress.connect(lambda val, lbl="Відео": host.set_progress(self, int(val), lbl))
            self.sig_running.connect(lambda running: host.set_running(self, bool(running)))
        except Exception:
            pass

    # -------------------- МАСШТАБУВАННЯ 15″→34″ --------------------
    def apply_scale(self, scale: float):
        """Пропорційне масштабування всього UI (іконки, тексти, логи)."""
        f = self.font()
        f.setPointSize(max(9, int(10 * scale)))
        self.setFont(f)

        # Превʼю фіксоване — лише картинка масштабується всередині
        self.preview.setFixedHeight(max(220, int(260 * scale)))
        self.preview.setMinimumWidth(max(480, int(520 * scale)))

        # Кнопки
        btn_h = max(28, int(34 * scale))
        for b in (self.btn_apply, self.btn_clear_cache, self.btn_reset_session,
                  self.btn_save_preset, self.btn_delete_preset):
            b.setMinimumHeight(btn_h)

        # Логове вікно — моноширинний та масштабований
        mono = self.report.font()
        mono.setPointSize(max(8, int(10 * scale)))
        try:
            self.report.setFont(mono)
        except Exception:
            pass

        # Картки форматів
        if hasattr(self, "fmt_selector"):
            self.fmt_selector.apply_scale(scale)
       