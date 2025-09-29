# -*- coding: utf-8 -*-
# ui/pages/audio_page.py
# Дві моделі (V5 дефолт, V4_5PLUS) як «пігулки» з підсвіткою та галочкою.
# Дефолти: 1 пакет; "Час у назві" вимкнено.

from PySide6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, QTextEdit,
    QSpinBox, QCheckBox, QFileDialog, QComboBox, QGroupBox,
    QSizePolicy, QGridLayout, QStackedWidget, QToolButton, QButtonGroup
)
from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtGui import QFontMetrics

import threading, queue, os, json

from ui.animated_push_button import AnimatedPushButton
from logic.audio_backend import run_suno_pipeline, build_albums_pipeline, kie_fetch_models
from logic.gpt_namer import gpt_generate_titles, gpt_fetch_balances
from logic.kie_api import kie_fetch_credits

# ---- UI константи
BASE_CONTROL_H      = 30
BASE_TEXTEDIT_ROWS  = 2
BASE_SPACING        = 8
BASE_FORM_HSPACING  = 14
BASE_FORM_VSPACING  = 10
MIN_LINE_W          = 360
MIN_TITLES_W        = 420
BALANCE_LABEL_W     = 110
ICON_BTN_W          = 36
DOT_SIZE            = 12
DONT_WRAP_FORM_ROWS = True

CONFIG_PATH = os.path.join(os.getcwd(), "suno_qt_config.json")


