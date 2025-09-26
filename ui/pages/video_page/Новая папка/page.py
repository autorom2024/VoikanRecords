# -*- coding: utf-8 -*-
from __future__ import annotations
"""
VideoPage — повна версія.
Ключове:
  • «Застосувати» оновлює превʼю та зберігає JSON, але «Старт» завжди бере ПАКЕТ поточних значень напряму з UI.
  • У лог додається підпис EQ/FX (MD5) — легко звірити, що пішло в бекенд те саме, що ти бачиш у превʼю.
  • Альбом-режим (чекбокс) -> тривалість активна; інакше «К-ть пісень».
  • «Поки є матеріал» — поважається (рендерить далі лише якщо увімкнено).
  • Захист від подвійного старту. Стоп глушить усі джоби.
  • Превʼю — сіре тло, правильне співвідношення, формати Shorts/FHD/4K.

Залежності бекенду:
  start_video_jobs(cfg, status_q, cancel_event)
  stop_all_jobs()
  effects_render.make_eq_overlay / make_*_overlay / draw_motion_indicator
"""

import os
import json
import time
import queue
import shutil
import hashlib
import threading
from typing import Dict, Tuple, Optional, List

from PySide6.QtCore import Qt, QTimer, QSize, Signal, Slot
from PySide6.QtGui import QPixmap, QColor, QIcon, QPainter
from PySide6.QtWidgets import (
    QWidget, QLabel, QPushButton, QLineEdit, QFileDialog, QComboBox,
    QCheckBox, QSpinBox, QDoubleSpinBox, QSlider,
    QHBoxLayout, QVBoxLayout, QGridLayout, QGroupBox, QFormLayout,
    QTextEdit, QProgressBar, QMessageBox
)

# ==== бекенд та рендер ====
try:
    from video_backend import start_video_jobs, stop_all_jobs
    from effects_render import (
        make_eq_overlay, make_stars_overlay, make_rain_overlay, make_smoke_overlay,
        draw_motion_indicator,
    )
except Exception:
    from logic.video_backend import start_video_jobs, stop_all_jobs
    from logic.effects_render import (
        make_eq_overlay, make_stars_overlay, make_rain_overlay, make_smoke_overlay,
        draw_motion_indicator,
    )

CONFIG_FILE = "video_qt_config.json"
USER_PRESETS_FILE = "video_user_presets.json"
CACHE_DIR   = os.path.join("_cache", "video_ui")
STAGE_DIR   = os.path.join(CACHE_DIR, "playlist_stage")
os.makedirs(CACHE_DIR, exist_ok=True)

# ------------------------ допоміжні віджети ------------------------

class ColorButton(QPushButton):
    changed = Signal(QColor)
    def __init__(self, hex_color: str = "#FFFFFF", parent=None):
        super().__init__(parent)
        self._c = QColor(hex_color)
        self.setFixedWidth(60)
        self._apply_style()
        self.clicked.connect(self._pick)

    def _apply_style(self):
        self.setText(self._c.name().upper())
        self.setStyleSheet(f"background:{self._c.name()}; color:#000; border:1px solid #444;")

    def _pick(self):
        from PySide6.QtWidgets import QColorDialog
        c = QColorDialog.getColor(self._c, self, "Колір")
        if c.isValid():
            self._c = c
            self._apply_style()
            self.changed.emit(self._c)

    def color(self) -> QColor:
        return self._c

    def setColor(self, c: QColor):
        if c and c.isValid():
            self._c = c
            self._apply_style()
            self.changed.emit(self._c)


