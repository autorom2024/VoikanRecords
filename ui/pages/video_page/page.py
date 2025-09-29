# -*- coding: utf-8 -*-
from __future__ import annotations
"""
VideoPage — фінальна версія з урахуванням всіх побажань.
Оптимізовано для уникнення зависання UI та покращено налаштування ефектів.
"""

import os
import json
import queue
import shutil
import threading
from typing import Dict, Tuple, Optional, Any

# <--- ВИПРАВЛЕННЯ 1: Додано блок імпорту для psutil та GPUtil ---
# Для моніторингу ресурсів. Встановіть командою: pip install psutil gputil
try:
    import psutil
except ImportError:
    psutil = None
try:
    import GPUtil
except ImportError:
    GPUtil = None

from PySide6.QtCore import Qt, QTimer, Signal, Slot, QRectF
from PySide6.QtGui import (
    QPixmap, QColor, QPainter, QFont, QPainterPath, QPen
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
    try:
        from logic.video_backend import start_video_jobs, stop_all_jobs, reset_processing_state
        from logic.effects_render import (
            make_eq_overlay, make_stars_overlay, make_rain_overlay, make_smoke_overlay,
            draw_motion_indicator,
        )
    except ImportError:
        print("ПОПЕРЕДЖЕННЯ: Не вдалося знайти бекенд. Використовуються заглушки для тестування UI.")
        def start_video_jobs(cfg, queue, event):
            import time
            for i in range(10):
                if event.is_set(): break
                time.sleep(0.5)
                queue.put({"type": "log", "msg": f"Тестовий лог #{i+1}"})
            queue.put({"type": "done", "output": "test_video.mp4"})
        def stop_all_jobs(): pass
        def reset_processing_state(): pass
        def make_eq_overlay(eq, w, h): p = QPixmap(w, h); p.fill(Qt.transparent); return p
        def make_stars_overlay(st, w, h): p = QPixmap(w, h); p.fill(Qt.transparent); return p
        def make_rain_overlay(rn, w, h): p = QPixmap(w, h); p.fill(Qt.transparent); return p
        def make_smoke_overlay(sm, w, h): p = QPixmap(w, h); p.fill(Qt.transparent); return p
        def draw_motion_indicator(painter, rect, mv_cfg): pass

CACHE_DIR = os.path.join("_cache", "video_ui")
STAGE_DIR = os.path.join(CACHE_DIR, "playlist_stage")
os.makedirs(CACHE_DIR, exist_ok=True)

CONFIG_FILE = os.path.join(CACHE_DIR, "video_qt_config.json")
USER_PRESETS_FILE = os.path.join(CACHE_DIR, "video_user_presets.json")

# ------------------------ REFINED DARK BLUE THEME ------------------------
THEME_CSS = """
QWidget {
    background-color: #0D1117; color: #C9D1D9;
    font-family: 'Segoe UI', 'Roboto', sans-serif; font-size: 14px;
}
QLabel, QCheckBox, QRadioButton { background-color: transparent; }
QGroupBox {
    background-color: #161B22; border: 1px solid #30363D; border-radius: 8px;
    margin-top: 18px; padding: 12px;
}
QGroupBox > QWidget { background-color: transparent; }
QGroupBox::title {
    subcontrol-origin: margin; left: 14px; padding: 0 8px;
    color: #C9D1D9; font-size: 15px; font-weight: 600;
}
QPushButton {
    background-color: #21262D; border: 1px solid #30363D; border-radius: 6px;
    padding: 8px 16px; color: #C9D1D9; font-weight: 500; min-height: 28px;
}
QPushButton:hover { background-color: #30363D; border-color: #8B949E; }
QPushButton:pressed { background-color: #21262D; }
QPushButton:disabled { background-color: #161B22; color: #484F58; border-color: #30363D; }
QPushButton[cssClass="accent"] { background-color: #238636; color: #ffffff; border: 1px solid #2ea043; }
QPushButton[cssClass="accent"]:hover { background-color: #2ea043; }
QPushButton[cssClass="accent"]:pressed { background-color: #238636; }
QPushButton[cssClass="blue_accent"] { background-color: #1F6FEB; color: #ffffff; border: 1px solid #388BFD; }
QPushButton[cssClass="blue_accent"]:hover { background-color: #388BFD; }
QPushButton[cssClass="blue_accent"]:pressed { background-color: #1F6FEB; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit {
    background-color: #0D1117; border: 1px solid #30363D; border-radius: 6px;
    padding: 7px 12px; color: #C9D1D9; selection-background-color: #1F6FEB;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QPlainTextEdit:focus {
    border-color: #1F6FEB;
}
QPlainTextEdit { font-family: "Consolas", "Courier New", monospace; font-size: 13px; background-color: #161B22; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator {
    width: 18px; height: 18px; border: 1px solid #30363D;
    border-radius: 4px; background-color: #0D1117;
}
QCheckBox::indicator:hover { border-color: #8B949E; }
QCheckBox::indicator:checked {
    background-color: #1F6FEB; border-color: #1F6FEB;
    image: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>');
}
QComboBox::drop-down { border: none; width: 24px; background: transparent; }
QComboBox::down-arrow { image: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="%238B949E" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"></polyline></svg>'); }
QComboBox QAbstractItemView {
    background-color: #161B22; border: 1px solid #30363D; border-radius: 8px;
    selection-background-color: #1F6FEB; color: #C9D1D9; padding: 4px;
}
QSlider::groove:horizontal {
    height: 4px;
    background: #30363D;
    border: none;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    width: 18px; height: 18px; margin: -7px 0;
    border-radius: 9px; background: #8B949E;
}
QSlider::handle:horizontal:hover { background: #C9D1D9; }
QProgressBar {
    background-color: #161B22; border: 1px solid #30363D; border-radius: 8px;
    text-align: center; padding: 1px; color: #C9D1D9; font-weight: 600;
}
QProgressBar::chunk { border-radius: 7px; background-color: #1F6FEB; }
QScrollBar:vertical { background: #0D1117; width: 12px; border-radius: 6px; margin: 0; }
QScrollBar::handle:vertical { background: #21262D; border-radius: 6px; min-height: 25px; }
QScrollBar::handle:vertical:hover { background: #30363D; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QSplitter::handle { background: #161B22; }
QSplitter::handle:hover { background: #1F6FEB; }
#SystemMonitorWidget QProgressBar {
    min-height: 22px; max-height: 22px; text-align: left;
    padding-left: 10px; font-size: 12px; font-weight: 600;
}
#SystemMonitorWidget QProgressBar::chunk { background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1F6FEB, stop:1 #388BFD); }
#SystemMonitorWidget QLabel { font-size: 13px; font-weight: 500; }
#EffectCard { background-color: #0D1117; border: 1px solid #30363D; border-radius: 6px; }
#EffectCard QPushButton {
    background-color: transparent; border: none; text-align: left;
    padding: 4px; color: #8B949E;
}
#EffectCard QPushButton:hover { color: #C9D1D9; }
#FormatCard {
    background-color: #161B22; border: 1px solid #30363D; border-radius: 8px;
    padding: 8px 14px;
}
#FormatCard:hover {
    border-color: #8B949E; background-color: #21262D;
}
#FormatCard[checked="true"] {
    background-color: #1F6FEB; border-color: #388BFD;
}
#FormatCard #titleLabel {
    font-size: 13px; font-weight: 600; color: #C9D1D9;
}
#FormatCard #subtitleLabel {
    font-size: 11px; color: #8B949E;
}
#FormatCard[checked="true"] #titleLabel { color: #FFFFFF; }
#FormatCard[checked="true"] #subtitleLabel { color: #D0D8E0; }
"""

# ------------------------ ІКОНКИ СОЦМЕРЕЖ ------------------------
def get_social_icon(brand: str) -> QPainterPath:
    path = QPainterPath()
    if brand == "youtube":
        path.addRoundedRect(QRectF(0, 2, 24, 16), 5, 5); path.moveTo(9, 6); path.lineTo(17, 10); path.lineTo(9, 14); path.closeSubpath()
    elif brand in ["ig", "instagram"]:
        path.addRoundedRect(QRectF(0, 0, 20, 20), 6, 6); path.addEllipse(QRectF(5, 5, 10, 10)); path.addEllipse(QRectF(15.5, 2.5, 2, 2))
    elif brand == "tiktok":
        path.moveTo(14, 2); path.arcTo(QRectF(7, 2, 7, 14), 90, 180); path.lineTo(14, 16); path.arcTo(QRectF(14, 4, 12, 12), 225, -90)
    elif brand == "facebook":
        path.addRoundedRect(QRectF(0, 0, 20, 20), 4, 4); path.moveTo(14, 20); path.lineTo(14, 12); path.lineTo(11, 12); path.arcTo(QRectF(7, 12, 4, 4), 90, -90); path.lineTo(11, 8); path.lineTo(8, 8)
    return path

# ------------------------ ДОПОМІЖНІ ФУНКЦІЇ ТА КЛАСИ ------------------------
def _ensure_dir(path: str) -> str: return path if path and os.path.isdir(path) else ""
def _hex(qc: QColor) -> str: return qc.name().upper()
def _mmss_to_seconds(text: str) -> int:
    try:
        parts = [int(x) for x in text.strip().split(":")]; return (parts[0] * 3600 + parts[1] * 60 + parts[2]) if len(parts) == 3 else (parts[0] * 60 + parts[1]) if len(parts) == 2 else int(parts[0])
    except: return 180
def _seconds_to_mmss(sec: int) -> str: sec = max(0, int(sec)); return f"{sec // 60:02d}:{sec % 60:02d}"

class SliderWithValueLabel(QWidget):
    valueChanged = Signal(float)
    def __init__(self, orientation=Qt.Horizontal, decimals=0, parent=None):
        super().__init__(parent)
        self.decimals = decimals
        self.slider = QSlider(orientation)
        self.value_label = QLineEdit()
        self.value_label.setFixedWidth(50)
        self.value_label.setAlignment(Qt.AlignCenter)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.slider)
        layout.addWidget(self.value_label)
        self.slider.valueChanged.connect(self._on_slider_change)
        self.value_label.editingFinished.connect(self._on_text_change)
    def _on_slider_change(self, value):
        real_value = value / (10 ** self.decimals)
        self.value_label.setText(f"{real_value:.{self.decimals}f}")
        self.valueChanged.emit(real_value)
    def _on_text_change(self):
        try:
            value = float(self.value_label.text())
            self.slider.setValue(int(value * (10 ** self.decimals)))
        except ValueError:
            self._on_slider_change(self.slider.value()) # Revert to slider value
    def setRange(self, min_val, max_val): self.slider.setRange(int(min_val * 10**self.decimals), int(max_val * 10**self.decimals))
    def setValue(self, value): self.slider.setValue(int(value * 10**self.decimals))
    def value(self): return self.slider.value() / (10 ** self.decimals)