class AudioPage(QWidget):
    balances_ready = Signal(object, object)  # ((kie_credit, kie_ok, models), (gpt_info, gpt_ok))

    def __init__(self):
        super().__init__()

        # стан
        self.host = None
        self.status_q = queue.Queue()
        self.cancel_event = threading.Event()
        self.worker = None
        self.running = False
        self.style_presets = []
        self._scale = 1.0
        self._ui_ready = False          # головний гард: поки False — ніяких доступів до UI
        self._pending_balances = None   # кеш сигналу, якщо прилетів до готовності UI

        # режими
        self.page_mode = "tracks"   # "tracks" | "albums"
        self.gen_mode  = "auto"     # "auto" | "lyrics" | "gpt"

        # колектори для підгонки геометрії
        self._form_layouts = []
        self._layout_spaces = []
        self._lineedits, self._combos, self._spins = [], [], []
        self._buttons, self._textedits, self._balance_labels = [], [], []

        # (оголошення полів-кнопок, щоб уникати AttributeError під час autoreload)
        self.btn_model_v5 = None
        self.btn_model_v45 = None
        self.btn_mode_tracks = None
        self.btn_mode_albums = None
        self.btn_m_auto = self.btn_m_lyrics = self.btn_m_gpt = None

        # побудова UI
        self._build_ui()
        self._load_config()
        self._wire_timers()

        self.balances_ready.connect(self._on_balances_ready)
        self._refresh_balances()

    # ---------- host / масштаб ----------
    def set_host(self, host_mainwindow): self.host = host_mainwindow
    def apply_scale(self, scale: float):
        self._scale = float(scale); self._reapply_sizes()

    # активні кнопки завжди підсвічені при відкритті
    def showEvent(self, e):
        super().showEvent(e)
        QTimer.singleShot(0, self._apply_segment_style)

    # ---------- хелпери ----------
    def _ctrl_h(self) -> int:
        fm = QFontMetrics(self.font())
        return int(max(BASE_CONTROL_H, fm.height() + 10) * self._scale)

    def _remember(self, w):
        from PySide6.QtWidgets import QLineEdit, QComboBox, QSpinBox, QTextEdit, QLayout
        if isinstance(w, QLineEdit):   self._lineedits.append(w)
        if isinstance(w, QComboBox):   self._combos.append(w)
        if isinstance(w, QSpinBox):    self._spins.append(w)
        if isinstance(w, (AnimatedPushButton, QToolButton)): self._buttons.append(w)
        if isinstance(w, QTextEdit):   self._textedits.append(w)
        if isinstance(w, QLayout):     self._layout_spaces.append(w)
        return w

    def _fix_input(self, w):
        self._remember(w); w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def _fix_spin(self, w):
        self._remember(w); w.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    def _fix_btn(self, b): self._remember(b)
    def _fix_textedit(self, w):
        self._remember(w); w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def _lbl(self, t):    lab = QLabel(t); lab.setAlignment(Qt.AlignRight | Qt.AlignVCenter); return lab
    def _sublbl(self, t): lab = QLabel(t); lab.setAlignment(Qt.AlignLeft  | Qt.AlignVCenter); return lab

    def _hbox(self, *widgets) -> QWidget:
        w = QWidget(); l = QHBoxLayout(w); l.setContentsMargins(0,0,0,0); self._remember(l)
        for wid in widgets: l.addWidget(wid)
        l.addStretch(1); return w

    def _form(self, parent=None) -> QFormLayout:
        fl = QFormLayout(parent)
        fl.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        fl.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        fl.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        if DONT_WRAP_FORM_ROWS: fl.setRowWrapPolicy(QFormLayout.DontWrapRows)
        self._form_layouts.append(fl); return fl

    # ===================== UI =====================
    def _build_ui(self):
        root = QVBoxLayout(self); root.setContentsMargins(8,8,8,8); root.setSpacing(8)

        # ---- Верх: вибір моделі (2 пігулки з підсвіткою та галочкою)
        hdr = QHBoxLayout()
        hdr.addWidget(QLabel("Модель:"))

        self.btn_model_v5 = AnimatedPushButton("V5")
        self.btn_model_v45 = AnimatedPushButton("V4_5PLUS")
        for b in (self.btn_model_v5, self.btn_model_v45):
            b.setCheckable(True); self._fix_btn(b); b.setMinimumWidth(90)
        self.btn_model_v5.setChecked(True)  # дефолт — V5

        g = QButtonGroup(self); g.setExclusive(True)
        g.addButton(self.btn_model_v5); g.addButton(self.btn_model_v45)
        self.btn_model_v5.toggled.connect(self._apply_segment_style)
        self.btn_model_v45.toggled.connect(self._apply_segment_style)

        hdr.addWidget(self.btn_model_v5); hdr.addWidget(self.btn_model_v45); hdr.addStretch(1)
        root.addLayout(hdr)

        # ---- Режим сторінки
        seg = QHBoxLayout(); seg.setSpacing(int(6*self._scale)); self._layout_spaces.append(seg)
        self.btn_mode_tracks = AnimatedPushButton("🎵 Suno (KIE)")
        self.btn_mode_albums = AnimatedPushButton("💿 Альбоми")
        for b in (self.btn_mode_tracks, self.btn_mode_albums):
            b.setCheckable(True); self._fix_btn(b); b.setMinimumWidth(140)
        self.btn_mode_tracks.setChecked(True)
        self.btn_mode_tracks.clicked.connect(lambda: self._set_page_mode("tracks"))
        self.btn_mode_albums.clicked.connect(lambda: self._set_page_mode("albums"))
        seg.addWidget(QLabel("Режим:")); seg.addWidget(self.btn_mode_tracks); seg.addWidget(self.btn_mode_albums); seg.addStretch(1)
        seg_w = QWidget(); seg_w.setLayout(seg)
        root.addWidget(seg_w)

        # ---- Ключі + баланси
        keys_box = QGroupBox("API ключі та баланс")
        keys_box.setObjectName("apiKeysGroup")
        gk = QGridLayout(keys_box); gk.setContentsMargins(8,8,8,8); gk.setHorizontalSpacing(10); gk.setVerticalSpacing(6)

        kform = self._form()
        # KIE
        self.kie_key = QLineEdit(); self.kie_key.setEchoMode(QLineEdit.Password); self._fix_input(self.kie_key)
        self.kie_eye = self._make_eye(self.kie_key)
        self.kie_dot = self._make_dot("не перевірено")
        self.kie_balance_lbl = QLabel("KIE: —"); self._balance_labels.append(self.kie_balance_lbl)
        self.kie_auth_btn = AnimatedPushButton("🔐 Авторизувати/Моделі"); self._fix_btn(self.kie_auth_btn)
        self.kie_auth_btn.setToolTip("Авторизація + підтягнути доступні моделі")
        self.kie_auth_btn.clicked.connect(self._authorize_and_fetch_models)
        kform.addRow(self._lbl("KIE API Key:"), self._hbox(self.kie_key, self.kie_eye, self.kie_dot, self.kie_balance_lbl, self.kie_auth_btn))

        # GPT
        self.gpt_key = QLineEdit(); self.gpt_key.setEchoMode(QLineEdit.Password); self._fix_input(self.gpt_key)
        self.gpt_eye = self._make_eye(self.gpt_key)
        self.gpt_dot = self._make_dot("не перевірено")
        self.gpt_balance_lbl = QLabel("GPT: —"); self._balance_labels.append(self.gpt_balance_lbl)
        kform.addRow(self._lbl("GPT API Key:"), self._hbox(self.gpt_key, self.gpt_eye, self.gpt_dot, self.gpt_balance_lbl))
        gk.addLayout(kform, 0, 0, 3, 1)

        right = QVBoxLayout(); right.setContentsMargins(0,0,0,0); self._layout_spaces.append(right)
        self.btn_save_cfg = AnimatedPushButton("💾 Зберегти ключі/настройки"); self._fix_btn(self.btn_save_cfg); self.btn_save_cfg.clicked.connect(self._save_config)
        self.btn_check   = AnimatedPushButton("🔄 Перевірити ключі зараз");   self._fix_btn(self.btn_check);   self.btn_check.clicked.connect(self._manual_check_keys)
        right.addWidget(self.btn_save_cfg); right.addWidget(self.btn_check); right.addStretch(1)
        right_w = QWidget(); right_w.setLayout(right)
        gk.addWidget(right_w, 0, 1, 3, 1)

        root.addWidget(keys_box)

        # ---- Стек контенту
        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_tracks_box())
        self.stack.addWidget(self._build_albums_box())
        root.addWidget(self.stack, 1)

        root.addStretch(0)

        self._reapply_sizes()
        self._ui_ready = True  # UI готовий!
        # якщо сигнал балансів прилетів раніше — обробимо зараз
        if self._pending_balances:
            args = self._pending_balances
            self._pending_balances = None
            self._on_balances_ready(*args)
        else:
            self._apply_segment_style()

    def _build_tracks_box(self) -> QWidget:
        tracks_box = QGroupBox("Генерація треків (Suno/KIE)")
        tracks_box.setObjectName("tracksGroup")
        tform = self._form(tracks_box)

        # Генератор
        modes = QHBoxLayout(); modes.setContentsMargins(0,0,0,0); self._layout_spaces.append(modes)
        self.btn_m_auto   = AnimatedPushButton("Авто");   self.btn_m_auto.setCheckable(True); self.btn_m_auto.setChecked(True)
        self.btn_m_lyrics = AnimatedPushButton("Лірика"); self.btn_m_lyrics.setCheckable(True)
        self.btn_m_gpt    = AnimatedPushButton("GPT");    self.btn_m_gpt.setCheckable(True)
        for b in (self.btn_m_auto, self.btn_m_lyrics, self.btn_m_gpt):
            self._fix_btn(b); b.setMinimumWidth(90); b.clicked.connect(self._on_gen_mode_click)
        modes.addWidget(QLabel("Генератор:")); modes.addWidget(self.btn_m_auto); modes.addWidget(self.btn_m_lyrics); modes.addWidget(self.btn_m_gpt); modes.addStretch(1)
        modes_w = QWidget(); modes_w.setLayout(modes)
        tform.addRow(self._lbl("Режим генерації:"), modes_w)

        # Папка
        self.output_dir = QLineEdit(os.path.join(os.path.expanduser("~"), "Music", "Suno")); self._fix_input(self.output_dir)
        b_out = AnimatedPushButton("📂"); self._fix_btn(b_out); b_out.clicked.connect(self._pick_out_dir)
        tform.addRow(self._lbl("Папка збереження:"), self._hbox(self.output_dir, b_out))

        # Дві колонки
        grid2 = QGridLayout(); grid2.setContentsMargins(0,0,0,0); grid2.setHorizontalSpacing(8); grid2.setVerticalSpacing(8)

        # Ліва
        self.style_text = QTextEdit(); self._fix_textedit(self.style_text)
        self.style_text.setPlaceholderText("Опис/стиль музики... (ідейник для GPT у «Авто»/«GPT»)")
        presets_box = QGroupBox("Пресети стилів (до 15)")
        presets_box.setObjectName("presetsGroup")
        p = QHBoxLayout(presets_box); p.setContentsMargins(8,8,8,8); self._layout_spaces.append(p)
        self.style_combo = QComboBox(); self._fix_input(self.style_combo)
        b_load = AnimatedPushButton("⤵"); self._fix_btn(b_load)
        b_add  = AnimatedPushButton("＋"); self._fix_btn(b_add)
        b_del  = AnimatedPushButton("🗑"); self._fix_btn(b_del)
        p.addWidget(self.style_combo, 1); p.addWidget(b_load); p.addWidget(b_add); p.addWidget(b_del)
        b_load.clicked.connect(self._preset_load); b_add.clicked.connect(self._preset_add); b_del.clicked.connect(self._preset_delete)

        self.lyrics_text = QTextEdit(); self._fix_textedit(self.lyrics_text)
        self.lyrics_text.setPlaceholderText("Введи лірику (режим «Лірика»)")
        self._toggle_lyrics_visible()

        left = QVBoxLayout(); left.setContentsMargins(0,0,0,0); self._layout_spaces.append(left)
        left.addWidget(self.style_text)
        left.addWidget(presets_box)
        left.addWidget(self._sublbl("Лірика для треків:"))
        left.addWidget(self.lyrics_text)
        lw = QWidget(); lw.setLayout(left)

        # Права
        self.instrumental = QCheckBox("Інструментал")
        self.save_lyrics  = QCheckBox("Зберігати текст"); self.save_lyrics.setChecked(True)
        self.add_time     = QCheckBox("Час у назві");    self.add_time.setChecked(False)  # дефолт: вимкнено
        opts = self._hbox(self.instrumental, self.save_lyrics, self.add_time)

        self.batches = QSpinBox(); self._fix_spin(self.batches); self.batches.setRange(1, 20); self.batches.setValue(1)  # дефолт: 1 пакет
        self.length_min = QSpinBox(); self._fix_spin(self.length_min); self.length_min.setRange(1, 10); self.length_min.setValue(3)
        nums = self._hbox(self._sublbl("Пакетів (×2):"), self.batches, self._sublbl("Тривалість (хв):"), self.length_min)

        self.titles_line = QLineEdit(); self._fix_input(self.titles_line)
        self.titles_line.setPlaceholderText("Назви (через ; ). Порожньо — GPT авто")

        right = QVBoxLayout(); right.setContentsMargins(0,0,0,0); self._layout_spaces.append(right)
        right.addWidget(self._sublbl("Опції:"));              right.addWidget(opts)
        right.addWidget(self._sublbl("К-сть / Тривалість:"));  right.addWidget(nums)
        right.addWidget(self._sublbl("Назви треків:"));        right.addWidget(self.titles_line)
        rw = QWidget(); rw.setLayout(right)

        grid2.addWidget(lw, 0, 0); grid2.addWidget(rw, 0, 1)
        grid2.setColumnStretch(0, 1); grid2.setColumnStretch(1, 1)
        grid2_w = QWidget(); grid2_w.setLayout(grid2)

        tform.addRow(self._lbl("Стиль / опис:"), grid2_w)
        return tracks_box

    def _build_albums_box(self) -> QWidget:
        albums_box = QGroupBox("Створення альбомів з локальних треків (назви GPT)")
        albums_box.setObjectName("albumsGroup")
        aform = self._form(albums_box)

        self.src_dir = QLineEdit(); self._fix_input(self.src_dir)
        b_src = AnimatedPushButton("📂"); self._fix_btn(b_src); b_src.clicked.connect(self._pick_src_dir)
        aform.addRow(self._lbl("Джерело (папка з треками):"), self._hbox(self.src_dir, b_src))

        self.alb_out = QLineEdit(os.path.join(os.path.expanduser("~"), "Music", "Albums")); self._fix_input(self.alb_out)
        b_aout = AnimatedPushButton("📂"); self._fix_btn(b_aout); b_aout.clicked.connect(self._pick_alb_out)
        aform.addRow(self._lbl("Куди зберігати альбоми (root):"), self._hbox(self.alb_out, b_aout))

        self.num_albums = QSpinBox(); self._fix_spin(self.num_albums); self.num_albums.setRange(1,200); self.num_albums.setValue(1)
        self.tracks_per = QSpinBox(); self._fix_spin(self.tracks_per); self.tracks_per.setRange(1,50); self.tracks_per.setValue(13)

        self.selection_mode = QComboBox(); self._fix_input(self.selection_mode); self.selection_mode.addItems(["random","seq"])
        self.unique_between = QCheckBox("Без повторів між альбомами"); self.unique_between.setChecked(True)
        self.copy_mode = QComboBox(); self._fix_input(self.copy_mode); self.copy_mode.addItems(["move","copy"])

        self.schema = QLineEdit("{track_no:02} - {track_title}{ext}"); self._fix_input(self.schema)
        self.title_limit = QSpinBox(); self._fix_spin(self.title_limit); self.title_limit.setRange(20,120); self.title_limit.setValue(60)

        self.album_style = QLineEdit("Melodic tropical deep house, sunny, warm, lush pads"); self._fix_input(self.album_style)

        aform.addRow(self._lbl("Альбомів / Треків:"), self._hbox(self._sublbl("Альбомів:"), self.num_albums, self._sublbl("Треків/альбом:"), self.tracks_per))
        aform.addRow(self._lbl("Відбір / Операція:"), self._hbox(self._sublbl("Відбір:"), self.selection_mode, self._sublbl("Операція:"), self.copy_mode, self.unique_between))
        aform.addRow(self._lbl("Схема імені / Ліміт:"), self._hbox(self._sublbl("Схема:"), self.schema, self._sublbl("Ліміт:"), self.title_limit))
        aform.addRow(self._lbl("Стиль/опис для назв:"), self.album_style)
        return albums_box

    # ---------- лампи + «око» ----------
    def _make_dot(self, tip: str) -> QLabel:
        dot = QLabel()
        dot.setObjectName("statusIndicator")
        dot.setFixedSize(int(DOT_SIZE*self._scale), int(DOT_SIZE*self._scale))
        dot.setToolTip(tip)
        # Цей стиль встановлюється тут, оскільки головний QSS не визначає кольори стану.
        # Це локалізований стиль, який не конфліктує з глобальною темою.
        dot.setStyleSheet(
            f"background:#6B7280;border-radius:{int(DOT_SIZE*self._scale/2)}px;"
        )
        return dot

    def _set_dot(self, dot: QLabel, state: str):
        colors = {"ok":"#10B981","warn":"#F59E0B","bad":"#EF4444","unknown":"#6B7280"}
        c = colors.get(state, colors["unknown"])
        # Цей стиль встановлюється тут, оскільки головний QSS не визначає кольори стану.
        dot.setStyleSheet(
            f"background:{c};border-radius:{int(DOT_SIZE*self._scale/2)}px;"
        )

    def _make_eye(self, line: QLineEdit) -> QToolButton:
        eye = QToolButton(); eye.setCheckable(True); eye.setText("👁"); self._fix_btn(eye)
        eye.setToolTip("Показати/сховати ключ")
        def toggle(ch):
            line.setEchoMode(QLineEdit.Normal if ch else QLineEdit.Password)
            eye.setText("🙈" if ch else "👁")
        eye.toggled.connect(toggle); return eye

    # ---------- перемикачі / стилі ----------
    def _set_page_mode(self, mode: str):
        self.page_mode = mode
        if getattr(self, "_ui_ready", False):
            is_tracks = mode == "tracks"
            self.stack.setCurrentIndex(0 if is_tracks else 1)
            # Оновлюємо стан кнопок, а QSS подбає про вигляд
            self.btn_mode_tracks.setChecked(is_tracks)
            self.btn_mode_albums.setChecked(not is_tracks)

    def _on_gen_mode_click(self):
        src = self.sender()
        if src is self.btn_m_auto:
            self.gen_mode = "auto"
        elif src is self.btn_m_lyrics:
            self.gen_mode = "lyrics"
        else:
            self.gen_mode = "gpt"

        # Встановлюємо стан (checked), а QSS оновить вигляд
        self.btn_m_auto.setChecked(self.gen_mode == "auto")
        self.btn_m_lyrics.setChecked(self.gen_mode == "lyrics")
        self.btn_m_gpt.setChecked(self.gen_mode == "gpt")
        self._toggle_lyrics_visible()

    def _toggle_lyrics_visible(self):
        if hasattr(self, "lyrics_text") and self.lyrics_text:
            self.lyrics_text.setVisible(self.gen_mode == "lyrics")

    def _apply_segment_style(self):
        if not getattr(self, "_ui_ready", False):
            return

        # ВИДАЛЕНО: Жорстко закодовані стилі.
        # Тепер вигляд кнопок повністю контролюється QSS-файлом
        # через псевдо-стан :checked. Кнопки вже є checkable,
        # тому достатньо лише оновлювати їхній текст.

        # Функція для додавання/видалення галочки
        def _txt(btn, label):
            return f"✓ {label}" if (btn and btn.isChecked()) else label

        # Оновлюємо лише текст кнопок
        if self.btn_model_v5:   self.btn_model_v5.setText(_txt(self.btn_model_v5, "V5"))
        if self.btn_model_v45:  self.btn_model_v45.setText(_txt(self.btn_model_v45, "V4_5PLUS"))

    # ---------- розміри ----------
    def _reapply_sizes(self):
        h  = self._ctrl_h()
        hs = int(BASE_FORM_HSPACING * self._scale)
        vs = int(BASE_FORM_VSPACING * self._scale)

        for w in self._lineedits + self._combos:
            w.setMinimumHeight(h)
            base = MIN_TITLES_W if (hasattr(self, "titles_line") and w is self.titles_line) else MIN_LINE_W
            w.setMinimumWidth(int(base * self._scale))

        for b in self._buttons:
            try:
                b.setMinimumHeight(h)
                txt = b.text() if hasattr(b, "text") else ""
                if txt in ("📂", "⤵", "＋", "🗑"):
                    b.setFixedWidth(int(ICON_BTN_W * self._scale))
            except RuntimeError:
                pass

        for sp in self._spins:
            try: sp.setMinimumHeight(h)
            except RuntimeError: pass

        for te in self._textedits:
            try: te.setMinimumHeight(int(h * BASE_TEXTEDIT_ROWS))
            except RuntimeError: pass

        for lab in self._balance_labels:
            try: lab.setFixedWidth(int(BALANCE_LABEL_W * self._scale))
            except RuntimeError: pass

        for fl in self._form_layouts:
            try:
                fl.setHorizontalSpacing(hs); fl.setVerticalSpacing(vs)
            except RuntimeError:
                pass

        for l in self._layout_spaces:
            try: l.setSpacing(int(BASE_SPACING * self._scale))
            except Exception: pass

        for dot in (getattr(self, "kie_dot", None), getattr(self, "gpt_dot", None)):
            if dot:
                try:
                    dot.setFixedSize(int(DOT_SIZE*self._scale), int(DOT_SIZE*self._scale))
                except RuntimeError:
                    pass

        self.updateGeometry()

    # ---------- таймери / черга статусів ----------
    def _wire_timers(self):
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._drain_queue)
        self.timer.start(120)

        self.bal_timer = QTimer(self)
        self.bal_timer.timeout.connect(self._refresh_balances)
        self.bal_timer.start(90_000)

    def _drain_queue(self):
        try:
            while True:
                m = self.status_q.get_nowait()
                t = m.get("type")
                if t == "log":
                    self._log(m.get("msg",""))
                elif t == "progress":
                    self._set_progress(int(m.get("value",0)), m.get("label",""))
                elif t == "done":
                    self.running = False
                    self._host_running(False)
        except queue.Empty:
            pass

    def deleteLater(self):
        try:
            if hasattr(self, "timer") and self.timer: self.timer.stop()
            if hasattr(self, "bal_timer") and self.bal_timer: self.bal_timer.stop()
        finally:
            super().deleteLater()

    # ---------- перевірка ключів / авторизація ----------
    def _manual_check_keys(self):
        self._set_dot(self.kie_dot, "warn"); self._set_dot(self.gpt_dot, "warn")
        self._refresh_balances()

    def _authorize_and_fetch_models(self):
        self._set_dot(self.kie_dot, "warn")
        def work():
            kie_key = self.kie_key.text().strip()
            credit, ok, models = None, False, []
            if kie_key:
                try:
                    credit = kie_fetch_credits(kie_key); ok = True
                except Exception:
                    ok = False
                try:
                    models = kie_fetch_models(kie_key) or []
                except Exception:
                    models = []
            kie_pack = (credit, ok, models)
            gpt_pack = ({}, bool(self.gpt_key.text().strip()))
            if getattr(self, "_ui_ready", False) and hasattr(self, "balances_ready"):
                self.balances_ready.emit(kie_pack, gpt_pack)
            else:
                self._pending_balances = (kie_pack, gpt_pack)
        threading.Thread(target=work, daemon=True).start()

    def _refresh_balances(self):
        def work():
            kie_key = self.kie_key.text().strip()
            gpt_key = self.gpt_key.text().strip()
            kie_credit, kie_ok = None, False
            gpt, gpt_ok = {}, False
            models: list[str] = []
            if kie_key:
                try:
                    kie_credit = kie_fetch_credits(kie_key); kie_ok = True
                    models = kie_fetch_models(kie_key) or []
                except Exception:
                    kie_credit, kie_ok = None, False; models = []
            if gpt_key:
                try:
                    gpt = gpt_fetch_balances(gpt_key) or {}; gpt_ok = True
                except Exception:
                    gpt, gpt_ok = {}, False
            kie_pack = (kie_credit, kie_ok, models)
            gpt_pack = (gpt, gpt_ok)
            if getattr(self, "_ui_ready", False) and hasattr(self, "balances_ready"):
                self.balances_ready.emit(kie_pack, gpt_pack)
            else:
                self._pending_balances = (kie_pack, gpt_pack)
        threading.Thread(target=work, daemon=True).start()

    @Slot(object, object)
    def _on_balances_ready(self, kie_pack, gpt_pack):
        if not getattr(self, "_ui_ready", False):
            self._pending_balances = (kie_pack, gpt_pack)
            return

        kie_credit, kie_ok, models = (kie_pack + ([],))[:3] if isinstance(kie_pack, tuple) else (None, False, [])
        gpt, gpt_ok = gpt_pack if isinstance(gpt_pack, tuple) else ({}, False)

        self.kie_balance_lbl.setText(f"KIE: {('%.2f' % kie_credit) if isinstance(kie_credit,(int,float)) else '—'}")
        usage = gpt.get("usage_30d_usd"); credits = gpt.get("credits_remaining_usd")
        parts=[]
        if isinstance(usage,(int,float)): parts.append(f"30д: ${usage:.2f}")
        if isinstance(credits,(int,float)): parts.append(f"кредити: ${credits:.2f}")
        self.gpt_balance_lbl.setText("GPT: " + (" | ".join(parts) if parts else "—"))

        self._set_dot(self.kie_dot, "ok" if kie_ok else ("bad" if self.kie_key.text().strip() else "unknown"))
        self._set_dot(self.gpt_dot, "ok" if gpt_ok else ("bad" if self.gpt_key.text().strip() else "unknown"))

        up = [m.upper() for m in (models or [])]
        if "V5" in up:
            self.btn_model_v5.setChecked(True)
        elif ("V4_5PLUS" in up) or ("V4.5PLUS" in up) or ("V4_5" in up):
            self.btn_model_v45.setChecked(True)

        self._apply_segment_style()

    # ---------- старт / стоп ----------
    def _selected_model(self) -> str:
        return "V5" if (self.btn_model_v5 and self.btn_model_v5.isChecked()) else "V4_5PLUS"

    def handle_start(self, _auto_unused: bool):
        if self.running:
            self._log("⚠️ Вже виконується."); return
        self.cancel_event.clear()

        if self.page_mode == "tracks":
            kie_key = self.kie_key.text().strip()
            if not kie_key: self._log("❌ Вкажіть KIE ключ."); return
            outdir = self.output_dir.text().strip()
            if not outdir: self._log("❌ Вкажіть папку збереження."); return

            style_text   = self.style_text.toPlainText().strip()
            lyrics_user  = self.lyrics_text.toPlainText().strip()
            titles_raw   = [t.strip() for t in self.titles_line.text().split(";") if t.strip()]
            gpt_key      = self.gpt_key.text().strip()

            def title_gen(style: str, kind: str, count: int):
                return gpt_generate_titles(gpt_key, style, kind, count)

            self._set_progress(0, "Підготовка…")

            def _worker_tracks():
                try:
                    run_mode = "auto"
                    lyrics_to_use = None
                    tg = None

                    if self.gen_mode == "auto":
                        run_mode = "auto"
                        tg = title_gen if not titles_raw else None
                        self.status_q.put({"type":"log","msg":"▶️ Авто-генерація (KIE). GPT для назв — якщо поле порожнє."})

                    elif self.gen_mode == "lyrics":
                        if not lyrics_user:
                            self.status_q.put({"type":"log","msg":"❌ Вкажи лірику у режимі «Лірика»."})
                            self.status_q.put({"type":"done"}); return
                        run_mode = "manual"
                        lyrics_to_use = lyrics_user
                        self.status_q.put({"type":"log","msg":"▶️ Режим «Лірика»: відправляємо твої слова."})

                    else:  # GPT
                        tg = title_gen
                        if self.instrumental.isChecked():
                            run_mode = "auto"; lyrics_to_use = None
                            self.status_q.put({"type":"log","msg":"▶️ GPT (інструментал): назви від GPT, без лірики; KIE — інструментал."})
                        else:
                            run_mode = "manual"; lyrics_to_use = None
                            self.status_q.put({"type":"log","msg":"▶️ GPT: пробуємо згенерувати назви й лірику зі стилю."})
                            try:
                                lyr_list = gpt_generate_titles(gpt_key, style_text, "lyrics", 1)
                                if isinstance(lyr_list,(list,tuple)) and lyr_list:
                                    lyrics_to_use = str(lyr_list[0]).strip()
                            except Exception:
                                lyrics_to_use = None
                            if not lyrics_to_use:
                                run_mode = "auto"
                                self.status_q.put({"type":"log","msg":"ℹ️ GPT-лірику не отримали — KIE згенерує її автоматично."})

                    run_suno_pipeline(
                        api_key=kie_key,
                        model=self._selected_model(),
                        style_text=style_text,
                        mode=run_mode,
                        lyrics_text=lyrics_to_use,
                        user_titles=titles_raw if titles_raw else None,
                        instrumental=self.instrumental.isChecked(),
                        output_dir=outdir,
                        save_lyrics_to_file=self.save_lyrics.isChecked(),
                        add_time_prefix=self.add_time.isChecked(),
                        batches=self.batches.value(),
                        length_minutes=self.length_min.value(),
                        status_queue=self.status_q,
                        cancel_event=self.cancel_event,
                        title_generator=tg
                    )
                except Exception as e:
                    self.status_q.put({"type":"log","msg":f"❌ Критична помилка: {e}"})
                self.status_q.put({"type":"done"})

            self.running = True; self._host_running(True)
            self.worker = threading.Thread(target=_worker_tracks, daemon=True); self.worker.start()

        else:
            # альбоми
            src = self.src_dir.text().strip()
            out = self.alb_out.text().strip()
            if not (src and os.path.isdir(src)): self._log("❌ Вкажіть коректну папку джерела."); return
            if not out: self._log("❌ Вкажіть папку призначення."); return
            gpt_key = self.gpt_key.text().strip()

            def alb_gen(style: str, kind: str, count: int): return gpt_generate_titles(gpt_key, style, "album", count)
            def trk_gen(style: str, kind: str, count: int): return gpt_generate_titles(gpt_key, style, "track", count)

            self._set_progress(0, "Альбоми: старт")
            self._log("▶️ Створення альбомів (GPT назви)")

            def _worker_albums():
                try:
                    build_albums_pipeline(
                        src_dir=src, out_root=out,
                        num_albums=self.num_albums.value(), tracks_per=self.tracks_per.value(),
                        selection_mode=self.selection_mode.currentText(),
                        unique_between=self.unique_between.isChecked(),
                        copy_mode=self.copy_mode.currentText(),
                        schema=self.schema.text().strip() or "{track_no:02} - {track_title}{ext}",
                        title_limit=self.title_limit.value(),
                        style_prompt=self.album_style.text().strip(),
                        status_queue=self.status_q,
                        cancel_event=self.cancel_event,
                        album_title_generator=alb_gen, track_title_generator=trk_gen
                    )
                except Exception as e:
                    self.status_q.put({"type":"log","msg":f"❌ Критична помилка: {e}"})
                self.status_q.put({"type":"done"})

            self.running = True; self._host_running(True)
            self.worker = threading.Thread(target=_worker_albums, daemon=True); self.worker.start()

    def handle_stop(self):
        if self.worker and self.worker.is_alive():
            self.cancel_event.set()
            self._log("⛔ Зупинка після поточного кроку…")
            self._host_running(False)
        else:
            self._log("ℹ️ Нічого зупиняти.")
            self._host_running(False)

    # ---------- логер/прогрес/хост ----------
    def _log(self, text: str):
        if self.host: self.host.log(self, text)

    def _set_progress(self, value: int, label: str = ""):
        if self.host: self.host.set_progress(self, value, label)

    def _host_running(self, state: bool):
        if self.host and hasattr(self.host, "set_running"):
            self.host.set_running(self, state)

    # ---------- конфіг / пресети / пікери ----------
    def _load_config(self):
        cfg = {}
        try:
            if os.path.exists(CONFIG_PATH):
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
        except Exception:
            cfg = {}

        self.style_presets = list(map(str, cfg.get("style_presets", [])))[:15] or []
        if hasattr(self, "style_combo"):
            self.style_combo.clear(); self.style_combo.addItems(self.style_presets)

        last = cfg.get("last", {})
        self.kie_key.setText(last.get("kie_key",""))
        self.gpt_key.setText(last.get("gpt_key",""))
        if last.get("style_text"): self.style_text.setPlainText(last.get("style_text",""))
        if last.get("lyrics_text"): self.lyrics_text.setPlainText(last.get("lyrics_text",""))
        if last.get("output_dir"): self.output_dir.setText(last.get("output_dir",""))

        prev_model = (last.get("suno_model") or "V5").upper()
        if self.btn_model_v5:  self.btn_model_v5.setChecked(prev_model.startswith("V5"))
        if self.btn_model_v45: self.btn_model_v45.setChecked(prev_model.startswith("V4"))

    def _save_config(self):
        cfg = {
            "style_presets": self.style_presets[:15],
            "last": {
                "kie_key": self.kie_key.text(),
                "gpt_key": self.gpt_key.text(),
                "style_text": self.style_text.toPlainText(),
                "lyrics_text": self.lyrics_text.toPlainText(),
                "output_dir": self.output_dir.text(),
                "suno_model": self._selected_model(),
            }
        }
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            self._log("💾 Налаштування збережено.")
        except Exception as e:
            self._log(f"⚠️ Не вдалося зберегти: {e}")
        self._refresh_balances()

    def _preset_load(self):
        idx = self.style_combo.currentIndex()
        if 0 <= idx < len(self.style_presets):
            self.style_text.setPlainText(self.style_presets[idx])

    def _preset_add(self):
        txt = self.style_text.toPlainText().strip()
        if not txt or txt in self.style_presets: return
        if len(self.style_presets) >= 15: self.style_presets.pop(0)
        self.style_presets.append(txt)
        self.style_combo.clear(); self.style_combo.addItems(self.style_presets)
        self._save_config()

    def _preset_delete(self):
        idx = self.style_combo.currentIndex()
        if 0 <= idx < len(self.style_presets):
            self.style_presets.pop(idx)
            self.style_combo.clear(); self.style_combo.addItems(self.style_presets)
            self._save_config()

    def _pick_out_dir(self):
        dlg = QFileDialog(self, "Обрати папку збереження")
        dlg.setFileMode(QFileDialog.Directory); dlg.setOption(QFileDialog.ShowDirsOnly, True)
        if dlg.exec():
            sel = dlg.selectedFiles()
            if sel: self.output_dir.setText(sel[0])

    def _pick_src_dir(self):
        dlg = QFileDialog(self, "Обрати джерело треків")
        dlg.setFileMode(QFileDialog.Directory); dlg.setOption(QFileDialog.ShowDirsOnly, True)
        if dlg.exec():
            sel = dlg.selectedFiles()
            if sel: self.src_dir.setText(sel[0])

    def _pick_alb_out(self):
        dlg = QFileDialog(self, "Обрати папку для альбомів")
        dlg.setFileMode(QFileDialog.Directory); dlg.setOption(QFileDialog.ShowDirsOnly, True)
        if dlg.exec():
            sel = dlg.selectedFiles()
            if sel: self.alb_out.setText(sel[0])