class PathPicker(QWidget):
    changed = Signal(str)
    def __init__(self, placeholder: str = "", default: str = "", is_dir=True, parent=None):
        super().__init__(parent)
        self.is_dir = is_dir
        self.ed = QLineEdit(default); self.ed.setPlaceholderText(placeholder)
        self.btn = QPushButton("…"); self.btn.setFixedWidth(28)
        lay = QHBoxLayout(self); lay.setContentsMargins(0,0,0,0)
        lay.addWidget(self.ed); lay.addWidget(self.btn)
        self.btn.clicked.connect(self._pick)
        self.ed.textChanged.connect(lambda _: self.changed.emit(self.text()))

    def _pick(self):
        if self.is_dir:
            d = QFileDialog.getExistingDirectory(self, "Обрати папку", self.text() or "D:/")
        else:
            d, _ = QFileDialog.getOpenFileName(self, "Обрати файл", self.text() or "D:/")
        if d:
            self.ed.setText(d)
            self.changed.emit(self.text())

    def text(self) -> str:
        return self.ed.text().strip()

    def setText(self, s: str):
        self.ed.setText(s or "")

# ------------------------ HELPERS ------------------------

def _ensure_dir(path: str) -> str:
    return path if path and os.path.isdir(path) else ""

def _pct(slider: QSlider) -> int:
    return max(0, min(100, int(slider.value())))

def _hex(qc: QColor) -> str:
    return qc.name().upper()