class SystemMonitorWidget(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SystemMonitorWidget")
        self.setFrameShape(QFrame.StyledPanel)
        self.setFrameShadow(QFrame.Raised)
        self.setStyleSheet("QFrame#SystemMonitorWidget { border: 1px solid #30363D; border-radius: 6px; padding: 8px; }")
        self.setMaximumWidth(350)

        layout = QGridLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(8)

        self.cpu_progress = QProgressBar(format="CPU: %p%")
        self.ram_progress = QProgressBar(format="RAM: %p%")
        self.gpu_progress = QProgressBar(format="GPU: N/A", value=0, enabled=False)

        layout.addWidget(self.cpu_progress, 0, 0)
        layout.addWidget(self.ram_progress, 1, 0)
        layout.addWidget(self.gpu_progress, 2, 0)

        self.timer = QTimer(self); self.timer.setInterval(1000)
        self.timer.timeout.connect(self.update_stats); self.timer.start()
        if psutil: psutil.cpu_percent(interval=None)
        self.update_stats()

    def update_stats(self):
        if psutil:
            try:
                p = psutil.cpu_percent(interval=None)
                self.cpu_progress.setValue(int(p)); self.cpu_progress.setFormat(f"CPU: {p:.1f}%")
                p = psutil.virtual_memory().percent
                self.ram_progress.setValue(int(p)); self.ram_progress.setFormat(f"RAM: {p:.1f}%")
            except Exception:
                self.cpu_progress.setFormat("CPU: Error"); self.ram_progress.setFormat("RAM: Error")
        if GPUtil:
            try:
                gpus = GPUtil.getGPUs()
                if gpus:
                    p = gpus[0].load * 100
                    self.gpu_progress.setEnabled(True); self.gpu_progress.setValue(int(p)); self.gpu_progress.setFormat(f"GPU: {p:.1f}%")
                else:
                    self.gpu_progress.setEnabled(False); self.gpu_progress.setFormat("GPU: N/A")
            except Exception:
                self.gpu_progress.setEnabled(False); self.gpu_progress.setFormat("GPU: Error")

class ColorButton(QPushButton):
    changed = Signal(QColor)
    def __init__(self, hex_color: str = "#FFFFFF", parent=None):
        super().__init__(parent); self._color = QColor(hex_color); self.setFixedSize(70, 30); self._apply_style(); self.clicked.connect(self._pick_color)
    def _apply_style(self):
        text_color = "#000" if self._color.lightness() > 120 else "#FFF"
        self.setStyleSheet(f"background-color: {self._color.name()}; color: {text_color}; border: 1px solid #30363D; border-radius: 6px; font-weight: bold; font-size: 11px; padding: 2px;")
    def _pick_color(self):
        from PySide6.QtWidgets import QColorDialog
        new_color = QColorDialog.getColor(self._color, self, "Вибір кольору")
        if new_color.isValid():
            self._color = new_color; self._apply_style(); self.changed.emit(self._color)
    def color(self) -> QColor: return self._color
    def setColor(self, color: QColor):
        if color and color.isValid(): self._color = color; self._apply_style(); self.changed.emit(self._color)

class PathPicker(QWidget):
    changed = Signal(str)
    def __init__(self, placeholder: str = "", default: str = "", is_dir=True, parent=None):
        super().__init__(parent); self.is_dir = is_dir
        self.editor = QLineEdit(default); self.editor.setPlaceholderText(placeholder)
        self.button = QPushButton("Browse"); self.button.setProperty("cssClass", "blue_accent"); self.button.setFixedWidth(100)
        layout = QHBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(6); layout.addWidget(self.editor, 1); layout.addWidget(self.button, 0)
        self.button.clicked.connect(self._pick_path); self.editor.textChanged.connect(self.changed)
    def _pick_path(self):
        current_path = self.text()
        if self.is_dir: new_path = QFileDialog.getExistingDirectory(self, "Вибір папки", current_path or "D:/")
        else: new_path, _ = QFileDialog.getOpenFileName(self, "Вибір файлу", current_path or "D:/")
        if new_path: self.editor.setText(new_path)
    def text(self) -> str: return self.editor.text().strip()
    def setText(self, text: str): self.editor.setText(text or "")

class IconWidget(QWidget):
    def __init__(self, brand: str, parent=None):
        super().__init__(parent)
        self.setFixedSize(28, 28)
        self.path = get_social_icon(brand)
        self._color = QColor("#8B949E")
    def setColor(self, color: QColor):
        self._color = color
        self.update()
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHints(QPainter.Antialiasing)
        painter.setBrush(self._color)
        painter.setPen(Qt.NoPen)
        rect = self.path.boundingRect()
        painter.translate((self.width() - rect.width()) / 2 - rect.left(), (self.height() - rect.height()) / 2 - rect.top())
        painter.drawPath(self.path)

class FormatCard(QFrame):
    clicked = Signal(str)
    def __init__(self, key: str, title: str, subtitle: str, brand: str, parent=None):
        super().__init__(parent)
        self.key = key
        self._checked = False
        self.setObjectName("FormatCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout = QHBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(12)
        self.icon_widget = IconWidget(brand); layout.addWidget(self.icon_widget)
        text_layout = QVBoxLayout(); text_layout.setSpacing(2); text_layout.addStretch()
        self.title_label = QLabel(title); self.title_label.setObjectName("titleLabel")
        self.subtitle_label = QLabel(subtitle); self.subtitle_label.setObjectName("subtitleLabel")
        text_layout.addWidget(self.title_label); text_layout.addWidget(self.subtitle_label); text_layout.addStretch()
        layout.addLayout(text_layout); layout.addStretch()
    def setChecked(self, checked: bool):
        self._checked = bool(checked)
        self.setProperty("checked", self._checked)
        self.icon_widget.setColor(QColor("#FFFFFF") if checked else QColor("#8B949E"))
        self.style().unpolish(self); self.style().polish(self)
    def mousePressEvent(self, event):
        self.clicked.emit(self.key); super().mousePressEvent(event)

class FormatSelectorVertical(QWidget):
    selected = Signal(str)
    def __init__(self, parent=None):
        super().__init__(parent); layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(8)
        title = QLabel("Формат відео"); title_font = QFont(); title_font.setPointSize(14); title_font.setBold(True); title.setFont(title_font); title.setStyleSheet("color: #C9D1D9; margin-bottom: 8px; padding-left: 4px;"); layout.addWidget(title)
        self.cards: Dict[str, FormatCard] = {}
        formats = [
            ("youtube_4k_16_9", "YouTube 4K", "16:9 · 3840×2160", "youtube"),
            ("youtube_16_9", "YouTube", "16:9 · 1920×1080", "youtube"),
            ("shorts_9_16", "Shorts", "9:16 · 1080×1920", "youtube"),
            ("ig_reels_9_16", "Instagram Reels", "9:16 · 1080×1920", "ig"),
            ("ig_4_5", "Instagram 4:5", "4:5 · 1080×1350", "ig"),
            ("ig_1_1", "Instagram 1:1", "1:1 · 1080×1080", "ig"),
            ("tiktok_9_16", "TikTok", "9:16 · 1080×1920", "tiktok"),
            ("fb_4_5", "Facebook 4:5", "4:5 · 1080×1350", "facebook"),
            ("fb_1_1", "Facebook 1:1", "1:1 · 1080×1080", "facebook")
        ]
        for key, title_text, subtitle, brand in formats:
            card = FormatCard(key, title_text, subtitle, brand, self); card.clicked.connect(self._on_card_clicked); self.cards[key] = card; layout.addWidget(card)
        layout.addStretch(1); self._on_card_clicked("youtube_16_9")
    def _on_card_clicked(self, key: str):
        for card_key, card in self.cards.items(): card.setChecked(card_key == key)
        self.selected.emit(key)

class EffectCard(QFrame):
    def __init__(self, title: str, parent=None):
        super().__init__(parent); self.setObjectName("EffectCard")
        main_layout = QVBoxLayout(self); main_layout.setContentsMargins(10, 10, 10, 10); main_layout.setSpacing(8)
        header_layout = QHBoxLayout(); self.toggle_checkbox = QCheckBox(title); self.toggle_checkbox.setStyleSheet("font-weight: 600; font-size: 15px;")
        self.settings_button = QPushButton("⚙️ Налаштувати"); self.settings_button.setCheckable(True); self.settings_button.setChecked(False)
        header_layout.addWidget(self.toggle_checkbox); header_layout.addStretch(); header_layout.addWidget(self.settings_button)
        self.settings_panel = QWidget(); self.content_layout = QFormLayout(self.settings_panel); self.content_layout.setContentsMargins(10, 10, 10, 10); self.content_layout.setSpacing(10); self.content_layout.setLabelAlignment(Qt.AlignLeft)
        main_layout.addLayout(header_layout); main_layout.addWidget(self.settings_panel); self.settings_button.toggled.connect(self.settings_panel.setVisible); self.settings_panel.hide()
    def addRow(self, label: str, widget: QWidget): self.content_layout.addRow(label, widget)

class VideoPage(QWidget):
    sig_biglog = Signal(str); sig_progress = Signal(int, str); sig_running = Signal(bool)
    def __init__(self, parent=None):
        super().__init__(parent); self.setStyleSheet(THEME_CSS)
        self._running = False; self._songs_total = 0; self._songs_done = 0; self.host = None
        self.worker_thread: Optional[threading.Thread] = None
        self.status_queue = queue.Queue(); self.cancel_event = threading.Event()
        self.poll_timer = QTimer(self); self.poll_timer.setInterval(100); self.poll_timer.timeout.connect(self._poll_status)
        self.live_preview_timer = QTimer(self); self.live_preview_timer.setInterval(150); self.live_preview_timer.setSingleShot(True); self.live_preview_timer.timeout.connect(self._update_preview)
        self._setup_ui(); self._setup_connections()
        self._load_config(); self._on_format_selected("youtube_16_9"); self._update_preview(True)

    def _setup_ui(self):
        main_layout = QHBoxLayout(self); main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_splitter = QSplitter(Qt.Horizontal); self.main_splitter.setChildrenCollapsible(False); self.main_splitter.setHandleWidth(8); main_layout.addWidget(self.main_splitter)
        self.left_panel = QWidget(); left_layout = QVBoxLayout(self.left_panel); left_layout.setContentsMargins(0, 0, 0, 0); self.main_splitter.addWidget(self.left_panel)
        self.left_splitter = QSplitter(Qt.Vertical); self.left_splitter.setHandleWidth(8); left_layout.addWidget(self.left_splitter)
        self.right_panel = QWidget(); right_layout = QVBoxLayout(self.right_panel); right_layout.setContentsMargins(0, 0, 0, 0); self.main_splitter.addWidget(self.right_panel)
        self.right_splitter = QSplitter(Qt.Vertical); self.right_splitter.setHandleWidth(8); right_layout.addWidget(self.right_splitter)
        self._setup_left_panel(); self._setup_right_panel(); self._setup_proportions()

    def _setup_left_panel(self):
        self._setup_folders_section(); self._setup_presets_section(); self._setup_equalizer_section(); self._setup_effects_section(); self._setup_motion_section()

    def _setup_folders_section(self):
        group = QGroupBox("Папки"); layout = QFormLayout()
        self.music_path = PathPicker("Папка з музикою...", "D:/music", True)
        self.media_path = PathPicker("Папка з медіа...", "D:/media", True)
        self.output_path = PathPicker("Вихідна папка...", "D:/output", True)
        self.media_type = QComboBox()
        self.media_type.addItems(["Змішано (Фото і Відео)", "Тільки фото", "Тільки відео"])
        layout.addRow("Музика:", self.music_path)
        layout.addRow("Медіа:", self.media_path)
        layout.addRow("Тип фону:", self.media_type)
        layout.addRow("Вихід:", self.output_path)
        group.setLayout(layout)
        self.left_splitter.addWidget(group)

    def _setup_presets_section(self):
        group = QGroupBox("Пресет"); layout = QHBoxLayout()
        self.presets_combo = QComboBox(); self.presets_combo.setMinimumWidth(150); layout.addWidget(self.presets_combo, 1)
        self.btn_save_preset = QPushButton("Зберегти"); self.btn_delete_preset = QPushButton("Видалити")
        layout.addWidget(self.btn_save_preset); layout.addWidget(self.btn_delete_preset)
        group.setLayout(layout); self.left_splitter.addWidget(group)

    def _setup_equalizer_section(self):
        group = QGroupBox("Еквалайзер"); grid = QGridLayout()
        self.eq_enabled = QCheckBox("Увімк. еквалайзер"); grid.addWidget(self.eq_enabled, 0, 0, 1, 6)
        self.eq_engine = QComboBox(); self.eq_engine.addItems(["Хвилі", "Частоти"]); grid.addWidget(QLabel("Тип:"), 1, 0); grid.addWidget(self.eq_engine, 1, 1, 1, 2)
        self.eq_mode = QComboBox(); self.eq_mode.addItems(["Стовпці", "Лінії", "Крапки"]); grid.addWidget(QLabel("Вид:"), 1, 3); grid.addWidget(self.eq_mode, 1, 4, 1, 2)
        self.eq_bars = QSpinBox(); self.eq_bars.setRange(8, 256); self.eq_bars.setValue(96); grid.addWidget(QLabel("Смуги:"), 2, 0); grid.addWidget(self.eq_bars, 2, 1)
        self.eq_thick = QSpinBox(); self.eq_thick.setRange(1, 12); self.eq_thick.setValue(3); grid.addWidget(QLabel("Товщ.:"), 2, 2); grid.addWidget(self.eq_thick, 2, 3)
        self.eq_height = QSpinBox(); self.eq_height.setRange(40, 1000); self.eq_height.setValue(360); grid.addWidget(QLabel("Висота:"), 2, 4); grid.addWidget(self.eq_height, 2, 5)
        self.eq_fullscr = QCheckBox("Повний екран"); grid.addWidget(self.eq_fullscr, 3, 0); self.eq_mirror = QCheckBox("Дзеркало"); self.eq_mirror.setChecked(True); grid.addWidget(self.eq_mirror, 3, 1)
        self.eq_baseline = QCheckBox("Базова лінія"); grid.addWidget(self.eq_baseline, 3, 2)
        self.eq_yoffset = QSpinBox(); self.eq_yoffset.setRange(-100, 100); self.eq_yoffset.setValue(0); grid.addWidget(QLabel("Зсув Y:"), 3, 3, 1, 2); grid.addWidget(self.eq_yoffset, 3, 5)
        self.eq_color = ColorButton("#1F6FEB"); grid.addWidget(QLabel("Колір:"), 4, 0); grid.addWidget(self.eq_color, 4, 1)
        self.eq_opacity = SliderWithValueLabel(); self.eq_opacity.setRange(0, 100); self.eq_opacity.setValue(90); grid.addWidget(QLabel("Прозорість:"), 4, 2, 1, 2); grid.addWidget(self.eq_opacity, 4, 4, 1, 2)
        group.setLayout(grid); self.left_splitter.addWidget(group)

    def _setup_effects_section(self):
        scroll_area = QScrollArea(); scroll_area.setWidgetResizable(True); scroll_area.setFrameShape(QFrame.NoFrame)
        container = QWidget(); effects_layout = QVBoxLayout(container); effects_layout.setContentsMargins(0, 6, 0, 6); effects_layout.setSpacing(10)
        self.stars_card = EffectCard("✨ Зірки"); self.st_enabled = self.stars_card.toggle_checkbox; self.st_count = SliderWithValueLabel(); self.st_count.setRange(10, 1000); self.st_count.setValue(200); self.stars_card.addRow("Кількість:", self.st_count); self.st_size = SliderWithValueLabel(); self.st_size.setRange(1, 20); self.st_size.setValue(3); self.stars_card.addRow("Розмір:", self.st_size); self.st_pulse = SliderWithValueLabel(); self.st_pulse.setRange(0, 100); self.st_pulse.setValue(40); self.stars_card.addRow("Пульсація:", self.st_pulse); self.st_color = ColorButton("#FFFFFF"); self.stars_card.addRow("Колір:", self.st_color); self.st_opacity = SliderWithValueLabel(); self.st_opacity.setRange(0, 100); self.st_opacity.setValue(70); self.stars_card.addRow("Прозорість:", self.st_opacity); effects_layout.addWidget(self.stars_card)
        self.rain_card = EffectCard("💧 Дощ"); self.rn_enabled = self.rain_card.toggle_checkbox; self.rn_count = SliderWithValueLabel(); self.rn_count.setRange(50, 2000); self.rn_count.setValue(500); self.rain_card.addRow("Кількість:", self.rn_count); self.rn_length = SliderWithValueLabel(); self.rn_length.setRange(10, 200); self.rn_length.setValue(50); self.rain_card.addRow("Довжина:", self.rn_length); self.rn_thick = SliderWithValueLabel(); self.rn_thick.setRange(1, 10); self.rn_thick.setValue(2); self.rain_card.addRow("Товщина:", self.rn_thick); self.rn_speed = SliderWithValueLabel(decimals=1); self.rn_speed.setRange(50, 500); self.rn_speed.setValue(200); self.rain_card.addRow("Швидкість:", self.rn_speed); self.rn_angle = SliderWithValueLabel(decimals=1); self.rn_angle.setRange(-45, 45); self.rn_angle.setValue(15.0); self.rain_card.addRow("Кут:", self.rn_angle); self.rn_color = ColorButton("#6CA0FF"); self.rain_card.addRow("Колір:", self.rn_color); self.rn_opacity = SliderWithValueLabel(); self.rn_opacity.setRange(0, 100); self.rn_opacity.setValue(55); self.rain_card.addRow("Прозорість:", self.rn_opacity); effects_layout.addWidget(self.rain_card)
        self.smoke_card = EffectCard("💨 Дим"); self.sm_enabled = self.smoke_card.toggle_checkbox; self.sm_density = SliderWithValueLabel(); self.sm_density.setRange(1, 100); self.sm_density.setValue(20); self.smoke_card.addRow("Густота (%):", self.sm_density); self.sm_speed = SliderWithValueLabel(decimals=1); self.sm_speed.setRange(-50, 50); self.sm_speed.setValue(12); self.smoke_card.addRow("Швидкість:", self.sm_speed); self.sm_color = ColorButton("#A0A0FF"); self.smoke_card.addRow("Колір:", self.sm_color); self.sm_opacity = SliderWithValueLabel(); self.sm_opacity.setRange(0, 100); self.sm_opacity.setValue(35); self.smoke_card.addRow("Прозорість:", self.sm_opacity); effects_layout.addWidget(self.smoke_card)
        effects_layout.addStretch(1); scroll_area.setWidget(container); self.left_splitter.addWidget(scroll_area)

    def _setup_motion_section(self):
        group = QGroupBox("Рух камери"); grid = QGridLayout()
        self.mv_enabled = QCheckBox("Увімкнути рух"); grid.addWidget(self.mv_enabled, 0, 0, 1, 4)
        self.mv_direction = QComboBox(); self.mv_direction.addItems(["Ліво→Право", "Право→Ліво", "Вверх", "Вниз", "Зум IN", "Зум OUT", "Обертання", "Тряска"]); grid.addWidget(QLabel("Напрям:"), 1, 0); grid.addWidget(self.mv_direction, 1, 1)
        self.mv_oscillate = QCheckBox("Коливання"); self.mv_oscillate.setChecked(True); grid.addWidget(self.mv_oscillate, 1, 2, 1, 2)
        self.mv_speed = SliderWithValueLabel(decimals=1); self.mv_speed.setRange(0, 100); self.mv_speed.setValue(10); grid.addWidget(QLabel("Швидкість:"), 2, 0); grid.addWidget(self.mv_speed, 2, 1, 1, 3)
        self.mv_amount = SliderWithValueLabel(decimals=1); self.mv_amount.setRange(0, 25); self.mv_amount.setValue(5); grid.addWidget(QLabel("Амплітуда:"), 3, 0); grid.addWidget(self.mv_amount, 3, 1, 1, 3)
        group.setLayout(grid); self.left_splitter.addWidget(group)

    def _setup_right_panel(self):
        self._setup_render_section(); self._setup_preview_section(); self._setup_log_section()

    def _setup_render_section(self):
        group = QGroupBox("Налаштування рендеру"); grid = QGridLayout()
        self.use_gpu = QCheckBox("Використовувати GPU"); self.use_gpu.setChecked(True); grid.addWidget(self.use_gpu, 0, 0, 1, 2)
        self.gpu_device = QComboBox(); self.gpu_device.addItems(["Авто", "NVIDIA", "Intel", "AMD", "CPU"]); grid.addWidget(QLabel("Пристрій:"), 0, 2); grid.addWidget(self.gpu_device, 0, 3)
        self.gpu_preset = QComboBox(); self.gpu_preset.addItems(["Авто", "Швидкий", "Якісний", "Найкращий"]); grid.addWidget(QLabel("Якість:"), 1, 0); grid.addWidget(self.gpu_preset, 1, 1)
        self.threads_count = QSpinBox(); self.threads_count.setRange(0, 64); self.threads_count.setValue(16); grid.addWidget(QLabel("Потоки:"), 1, 2); grid.addWidget(self.threads_count, 1, 3)
        self.jobs_count = QSpinBox(); self.jobs_count.setRange(1, 10); self.jobs_count.setValue(1); grid.addWidget(QLabel("Воркери:"), 2, 0); grid.addWidget(self.jobs_count, 2, 1)
        
        ### === ВИПРАВЛЕНО: Створюємо змінну для тексту, щоб його можна було міняти ===
        self.songs_count_label = QLabel("К-ть пісень:")
        self.songs_count = QSpinBox(); self.songs_count.setRange(1, 1000); self.songs_count.setValue(10)
        grid.addWidget(self.songs_count_label, 2, 2); grid.addWidget(self.songs_count, 2, 3)

        self.album_mode = QCheckBox("Альбомний режим"); grid.addWidget(self.album_mode, 3, 0)
        self.album_duration = QLineEdit("30:00"); self.album_duration.setEnabled(False); grid.addWidget(self.album_duration, 3, 1)
        self.album_mode.toggled.connect(self.album_duration.setEnabled)

        self.until_material = QCheckBox("Обробляти, поки є матеріал"); grid.addWidget(self.until_material, 3, 2, 1, 2)
        
        self.video_min_duration_enabled = QCheckBox("Відео довше, ніж"); grid.addWidget(self.video_min_duration_enabled, 4, 0, 1, 1)
        self.video_min_duration_sec = QSpinBox(); self.video_min_duration_sec.setRange(1, 300); self.video_min_duration_sec.setValue(5); self.video_min_duration_sec.setSuffix(" сек"); grid.addWidget(self.video_min_duration_sec, 4, 1, 1, 1)
        self.video_min_duration_enabled.toggled.connect(self.video_min_duration_sec.setEnabled)
        self.video_min_duration_sec.setEnabled(False)
        
        self.btn_clear_cache = QPushButton("Очистити кеш"); grid.addWidget(self.btn_clear_cache, 5, 0, 1, 2)
        self.btn_reset_session = QPushButton("Скинути сесію"); grid.addWidget(self.btn_reset_session, 5, 2, 1, 2)
        group.setLayout(grid); self.right_splitter.addWidget(group)

    def _setup_preview_section(self):
        group = QGroupBox("Прев'ю"); layout = QVBoxLayout()
        preview_row = QHBoxLayout(); preview_row.setSpacing(12)
        self.format_selector = FormatSelectorVertical(); preview_row.addWidget(self.format_selector, 0)
        self.preview_label = QLabel(); self.preview_label.setMinimumSize(320, 200); self.preview_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding); self.preview_label.setStyleSheet("background-color: #0D1117; border: 1px solid #30363D; border-radius: 6px;"); self.preview_label.setAlignment(Qt.AlignCenter); preview_row.addWidget(self.preview_label, 1)
        layout.addLayout(preview_row)
        bottom_layout = QHBoxLayout(); bottom_layout.setContentsMargins(0, 8, 0, 0)
        self.system_monitor = SystemMonitorWidget(); bottom_layout.addWidget(self.system_monitor)
        bottom_layout.addStretch()
        self.btn_apply_settings = QPushButton("Застосувати та зберегти"); self.btn_apply_settings.setProperty("cssClass", "accent"); bottom_layout.addWidget(self.btn_apply_settings)
        layout.addLayout(bottom_layout)
        group.setLayout(layout); self.right_splitter.addWidget(group)

    def _setup_log_section(self):
        group = QGroupBox("Журнал виконання"); layout = QVBoxLayout()
        self.log_text = QPlainTextEdit(); self.log_text.setReadOnly(True); self.log_text.setMinimumHeight(150)
        layout.addWidget(self.log_text); group.setLayout(layout); self.right_splitter.addWidget(group)

    def _setup_proportions(self):
        self.main_splitter.setSizes([600, 600])
        self.left_splitter.setSizes([120, 80, 240, 300, 150])
        self.right_splitter.setSizes([220, 500, 180])

    ### === ВИПРАВЛЕНО: Єдина функція для керування станом елементів ===
    def _update_render_controls_state(self):
        is_cpu = self.gpu_device.currentText().lower() == "cpu"
        is_album_mode = self.album_mode.isChecked()
        is_until_material = self.until_material.isChecked()

        # Керування полем "Потоки"
        self.threads_count.setEnabled(is_cpu)
        if not is_cpu:
            self.threads_count.setValue(0) # Автоматично ставимо 0 для GPU

        # Керування полем "К-ть пісень"
        if is_album_mode:
            self.songs_count_label.setText("Пісень в альбомі:")
            self.songs_count.setEnabled(True) # В альбомному режимі ЗАВЖДИ активно
        else:
            self.songs_count_label.setText("К-ть пісень:")
            self.songs_count.setEnabled(not is_until_material) # В режимі кліпів залежить від галочки

    def _setup_connections(self):
        self.btn_apply_settings.clicked.connect(self._apply_settings); self.btn_clear_cache.clicked.connect(self._clear_cache); self.btn_reset_session.clicked.connect(self._reset_session)
        self.btn_save_preset.clicked.connect(self._save_preset); self.btn_delete_preset.clicked.connect(self._delete_preset)
        self.presets_combo.currentIndexChanged.connect(self._load_preset)
        self.format_selector.selected.connect(self._on_format_selected)

        ### === ВИПРАВЛЕНО: Всі залежні елементи викликають одну функцію ===
        self.gpu_device.currentIndexChanged.connect(self._update_render_controls_state)
        self.album_mode.toggled.connect(self._update_render_controls_state)
        self.until_material.toggled.connect(self._update_render_controls_state)
        
        for w in self.__dict__.values():
            if isinstance(w, (QCheckBox, QComboBox, QSlider, QSpinBox, QDoubleSpinBox, ColorButton, PathPicker, SliderWithValueLabel)):
                for signal_name in ['toggled', 'clicked', 'valueChanged', 'currentIndexChanged', 'textChanged', 'changed']:
                    if hasattr(w, signal_name) and w not in [self.gpu_device, self.album_mode, self.until_material]: # Щоб уникнути подвійних підключень
                        getattr(w, signal_name).connect(self._arm_live_preview)

    def _arm_live_preview(self):
        if not self.live_preview_timer.isActive(): self.live_preview_timer.start()

    def _on_format_selected(self, key: str): self._arm_live_preview()

    def _get_resolution_fps(self) -> Tuple[int, int, int]:
        key = next((k for k, v in self.format_selector.cards.items() if v._checked), "youtube_16_9")
        res_map = {
            "youtube_4k_16_9": (3840, 2160), "youtube_16_9": (1920, 1080), "shorts_9_16": (1080, 1920),
            "ig_reels_9_16": (1080, 1920), "ig_4_5": (1080, 1350), "ig_1_1": (1080, 1080),
            "tiktok_9_16": (1080, 1920), "fb_4_5": (1080, 1350), "fb_1_1": (1080, 1080)
        }
        w, h = res_map.get(key, (1920, 1080))
        return w, h, 30

    def _build_config(self) -> Dict:
        w, h, fps = self._get_resolution_fps()
        media_type_map = {"Змішано (Фото і Відео)": "mixed", "Тільки фото": "image", "Тільки відео": "video"}
        
        threads_val = self.threads_count.value()
        if self.gpu_device.currentText().lower() != "cpu":
            threads_val = 0 # Гарантуємо 0 для GPU

        return {
            "music_dir": _ensure_dir(self.music_path.text()), "media_dir": _ensure_dir(self.media_path.text()), "out_dir": _ensure_dir(self.output_path.text()),
            "media_type": media_type_map.get(self.media_type.currentText(), "mixed"), "resolution": f"{w}x{h} {fps}fps",
            "use_gpu": self.use_gpu.isChecked(), "gpu": self.gpu_device.currentText().lower(), "gpu_preset": self.gpu_preset.currentText(),
            "threads": threads_val,
            "jobs": self.jobs_count.value(),
            "songs": self.songs_count.value(),
            "album_enabled": self.album_mode.isChecked(), "album_sec": _mmss_to_seconds(self.album_duration.text()),
            "until_material": self.until_material.isChecked(),
            "video_min_duration_enabled": self.video_min_duration_enabled.isChecked(), "video_min_duration_sec": self.video_min_duration_sec.value(),
            "eq_ui": {"enabled": self.eq_enabled.isChecked(), "engine": self.eq_engine.currentText(), "mode": self.eq_mode.currentText(), "bars": self.eq_bars.value(), "thickness": self.eq_thick.value(), "height": self.eq_height.value(), "fullscreen": self.eq_fullscr.isChecked(), "y_offset": self.eq_yoffset.value(), "mirror": self.eq_mirror.isChecked(), "baseline": self.eq_baseline.isChecked(), "color": _hex(self.eq_color.color()), "opacity": self.eq_opacity.value()},
            "stars_ui": {"enabled": self.st_enabled.isChecked(), "count": self.st_count.value(), "size": self.st_size.value(), "pulse": self.st_pulse.value(), "color": _hex(self.st_color.color()), "opacity": self.st_opacity.value()},
            "rain_ui": {"enabled": self.rn_enabled.isChecked(), "count": self.rn_count.value(), "length": self.rn_length.value(), "thickness": self.rn_thick.value(), "angle_deg": self.rn_angle.value(), "speed": self.rn_speed.value(), "color": _hex(self.rn_color.color()), "opacity": self.rn_opacity.value()},
            "smoke_ui": {"enabled": self.sm_enabled.isChecked(), "density": self.sm_density.value(), "color": _hex(self.sm_color.color()), "opacity": self.sm_opacity.value(), "speed": self.sm_speed.value()},
            "motion_ui": {"enabled": self.mv_enabled.isChecked(), "direction": self.mv_direction.currentText(), "speed": self.mv_speed.value(), "amount": self.mv_amount.value(), "oscillate": self.mv_oscillate.isChecked()}
        }

    def _update_preview(self, initial: bool = False):
        w, h, _ = self._get_resolution_fps(); pixmap = QPixmap(w, h); pixmap.fill(QColor("#0D1117")); painter = QPainter(pixmap); painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        try:
            cfg = self._build_config()
            cfg["motion_ui"]["direction"] = {"Ліво→Право": "lr", "Право→Ліво": "rl", "Вверх": "up", "Вниз": "down", "Зум IN": "zin", "Зум OUT": "zout", "Обертання": "rotate", "Тряска": "shake"}.get(cfg["motion_ui"]["direction"], "lr")
            if cfg["eq_ui"]["enabled"]: painter.drawPixmap(0, 0, make_eq_overlay(cfg["eq_ui"], w, h))
            if cfg["stars_ui"]["enabled"]: painter.drawPixmap(0, 0, make_stars_overlay(cfg["stars_ui"], w, h))
            if cfg["rain_ui"]["enabled"]: painter.drawPixmap(0, 0, make_rain_overlay(cfg["rain_ui"], w, h))
            if cfg["smoke_ui"]["enabled"]: painter.drawPixmap(0, 0, make_smoke_overlay(cfg["smoke_ui"], w, h))
            if cfg["motion_ui"]["enabled"]: draw_motion_indicator(painter, pixmap.rect(), cfg["motion_ui"])
        except Exception as e:
            painter.setPen(QColor("#FF6B6B")); painter.setFont(QFont("Arial", 20)); painter.drawText(pixmap.rect(), Qt.AlignCenter, f"Помилка рендеру: {e}")
        finally: painter.end()
        self.preview_label.setPixmap(pixmap.scaled(self.preview_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _apply_config_to_ui(self, config: Dict):
        # ... (rest of the function remains the same as original)
        def set_widget_value(widget: QWidget, value: Any):
            if isinstance(widget, (QSpinBox, QDoubleSpinBox, QSlider, SliderWithValueLabel)): widget.setValue(value)
            elif isinstance(widget, QCheckBox): widget.setChecked(value)
            elif isinstance(widget, QLineEdit): widget.setText(str(value))
            elif isinstance(widget, QComboBox): widget.setCurrentText(str(value))
            elif isinstance(widget, ColorButton): widget.setColor(QColor(value))
            elif isinstance(widget, PathPicker): widget.setText(str(value))

        all_widget_maps = {
            "": {"music_dir": self.music_path, "media_dir": self.media_path, "out_dir": self.output_path, "media_type": self.media_type},
            None: {"use_gpu": self.use_gpu, "gpu": self.gpu_device, "gpu_preset": self.gpu_preset, "threads": self.threads_count, "jobs": self.jobs_count, "songs": self.songs_count, "album_enabled": self.album_mode, "until_material": self.until_material, "video_min_duration_enabled": self.video_min_duration_enabled, "video_min_duration_sec": self.video_min_duration_sec},
            "eq_ui": {"enabled": self.eq_enabled, "engine": self.eq_engine, "mode": self.eq_mode, "bars": self.eq_bars, "thickness": self.eq_thick, "height": self.eq_height, "fullscreen": self.eq_fullscr, "y_offset": self.eq_yoffset, "mirror": self.eq_mirror, "baseline": self.eq_baseline, "color": self.eq_color, "opacity": self.eq_opacity},
            "stars_ui": {"enabled": self.st_enabled, "count": self.st_count, "size": self.st_size, "pulse": self.st_pulse, "color": self.st_color, "opacity": self.st_opacity},
            "rain_ui": {"enabled": self.rn_enabled, "count": self.rn_count, "length": self.rn_length, "thickness": self.rn_thick, "angle_deg": self.rn_angle, "speed": self.rn_speed, "color": self.rn_color, "opacity": self.rn_opacity},
            "smoke_ui": {"enabled": self.sm_enabled, "density": self.sm_density, "color": self.sm_color, "opacity": self.sm_opacity, "speed": self.sm_speed},
            "motion_ui": {"enabled": self.mv_enabled, "direction": self.mv_direction, "speed": self.mv_speed, "amount": self.mv_amount, "oscillate": self.mv_oscillate}
        }
        for section_key, widget_map in all_widget_maps.items():
            section_data = config if section_key in [None, ""] else config.get(section_key, {})
            for key, widget in widget_map.items():
                if key in section_data:
                    value = section_data[key]
                    if widget == self.mv_direction: value = {"lr": "Ліво→Право", "rl": "Право→Ліво", "up": "Вверх", "down": "Вниз", "zin": "Зум IN", "zout": "Зум OUT", "rotate": "Обертання", "shake": "Тряска"}.get(value, "Ліво→Право")
                    set_widget_value(widget, value)
        if config.get("album_enabled"): self.album_duration.setText(_seconds_to_mmss(config.get("album_sec", 1800)))
        
        ### === ВИПРАВЛЕНО: Викликаємо єдину функцію для оновлення стану при завантаженні ===
        self._update_render_controls_state()
        self._arm_live_preview()

    def _save_config(self):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f: json.dump(self._build_config(), f, ensure_ascii=False, indent=2)
        except Exception as e: self._log_message(f"Помилка збереження конфігурації: {e}")
    def _load_config(self):
        if not os.path.isfile(CONFIG_FILE): return
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f: self._apply_config_to_ui(json.load(f))
        except Exception as e: self._log_message(f"Помилка завантаження конфігурації: {e}")
    def _load_presets(self):
        try:
            self.presets_combo.blockSignals(True); self.presets_combo.clear()
            if not os.path.exists(USER_PRESETS_FILE):
                with open(USER_PRESETS_FILE, 'w', encoding='utf-8') as f: json.dump({}, f)
            with open(USER_PRESETS_FILE, "r", encoding="utf-8") as f: presets = json.load(f)
            self.presets_combo.addItems(sorted(presets.keys())); self.presets_combo.blockSignals(False)
        except Exception as e: self._log_message(f"Помилка завантаження пресетів: {e}")
    def _save_preset(self):
        name, ok = QInputDialog.getText(self, "Збереження пресету", "Введіть назву пресету:")
        if not (ok and name.strip()): return
        try:
            presets = {};
            if os.path.isfile(USER_PRESETS_FILE):
                with open(USER_PRESETS_FILE, "r", encoding="utf-8") as f: presets = json.load(f)
            presets[name] = self._build_config()
            with open(USER_PRESETS_FILE, "w", encoding="utf-8") as f: json.dump(presets, f, ensure_ascii=False, indent=2)
            self._load_presets(); self.presets_combo.setCurrentText(name); self._log_message(f"✅ Пресет '{name}' збережено")
        except Exception as e: self._log_message(f"❌ Помилка збереження пресету: {e}")
    def _delete_preset(self):
        name = self.presets_combo.currentText()
        if not name or QMessageBox.question(self, "Підтвердження", f"Видалити пресет '{name}'?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.No: return
        try:
            if os.path.isfile(USER_PRESETS_FILE):
                with open(USER_PRESETS_FILE, "r", encoding="utf-8") as f: presets = json.load(f)
                if name in presets: del presets[name]
                with open(USER_PRESETS_FILE, "w", encoding="utf-8") as f: json.dump(presets, f, ensure_ascii=False, indent=2)
                self._load_presets(); self._log_message(f"✅ Пресет '{name}' видалено")
        except Exception as e: self._log_message(f"❌ Помилка видалення пресету: {e}")
    def _load_preset(self, index):
        name = self.presets_combo.itemText(index)
        if not name or not os.path.isfile(USER_PRESETS_FILE): return
        try:
            with open(USER_PRESETS_FILE, "r", encoding="utf-8") as f: presets = json.load(f)
            if name in presets: self._apply_config_to_ui(presets[name]); self._log_message(f"✅ Пресет '{name}' завантажено")
        except Exception as e: self._log_message(f"❌ Помилка завантаження пресету: {e}")

    def _apply_settings(self): self._update_preview(); self._save_config(); self._log_message("✅ Налаштування застосовано та збережено")
    def _clear_cache(self):
        try: shutil.rmtree(CACHE_DIR, ignore_errors=True); os.makedirs(CACHE_DIR, exist_ok=True); self._log_message("✅ Кеш очищено")
        except Exception as e: self._log_message(f"❌ Помилка очищення кешу: {e}")
    def _reset_session(self):
        try:
            self._stop_processing(); reset_processing_state()
            while not self.status_queue.empty(): self.status_queue.get_nowait()
            if os.path.isdir(STAGE_DIR): shutil.rmtree(STAGE_DIR, ignore_errors=True)
            self._log_message("✅ Сесію скинуто")
        except Exception as e: self._log_message(f"❌ Помилка скидання сесії: {e}")

    def _log_message(self, message: str):
        self.log_text.appendPlainText(message); self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())
    def _start_processing(self):
        if self._running: return
        config = self._build_config()
        if not config["music_dir"] or not config["out_dir"]: QMessageBox.warning(self, "Помилка", "Заповніть папки: Музика та Вихід"); return
        self.log_text.clear(); self._save_config(); self.cancel_event.clear(); self._running = True; self.sig_running.emit(True)
        self._songs_total = config.get("songs", 1); self._songs_done = 0
        self.worker_thread = threading.Thread(target=start_video_jobs, args=(config, self.status_queue, self.cancel_event), daemon=True)
        self.worker_thread.start(); self.poll_timer.start(); self._log_message("▶ Початок обробки відео...")
    def _stop_processing(self):
        if not self._running: return
        self.cancel_event.set(); stop_all_jobs(); self.poll_timer.stop()
        if self.worker_thread and self.worker_thread.is_alive(): self.worker_thread.join(timeout=2)
        self._running = False; self.sig_running.emit(False); self._log_message("⏹ Обробку зупинено")

    def _poll_status(self):
        while not self.status_queue.empty():
            msg = self.status_queue.get_nowait()
            t = msg.get("type")
            if t == "log": self._log_message(msg.get("msg", ""))
            elif t == "progress": self.sig_progress.emit(int(msg.get("value", 0)), "Рендеринг")
            elif t == "done":
                self._songs_done += 1; m = f"✅ Готово ({self._songs_done}/{self._songs_total}): {msg.get('output', '')}"
                self._log_message(m); self.sig_biglog.emit(m)
            elif t == "error":
                 m = f"❌ {msg.get('msg', '')}"; self._log_message(m); self.sig_biglog.emit(m); self._stop_processing()
            elif t == "all_done":
                self._stop_processing(); self._log_message("🎉 Вся обробка завершена!")

    def handle_start(self, auto_mode: bool = False): self._start_processing()
    def handle_stop(self): self._stop_processing()
    def set_host(self, host):
        self.host = host; self.sig_progress.connect(lambda v, l="Відео": host.set_progress(self, int(v), l))
        self.sig_running.connect(lambda r: host.set_running(self, bool(r))); self.sig_biglog.connect(lambda text: host.log(self, text))

if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    window = VideoPage()
    window.setWindowTitle("Video Processor (Optimized & Fixed)")
    window.resize(1300, 900)
    window.show()
    sys.exit(app.exec())