def _mk_slider(a: int, b: int, v: int) -> QSlider:
    s = QSlider(Qt.Horizontal)
    s.setMinimum(a); s.setMaximum(b); s.setValue(v)
    s.setTickInterval(max(1, (b - a) // 10))
    s.setSingleStep(max(1, (b - a) // 50))
    return s

def _mmss_to_seconds(text: str) -> int:
    try:
        t = text.strip()
        parts = [int(x) for x in t.split(":")]
        if len(parts) == 3:  # hh:mm:ss
            return parts[0]*3600 + parts[1]*60 + parts[2]
        if len(parts) == 2:  # mm:ss
            return parts[0]*60 + parts[1]
        return int(t)
    except Exception:
        return 180

def _seconds_to_mmss(sec: int) -> str:
    sec = max(0, int(sec))
    return f"{sec//60:02d}:{sec%60:02d}"

def _md5sig(d: dict) -> str:
    try:
        return hashlib.md5(json.dumps(d, sort_keys=True).encode("utf-8")).hexdigest()[:8]
    except Exception:
        return "????????"

# =================================================================
#                           VIDEO PAGE
# =================================================================

class VideoPage(QWidget):
    sig_biglog = Signal(str)  # у головний правий лог

    def __init__(self, parent=None):
        super().__init__(parent)

        self._running = False
        self.status_q: "queue.Queue[dict]" = queue.Queue()
        self.cancel_event = threading.Event()
        self.poll_timer = QTimer(self); self.poll_timer.setInterval(60); self.poll_timer.timeout.connect(self._poll)

        outer = QHBoxLayout(self); outer.setContentsMargins(6,6,6,6); outer.setSpacing(10)

        # -------- LEFT: EQ + FX + MOTION + PRESETS --------
        left = QVBoxLayout(); left.setSpacing(10); outer.addLayout(left, 2)

        # === ЕКВАЛАЙЗЕР ===
        self.eq_enabled = QCheckBox("Увімк.")
        self.eq_engine  = QComboBox(); self.eq_engine.addItems(["waves", "freqs"])  # для сумісності з конфігом
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
        left.addWidget(g_eq)

        # === ЕФЕКТИ ===
        # Зірки
        self.st_enabled = QCheckBox("⭐ Зірки")
        self.st_count   = QSpinBox(); self.st_count.setRange(0, 5000); self.st_count.setValue(900)
        self.st_int     = _mk_slider(0,100,80)
        self.st_size    = QSpinBox(); self.st_size.setRange(1, 20); self.st_size.setValue(2)
        self.st_pulse   = QSpinBox(); self.st_pulse.setRange(0,100); self.st_pulse.setValue(40)
        self.st_color   = ColorButton("#FFFFFF")
        self.st_opacity = _mk_slider(0,100,85)

        # Дощ
        self.rn_enabled = QCheckBox("🌧 Дощ")
        self.rn_count   = QSpinBox(); self.rn_count.setRange(0, 5000); self.rn_count.setValue(1200)
        self.rn_length  = QSpinBox(); self.rn_length.setRange(5,200); self.rn_length.setValue(40)
        self.rn_thick   = QSpinBox(); self.rn_thick.setRange(1,20); self.rn_thick.setValue(2)
        self.rn_angle   = QDoubleSpinBox(); self.rn_angle.setRange(-80, 80); self.rn_angle.setValue(15.0)
        self.rn_speed   = QDoubleSpinBox(); self.rn_speed.setRange(10.0, 800.0); self.rn_speed.setValue(160.0)
        self.rn_color   = ColorButton("#9BE2FF")
        self.rn_opacity = _mk_slider(0,100,55)

        # Дим
        self.sm_enabled = QCheckBox("🌫 Дим")
        self.sm_density = QSpinBox(); self.sm_density.setRange(0,400); self.sm_density.setValue(60)
        self.sm_color   = ColorButton("#A0A0A0")
        self.sm_opacity = _mk_slider(0,100,35)
        self.sm_speed   = QDoubleSpinBox(); self.sm_speed.setRange(-80.0, 80.0); self.sm_speed.setValue(12.0)

        g_fx = QGroupBox("Ефекти"); gf = QGridLayout(g_fx); r=0
        # зірки
        gf.addWidget(self.st_enabled, r,0); gf.addWidget(QLabel("К-ть:"), r,1); gf.addWidget(self.st_count, r,2)
        gf.addWidget(QLabel("Інтенс (%):"), r,3); gf.addWidget(self.st_int, r,4)
        gf.addWidget(QLabel("Розмір:"), r,5); gf.addWidget(self.st_size, r,6)
        gf.addWidget(QLabel("Пульс:"), r,7); gf.addWidget(self.st_pulse, r,8); r+=1
        gf.addWidget(QLabel("Колір:"), r,1); gf.addWidget(self.st_color, r,2)
        gf.addWidget(QLabel("Прозорість:"), r,3); gf.addWidget(self.st_opacity, r,4); r+=1
        # дощ
        gf.addWidget(self.rn_enabled, r,0); gf.addWidget(QLabel("К-ть:"), r,1); gf.addWidget(self.rn_count, r,2)
        gf.addWidget(QLabel("Довжина:"), r,3); gf.addWidget(self.rn_length, r,4)
        gf.addWidget(QLabel("Товщина:"), r,5); gf.addWidget(self.rn_thick, r,6)
        gf.addWidget(QLabel("Кут:"), r,7); gf.addWidget(self.rn_angle, r,8); r+=1
        gf.addWidget(QLabel("Швидк. (px/s):"), r,1); gf.addWidget(self.rn_speed, r,2)
        gf.addWidget(QLabel("Колір:"), r,3); gf.addWidget(self.rn_color, r,4)
        gf.addWidget(QLabel("Прозорість:"), r,5); gf.addWidget(self.rn_opacity, r,6); r+=1
        # дим
        gf.addWidget(self.sm_enabled, r,0); gf.addWidget(QLabel("Густина:"), r,1); gf.addWidget(self.sm_density, r,2)
        gf.addWidget(QLabel("Колір:"), r,3); gf.addWidget(self.sm_color, r,4)
        gf.addWidget(QLabel("Прозорість:"), r,5); gf.addWidget(self.sm_opacity, r,6)
        gf.addWidget(QLabel("Дрейф (px/s):"), r,7); gf.addWidget(self.sm_speed, r,8)
        left.addWidget(g_fx)

        # === РУХ КАДРА / КАМЕРА (індикатор у превʼю) ===
        self.mv_enabled = QCheckBox("Увімкнути рух кадра")
        self.mv_dir     = QComboBox(); self.mv_dir.addItems(["lr","rl","up","down","zin","zout","rotate","shake"])
        self.mv_speed   = QDoubleSpinBox(); self.mv_speed.setRange(0.0, 400.0); self.mv_speed.setValue(40.0)
        self.mv_amount  = QDoubleSpinBox(); self.mv_amount.setRange(0.0, 100.0); self.mv_amount.setValue(20.0)
        self.mv_osc     = QCheckBox("Oscillate"); self.mv_osc.setChecked(True)
        self.mv_rotdeg  = QDoubleSpinBox(); self.mv_rotdeg.setRange(0.0, 45.0); self.mv_rotdeg.setValue(8.0)
        self.mv_rothz   = QDoubleSpinBox(); self.mv_rothz.setRange(0.01, 2.5); self.mv_rothz.setSingleStep(0.01); self.mv_rothz.setValue(0.10)
        self.mv_shpx    = QDoubleSpinBox(); self.mv_shpx.setRange(0.0, 50.0); self.mv_shpx.setValue(6.0)
        self.mv_shz     = QDoubleSpinBox(); self.mv_shz.setRange(0.05, 8.0); self.mv_shz.setValue(1.2)

        g_mv = QGroupBox("Рух кадра / Камера (тільки індикатор у превʼю)"); gm = QGridLayout(g_mv); r=0
        gm.addWidget(self.mv_enabled, r,0); gm.addWidget(QLabel("Напрям:"), r,1); gm.addWidget(self.mv_dir, r,2)
        gm.addWidget(QLabel("Швидкість:"), r,3); gm.addWidget(self.mv_speed, r,4)
        gm.addWidget(QLabel("Міра (%):"), r,5); gm.addWidget(self.mv_amount, r,6); r+=1
        gm.addWidget(self.mv_osc, r,0)
        gm.addWidget(QLabel("Rotate °:"), r,3); gm.addWidget(self.mv_rotdeg, r,4)
        gm.addWidget(QLabel("Rotate Гц:"), r,5); gm.addWidget(self.mv_rothz, r,6); r+=1
        gm.addWidget(QLabel("Shake px:"), r,3); gm.addWidget(self.mv_shpx, r,4)
        gm.addWidget(QLabel("Shake Гц:"), r,5); gm.addWidget(self.mv_shz, r,6)
        left.addWidget(g_mv)

        # -------- RIGHT: PATHS + FORMAT + RENDER + PLAYLIST + PREVIEW + PROGRESS --------
        right = QVBoxLayout(); right.setSpacing(10); outer.addLayout(right, 1)

        # Папки
        self.p_music = PathPicker("Музика:", "D:/music", True)
        self.p_media = PathPicker("Фото/Відео:", "D:/media", True)
        self.p_out   = PathPicker("Вихід:", "D:/", True)
        g_paths = QGroupBox("Папки"); ff = QFormLayout(g_paths)
        ff.addRow("🎵 Музика:", self.p_music)
        ff.addRow("🖼 Фото/Відео:", self.p_media)
        ff.addRow("📤 Вихід:", self.p_out)
        right.addWidget(g_paths)

        # Формат
        self.cmb_format = QComboBox(); self.cmb_format.addItems(["FHD", "Shorts", "4K"])
        self.cmb_res    = QComboBox(); self.cmb_res.addItems([
            "YouTube FHD 1920x1080 30fps",
            "YouTube Shorts 1080x1920 30fps",
            "4K 3840x2160 30fps",
        ])
        g_fmt = QGroupBox("Формат"); lf = QGridLayout(g_fmt)
        lf.addWidget(QLabel("Тип:"), 0,0); lf.addWidget(self.cmb_format, 0,1)
        lf.addWidget(QLabel("Роздільна здатність:"), 0,2); lf.addWidget(self.cmb_res, 0,3)
        right.addWidget(g_fmt)

        # Параметри рендеру
        self.cmb_gpu    = QComboBox(); self.cmb_gpu.addItems(["auto","nvidia","intel","amd","cpu"])
        self.cmb_preset = QComboBox(); self.cmb_preset.addItems(["auto/balanced","p1","p2","p3","p4","p5","p6","p7(quality)"])
        self.sp_threads = QSpinBox(); self.sp_threads.setRange(0,64); self.sp_threads.setValue(16)
        self.sp_jobs    = QSpinBox(); self.sp_jobs.setRange(1,10); self.sp_jobs.setValue(1)
        self.sp_songs   = QSpinBox(); self.sp_songs.setRange(1,10); self.sp_songs.setValue(1)
        self.sld_gpu    = _mk_slider(10,100,100)
        self.chk_2s     = QCheckBox("Використовувати відео ≥ 2с"); self.chk_2s.setChecked(True)
        self.chk_until  = QCheckBox("Поки є матеріал"); self.chk_until.setChecked(False)
        self.chk_album  = QCheckBox("Альбом-режим")
        self.ed_album   = QLineEdit("00:30:00"); self.ed_album.setToolTip("hh:mm:ss (час альбому)")
        self.ed_album.setEnabled(False)
        self.chk_album.toggled.connect(self.ed_album.setEnabled)
        self.btn_clear_cache = QPushButton("Очистити кеш")
        self.btn_reset_session = QPushButton("Reset сесії")

        g_r = QGroupBox("Параметри рендеру"); gr = QGridLayout(g_r); r=0
        gr.addWidget(QLabel("GPU:"), r,0); gr.addWidget(self.cmb_gpu, r,1)
        gr.addWidget(QLabel("GPU Preset:"), r,2); gr.addWidget(self.cmb_preset, r,3); r+=1
        gr.addWidget(QLabel("Threads:"), r,0); gr.addWidget(self.sp_threads, r,1)
        gr.addWidget(QLabel("Паралельно (jobs):"), r,2); gr.addWidget(self.sp_jobs, r,3); r+=1
        gr.addWidget(QLabel("К-ть пісень:"), r,0); gr.addWidget(self.sp_songs, r,1)
        gr.addWidget(QLabel("Max GPU load (%):"), r,2); gr.addWidget(self.sld_gpu, r,3); r+=1
        gr.addWidget(self.chk_2s, r,0); gr.addWidget(self.chk_until, r,1)
        gr.addWidget(self.chk_album, r,2); gr.addWidget(self.ed_album, r,3); r+=1
        gr.addWidget(self.btn_clear_cache, r,0,1,2); gr.addWidget(self.btn_reset_session, r,2,1,2)
        right.addWidget(g_r)

        # Плейліст (плейсхолдер)
        self.chk_shuffle_after = QCheckBox("Після 1 кола — перемішувати"); self.chk_shuffle_after.setChecked(False)
        g_pl = QGroupBox("Плейліст (до 10 пісень)"); pl = QVBoxLayout(g_pl)
        pl.addWidget(QLabel("Не вибрано"))
        pl.addWidget(self.chk_shuffle_after)
        right.addWidget(g_pl)

        # Превʼю
        g_pv = QGroupBox("Превʼю (онлайн)"); pv = QVBoxLayout(g_pv)
        self.preview = QLabel(" "); self.preview.setFixedHeight(270)
        # сіре тло
        self.preview.setStyleSheet("background:#1E1E1E;border:1px solid #333")
        self.preview.setAlignment(Qt.AlignCenter)
        self.btn_apply = QPushButton("Застосувати"); self.btn_start = QPushButton("Старт"); self.btn_stop = QPushButton("Стоп")
        hb = QHBoxLayout(); hb.addStretch(1); hb.addWidget(self.btn_apply); hb.addWidget(self.btn_start); hb.addWidget(self.btn_stop)
        pv.addWidget(self.preview); pv.addLayout(hb)
        right.addWidget(g_pv)

        # Прогрес + малий лог
        g_prog = QGroupBox("Прогрес"); pr = QVBoxLayout(g_prog)
        self.progress = QProgressBar(); self.progress.setValue(0)
        self.small_log = QTextEdit(); self.small_log.setObjectName("smallLog")
        self.small_log.setReadOnly(True); self.small_log.setFixedHeight(150)
        pr.addWidget(self.progress); pr.addWidget(self.small_log)
        right.addWidget(g_prog)

        # ----- кнопки -----
        self.btn_apply.clicked.connect(self._on_apply)
        self.btn_start.clicked.connect(self._start)
        self.btn_stop.clicked.connect(self._stop)
        self.btn_clear_cache.clicked.connect(self._clear_cache)
        self.btn_reset_session.clicked.connect(self._reset_session)
        self.cmb_format.currentIndexChanged.connect(self._sync_format_res)

        # ----- live-preview debounce -----
        self._live_timer = QTimer(self); self._live_timer.setInterval(140); self._live_timer.setSingleShot(True)
        def _arm():
            if not self._live_timer.isActive(): self._live_timer.start()
        self._live_timer.timeout.connect(lambda: self._update_preview(initial=False))

        # підписи на зміни (щоб превʼю реагувало)
        for w in [self.eq_enabled, self.eq_engine, self.eq_mode, self.eq_bars, self.eq_thick,
                  self.eq_height, self.eq_fullscr, self.eq_yoffset, self.eq_mirror, self.eq_baseline,
                  self.eq_opacity,
                  self.st_enabled, self.st_count, self.st_int, self.st_size, self.st_pulse, self.st_opacity,
                  self.rn_enabled, self.rn_count, self.rn_length, self.rn_thick, self.rn_angle, self.rn_speed, self.rn_opacity,
                  self.sm_enabled, self.sm_density, self.sm_opacity, self.sm_speed,
                  self.mv_enabled, self.mv_dir, self.mv_speed, self.mv_amount, self.mv_osc, self.mv_rotdeg, self.mv_rothz, self.mv_shpx, self.mv_shz,
                  self.cmb_res, self.cmb_format]:
            if hasattr(w, "toggled"): w.toggled.connect(_arm)
            if hasattr(w, "valueChanged"): w.valueChanged.connect(_arm)
            if hasattr(w, "currentIndexChanged"): w.currentIndexChanged.connect(_arm)
        self.eq_color.changed.connect(_arm)
        self.st_color.changed.connect(_arm)
        self.rn_color.changed.connect(_arm)
        self.sm_color.changed.connect(_arm)

        # ініціалізація
        self._load_config()
        self._sync_format_res()
        self._update_preview(initial=True)

    # -------------------- допоміжні --------------------

    def _status(self, msg: str):
        self.small_log.append(msg)
        if any(k in msg for k in ("FFmpeg", "▶", "✅", "❌", "Готово", "Помилка", "Start:", "Apply:", "BEcfg")):
            self.sig_biglog.emit(msg)

    def _get_WH_fps(self) -> Tuple[int,int,int]:
        txt = self.cmb_res.currentText()
        try:
            wh = [p for p in txt.split() if "x" in p][0]
            w, h = map(int, wh.split("x"))
            fps = int([p for p in txt.split() if "fps" in p][0].replace("fps",""))
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

    # --- складання словників UI ---
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
            "count": self.st_count.value(),
            "intensity": _pct(self.st_int),
            "size": self.st_size.value(),
            "pulse": int(self.st_pulse.value()),
            "color": _hex(self.st_color.color()),
            "opacity": _pct(self.st_opacity),
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

    # --- превʼю ---
    def _base_pm(self, W:int, H:int) -> QPixmap:
        pm = QPixmap(W,H); pm.fill(QColor("#000")); return pm

    def _update_preview(self, initial: bool=False):
        W,H,_ = self._get_WH_fps()
        pm = QPixmap(self._base_pm(W,H))
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        # EQ
        eq = self._build_eq_dict()
        if eq["enabled"]:
            ov = make_eq_overlay(eq, W, H)
            p.drawPixmap(0,0,ov)

        # Stars
        st = self._build_stars_dict()
        if st["enabled"]:
            ov = make_stars_overlay(st, W, H)
            p.drawPixmap(0,0,ov)

        # Rain
        rn = self._build_rain_dict()
        if rn["enabled"]:
            ov = make_rain_overlay(rn, W, H)
            p.drawPixmap(0,0,ov)

        # Smoke
        sm = self._build_smoke_dict()
        if sm["enabled"]:
            ov = make_smoke_overlay(sm, W, H)
            p.drawPixmap(0,0,ov)

        # Motion indicator
        mv = self._build_motion_dict()
        if mv["enabled"]:
            draw_motion_indicator(p, pm.rect(), mv)
        p.end()

        self.preview.setPixmap(
            pm.scaled(self.preview.width(), self.preview.height(),
                      Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )
        if not initial:
            self._status("[UI] Превʼю оновлено")

    # --- конфіг ---
    def _build_cfg(self) -> Dict:
        W,H,fps = self._get_WH_fps()
        cfg = {
            "music_dir": _ensure_dir(self.p_music.text()),
            "media_dir": _ensure_dir(self.p_media.text()),
            "out_dir":   _ensure_dir(self.p_out.text()),
            "resolution": f"{W}x{H} {fps}fps",
            "gpu": self.cmb_gpu.currentText(),
            "gpu_preset": self.cmb_preset.currentText(),
            "threads": int(self.sp_threads.value()),
            "jobs": int(self.sp_jobs.value()),
            "songs": int(self.sp_songs.value()),
            "gpu_load": _pct(self.sld_gpu),
            "use_video_ge2s": bool(self.chk_2s.isChecked()),
            "until_material": bool(self.chk_until.isChecked()),
            "shuffle_after_loop": bool(self.chk_shuffle_after.isChecked()),
            # альбом
            "album_enabled": bool(self.chk_album.isChecked()),
            "album_sec": _mmss_to_seconds(self.ed_album.text()) if self.chk_album.isChecked() else 0,
            # ефекти
            "eq_ui": self._build_eq_dict(),
            "stars_ui": self._build_stars_dict(),
            "rain_ui": self._build_rain_dict(),
            "smoke_ui": self._build_smoke_dict(),
            "motion_ui": self._build_motion_dict(),
        }
        return cfg

    def _save_config(self):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self._build_cfg(), f, ensure_ascii=False, indent=2)
        except Exception as e:
            self._status(f"[UI] Помилка збереження конфігу: {e}")

    def _load_config(self):
        try:
            if os.path.isfile(CONFIG_FILE):
                cfg = json.load(open(CONFIG_FILE, "r", encoding="utf-8"))
                self.p_music.setText(cfg.get("music_dir",""))
                self.p_media.setText(cfg.get("media_dir",""))
                self.p_out.setText(cfg.get("out_dir",""))
                self.cmb_res.setCurrentText(cfg.get("resolution","YouTube FHD 1920x1080 30fps"))
                self.cmb_gpu.setCurrentText(cfg.get("gpu","auto"))
                self.cmb_preset.setCurrentText(cfg.get("gpu_preset","auto/balanced"))
                self.sp_threads.setValue(int(cfg.get("threads",16)))
                self.sp_jobs.setValue(int(cfg.get("jobs",1)))
                self.sp_songs.setValue(int(cfg.get("songs",1)))
                self.sld_gpu.setValue(int(cfg.get("gpu_load",100)))
                self.chk_2s.setChecked(bool(cfg.get("use_video_ge2s", True)))
                self.chk_until.setChecked(bool(cfg.get("until_material", False)))
                self.chk_shuffle_after.setChecked(bool(cfg.get("shuffle_after_loop", False)))
                # альбом
                self.chk_album.setChecked(bool(cfg.get("album_enabled", False)))
                if cfg.get("album_enabled", False):
                    self.ed_album.setText(_seconds_to_mmss(int(cfg.get("album_sec", 0))))
                    self.ed_album.setEnabled(True)
        except Exception as e:
            self._status(f"[UI] Конфіг не завантажено: {e}")

    # --- кеш / сесія ---
    def _clear_cache(self):
        try:
            if os.path.isdir(CACHE_DIR):
                shutil.rmtree(CACHE_DIR, ignore_errors=True)
            os.makedirs(CACHE_DIR, exist_ok=True)
            self._status("[UI] Кеш очищено.")
        except Exception as e:
            self._status(f"[UI] Помилка очищення кешу: {e}")

    def _reset_session_state(self):
        try:
            while True:
                self.status_q.get_nowait()
        except queue.Empty:
            pass
        self.progress.setValue(0)
        self.small_log.clear()
        try:
            if os.path.isdir(STAGE_DIR):
                shutil.rmtree(STAGE_DIR, ignore_errors=True)
        except Exception:
            pass

    def _reset_session(self):
        self._stop()
        self._reset_session_state()
        self._status("[UI] Сесію скинуто. Готово до нового запуску.")

    # -------------------- СТАРТ/СТОП/ПОЛІНГ --------------------
    def _on_apply(self):
        cfg = self._build_cfg()
        self._update_preview()
        self._save_config()
        self._status(f"[UI] Apply: EQsig={_md5sig(cfg['eq_ui'])} mode={cfg['eq_ui']['mode']} "
                     f"bars={cfg['eq_ui']['bars']} color={cfg['eq_ui']['color']} "
                     f"h={cfg['eq_ui'].get('height')} yoff={cfg['eq_ui'].get('y_offset')} "
                     f"mirror={cfg['eq_ui'].get('mirror')} full={cfg['eq_ui'].get('fullscreen')}")

    def _start(self):
        if self._running:
            self._status("[UI] Уже виконується — повторний старт ігнор.")
            return
        self.progress.setValue(0); self.small_log.clear()
        cfg = self._build_cfg()
        self._status(f"[UI] Start: EQsig={_md5sig(cfg['eq_ui'])}")
        if not cfg["music_dir"] or not cfg["out_dir"]:
            QMessageBox.warning(self, "Помилка", "Заповніть папки Музика та Вихід.")
            return
        # запасний дамп для дебагу
        try:
            with open(os.path.join(CACHE_DIR, "cfg_dump.json"), "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

        self._save_config()
        try:
            self._running = True
            self.btn_start.setEnabled(False)
            start_video_jobs(cfg, self.status_q, self.cancel_event)
            self._status("[Відео] ▶ старт")
            self.poll_timer.start()
        except Exception as e:
            self._running = False
            self.btn_start.setEnabled(True)
            self._status(f"[Відео] ❌ Не вдалося стартувати: {e}")

    def _stop(self):
        try:
            self.cancel_event.set()
            stop_all_jobs()
            self.cancel_event.clear()
            self._status("[Відео] Стоп/скасовано")
        except Exception as e:
            self._status(f"[Відео] Помилка стопу: {e}")
        finally:
            self._running = False
            self.btn_start.setEnabled(True)

    @Slot()
    def _poll(self):
        changed = False
        while True:
            try:
                msg = self.status_q.get_nowait()
            except queue.Empty:
                break

            t = msg.get("type")
            if t == "start":
                self._status(f"[Відео] FFmpeg: {msg.get('cmd','.')}")
            elif t == "log":
                self.small_log.append(msg.get("msg",""))
                changed = True
            elif t == "progress":
                try:
                    self.progress.setValue(int(msg.get("value",0)))
                except Exception:
                    pass
            elif t == "done":
                outp = msg.get("output","")
                self.progress.setValue(100)
                self._status(f"[Відео] ✅ Готово: {outp}")
                self.poll_timer.stop()
                self._running = False
                self.btn_start.setEnabled(True)
            elif t == "error":
                em = msg.get("msg","")
                self._status(f"[Відео] ❌ Помилка: {em}")
                self.poll_timer.stop()
                self._running = False
                self.btn_start.setEnabled(True)

        if changed:
            try:
                sb = self.small_log.verticalScrollBar()
                sb.setValue(sb.maximum())
            except Exception:
                pass

    # -------------------- системні події --------------------
    def closeEvent(self, e):
        # якщо сторінку закривають, глушимо рендери
        try:
            self._stop()
        except Exception:
            pass
        super().closeEvent(e)
