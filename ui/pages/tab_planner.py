# tab_planner.py
import os
import re
import sys
import time
import requests
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHBoxLayout, QTabWidget, QCheckBox,
    QSpinBox, QDateTimeEdit, QComboBox, QMessageBox, QHeaderView,
    QAbstractItemView, QScrollArea, QGridLayout, QTimeEdit, QRadioButton,
    QButtonGroup, QGroupBox, QFrame
)
from PySide6.QtCore import Qt, Signal, QTimer, QDateTime, QTime, QThread
from PySide6.QtGui import QPixmap

# --- Спробуйте імпортувати залежності, якщо вони є ---
try:
    from google_api import authorize_google, set_video_schedule, revoke_token
    from helpers_youtube import parse_duration
except ImportError:
    # --- Заглушки, якщо реальні файли відсутні ---
    print("ПОПЕРЕДЖЕННЯ: Файли 'google_api.py' та 'helpers_youtube.py' не знайдено. Використовуються функції-заглушки.")
    def authorize_google(client_secret_file):
        print(f"ЗАГЛУШКА: Авторизація з {client_secret_file}")
        return None, "mock@email.com", None
    def set_video_schedule(youtube, video_id, iso_time):
        print(f"ЗАГЛУШКА: Встановлення розкладу для {video_id} на {iso_time}")
        time.sleep(0.1) # імітація затримки
    def revoke_token():
        print("ЗАГЛУШКА: Видалення токенів")
        return True
    def parse_duration(iso_str):
        if not iso_str: return "00:00"
        m = re.fullmatch(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', iso_str)
        if not m: return "00:00"
        h = int(m.group(1) or 0); mi = int(m.group(2) or 0); s = int(m.group(3) or 0)
        total_seconds = h * 3600 + mi * 60 + s
        return f"{total_seconds // 60:02d}:{total_seconds % 60:02d}"

# ---------- Константи ----------
SHORTS_MAX_SEC = 60
DEFAULT_VIDEO_MAX_HOURS = 5        # дефолтний ліміт для вкладки «Відео» (макс тривалість)
STREAM_MIN_SEC = 5 * 3600          # для класифікації «справжніх» стрімів/записів


# ---------- helpers ----------
def _fmt_count(v):
    try:
        return f"{int(v):,}".replace(",", " ")
    except Exception:
        return str(v)

def _fmt_date(v):
    try:
        dt = datetime.fromisoformat(str(v).replace("Z", "+00:00")).astimezone()
        return dt.strftime("%d.%m.%Y %H:%M")
    except Exception:
        return "—"

def _make_centered_item(text, icon=None):
    txt = text if (text and str(text).strip()) else "—"
    it = QTableWidgetItem(f"{icon} {txt}" if icon else txt)
    it.setTextAlignment(Qt.AlignCenter)
    return it

def _iso8601_to_seconds(iso: str) -> int:
    if not iso:
        return 0
    m = re.fullmatch(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', iso)
    if not m:
        return 0
    h = int(m.group(1) or 0)
    mi = int(m.group(2) or 0)
    s = int(m.group(3) or 0)
    return h * 3600 + mi * 60 + s

def _fmt_mmss(sec: int) -> str:
    sec = max(0, int(sec))
    return f"{sec // 60:02d}:{sec % 60:02d}"

def _make_bar(pct: float, width: int = 24) -> str:
    pct = max(0.0, min(100.0, pct))
    filled = int(round(width * pct / 100.0))
    return "█" * filled + "░" * (width - filled)


# ================================================================
class PlannerTab(QWidget):
    COL_CHECK = 0
    COL_THUMB = 1
    COL_TITLE = 2
    COL_DESC = 3
    COL_DURATION = 4
    COL_VIEWS = 5
    COL_STATUS = 6
    COL_SCHEDULED_AT = 7

    TAB_VIDEOS = 0
    TAB_SHORTS = 1
    TAB_STREAMS = 2
    TAB_STREAM_RECORDS = 3

    # Додаємо сигнали для інтеграції з головним вікном
    log_signal = Signal(str)
    progress_signal = Signal(int, str)
    running_signal = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.is_running = False
        self.youtube = None
        self.email = None
        self.client_secret_file = "client_secret.json"

        # Базові (з API) списки
        self.base_videos = []
        self.base_shorts = []
        self.base_streams = []         # LIVE/UPCOMING
        self.base_stream_records = []  # завершені стріми (за ознаками API)

        # Поточні (з урахуванням корист. фільтрів/лімітів) списки
        self.all_videos = []
        self.all_shorts = []
        self.all_streams = []
        self.all_stream_records = []

        # Ліміт максимальної тривалості для вкладки «Відео»
        self.video_length_limit_sec = DEFAULT_VIDEO_MAX_HOURS * 3600

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # ---------- Header ----------
        header = QHBoxLayout()
        root.addLayout(header)

        self.avatar_lbl = QLabel()
        self.avatar_lbl.setFixedSize(84, 84)
        self.avatar_lbl.setScaledContents(True)

        title_col = QVBoxLayout()
        self.channel_lbl = QLabel("Канал: (не авторизовано)")
        self.channel_lbl.setStyleSheet("font-size: 18px; font-weight: 700; background: transparent;")
        self.stats_lbl = QLabel("📊 —")
        self.stats_lbl.setStyleSheet("font-size: 13px; color: #A0ACC0; background: transparent;")
        title_col.addWidget(self.channel_lbl)
        title_col.addWidget(self.stats_lbl)

        header.addWidget(self.avatar_lbl)
        header.addLayout(title_col)
        header.addStretch(1)

        self.btn_auth = QPushButton("🔑 Авторизуватись")
        self.btn_upload_json = QPushButton("📂 Завантажити JSON")
        self.btn_revoke = QPushButton("❌ Видалити токени")
        self.btn_refresh = QPushButton("🔄 Оновити список")
        self.btn_auto = QPushButton("⏱ Старт автооновлення (1 хв)")
        for b in (self.btn_auth, self.btn_upload_json, self.btn_revoke, self.btn_refresh, self.btn_auto):
            b.setFixedHeight(34)
        header.addWidget(self.btn_auth)
        header.addWidget(self.btn_upload_json)
        header.addWidget(self.btn_revoke)
        header.addWidget(self.btn_refresh)
        header.addWidget(self.btn_auto)

        # ---------- Planner controls ----------
        planner_grp = QGroupBox("Планування публікацій")
        planner = QVBoxLayout(planner_grp)

        controls = QWidget()
        row = QHBoxLayout(controls)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(QLabel("📅 Дата старту:"))
        self.date_start = QDateTimeEdit(QDateTime.currentDateTime())
        self.date_start.setCalendarPopup(True)
        self.date_start.setDisplayFormat("dd.MM.yyyy HH:mm")
        self.date_start.setFixedWidth(190)
        row.addWidget(self.date_start)

        row.addSpacing(8)
        row.addWidget(QLabel("⏳ Інтервал (днів):"))
        self.spin_interval = QSpinBox()
        self.spin_interval.setMinimum(1)
        self.spin_interval.setValue(1)
        self.spin_interval.setFixedWidth(70)
        row.addWidget(self.spin_interval)

        row.addSpacing(8)
        row.addWidget(QLabel("▶ Публікацій у день:"))
        self.spin_perday = QSpinBox()
        self.spin_perday.setRange(1, 20)
        self.spin_perday.setValue(1)
        self.spin_perday.setFixedWidth(70)
        row.addWidget(self.spin_perday)

        row.addSpacing(8)
        row.addWidget(QLabel("⏱ Формат часу:"))
        self.combo_format = QComboBox()
        self.combo_format.addItems(["24h", "AM/PM"])
        self.combo_format.setFixedWidth(90)
        row.addWidget(self.combo_format)

        row.addSpacing(8)
        row.addWidget(QLabel("🌍 Часовий пояс:"))
        self.rb_europe = QRadioButton("🇪🇺 Європа")
        self.rb_america = QRadioButton("🇺🇸 Америка")
        self.rb_europe.setChecked(True)
        row.addWidget(self.rb_europe)
        row.addWidget(self.rb_america)

        row.addSpacing(16)
        self.cb_throttle = QCheckBox("Бережний режим (2с/відео)")
        self.cb_throttle.setChecked(True)
        row.addWidget(self.cb_throttle)

        row.addStretch(1)
        planner.addWidget(controls)

        # Часи публікацій
        times_header = QHBoxLayout()
        times_header.addWidget(QLabel("🕒 Часи публікацій:"))
        times_header.addStretch(1)
        self.btn_add_time = QPushButton("➕ Додати час")
        self.btn_del_time = QPushButton("➖ Видалити вибраний")
        for b in (self.btn_add_time, self.btn_del_time):
            b.setFixedHeight(34)
        times_header.addWidget(self.btn_add_time)
        times_header.addWidget(self.btn_del_time)
        planner.addLayout(times_header)

        self._init_times_grid()
        planner.addWidget(self.times_area, 1)

        actions = QHBoxLayout()
        self.btn_start_plan = QPushButton("🚀 Старт планування")
        self.btn_start_plan.setObjectName("startBtn")
        self.btn_start_plan.setMinimumHeight(44)
        self.btn_stop_plan = QPushButton("⛔ Зупинити")
        self.btn_stop_plan.setObjectName("stopBtn")
        self.btn_stop_plan.setMinimumHeight(44)
        actions.addWidget(self.btn_start_plan)
        actions.addWidget(self.btn_stop_plan)
        actions.addStretch(1)
        planner.addLayout(actions)

        root.addWidget(planner_grp)

        # ---------- Filter (статус) ----------
        filter_bar = QHBoxLayout()
        filter_bar.addWidget(QLabel("🔎 Фільтр:"))
        self.combo_filter = QComboBox()
        self.combo_filter.addItem("Всі", "all")
        self.combo_filter.addItem("Не опубліковані", "unpublished")
        self.combo_filter.addItem("Заплановані", "scheduled")
        self.combo_filter.setFixedWidth(200)
        filter_bar.addWidget(self.combo_filter)
        filter_bar.addStretch(1)
        root.addLayout(filter_bar)

        # ---------- Tabs ----------
        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)

        self.table_videos = self._create_table()
        self.table_shorts = self._create_table()
        self.table_streams = self._create_table()
        self.table_stream_records = self._create_table()

        self.tabs.addTab(self.table_videos, "▶ Відео")
        self.tabs.addTab(self.table_shorts, "🎬 Shorts")
        self.tabs.addTab(self.table_streams, "🔴 Трансляції")
        self.tabs.addTab(self.table_stream_records, "📼 Записи стрімів")

        # ---------- Нижня панель + ФІЛЬТР ТРИВАЛОСТІ ----------
        self.btn_select_all = QPushButton("☑ Вибрати всі")
        self.btn_unselect_all = QPushButton("⬜ Зняти всі")
        for b in (self.btn_select_all, self.btn_unselect_all):
            b.setFixedHeight(34)
        self.selected_label = QLabel("Виділено: 0")
        self.planned_label = QLabel("Заплановано: 0")

        bottom = QHBoxLayout()
        bottom.addWidget(self.btn_select_all)
        bottom.addWidget(self.btn_unselect_all)
        bottom.addStretch(1)

        self.len_lbl = QLabel("Фільтр тривалості (Відео): до")
        self.spin_max_hours = QSpinBox()
        self.spin_max_hours.setRange(0, 999)
        self.spin_max_hours.setValue(DEFAULT_VIDEO_MAX_HOURS)
        self.spin_max_hours.setFixedWidth(70)
        self.lbl_hours = QLabel("год")
        self.spin_max_minutes = QSpinBox()
        self.spin_max_minutes.setRange(0, 59)
        self.spin_max_minutes.setValue(0)
        self.spin_max_minutes.setFixedWidth(70)
        self.lbl_minutes = QLabel("хв")

        self.btn_len_reset = QPushButton("Скинути до 5 год")
        self.btn_len_reset.setFixedHeight(30)

        bottom.addWidget(self.len_lbl)
        bottom.addWidget(self.spin_max_hours)
        bottom.addWidget(self.lbl_hours)
        bottom.addSpacing(6)
        bottom.addWidget(self.spin_max_minutes)
        bottom.addWidget(self.lbl_minutes)
        bottom.addSpacing(10)
        bottom.addWidget(self.btn_len_reset)

        bottom.addStretch(2)
        bottom.addWidget(self.selected_label)
        bottom.addSpacing(12)
        bottom.addWidget(self.planned_label)
        root.addLayout(bottom)

        # ---------- Signals ----------
        self.btn_auth.clicked.connect(self._authorize)
        self.btn_upload_json.clicked.connect(self._upload_json)
        self.btn_revoke.clicked.connect(self._revoke)
        self.btn_refresh.clicked.connect(lambda: self._load_videos(manual=True))
        self.btn_auto.clicked.connect(self._toggle_auto_refresh)
        self.btn_select_all.clicked.connect(lambda: self._toggle_all(True))
        self.btn_unselect_all.clicked.connect(lambda: self._toggle_all(False))
        self.btn_add_time.clicked.connect(self._add_time)
        self.btn_del_time.clicked.connect(self._del_time)
        self.btn_start_plan.clicked.connect(self.start)
        self.btn_stop_plan.clicked.connect(self.stop)
        self.combo_format.currentIndexChanged.connect(self._apply_time_format)
        self.combo_filter.currentIndexChanged.connect(self._apply_filter)
        self.tabs.currentChanged.connect(self._on_tab_change)

        self.spin_max_hours.valueChanged.connect(self._on_len_limit_change)
        self.spin_max_minutes.valueChanged.connect(self._on_len_limit_change)
        self.btn_len_reset.clicked.connect(self._reset_len_limit)

        self.timer = QTimer(self)
        self.timer.setInterval(60000)
        self.timer.timeout.connect(lambda: self._load_videos(manual=False))

        self._add_time(QTime.currentTime())
        self._on_tab_change()

    # ---------- Integration ----------
    def start(self):
        """Метод для запуску з кнопки на самій сторінці"""
        self._log("▶ Старт планування")
        self.is_running = True
        self.running_signal.emit(True)
        table = self._current_table()
        has_sel = any(
            isinstance(table.cellWidget(r, self.COL_CHECK), QWidget) and table.cellWidget(r, self.COL_CHECK).findChild(QCheckBox).isChecked()
            for r in range(table.rowCount())
        )
        mode = "selected" if has_sel else "all"
        self._plan(mode=mode)

    def stop(self):
        """Метод для зупинки з кнопки на самій сторінці"""
        self._log("⛔ Зупинено вручну")
        self.is_running = False
        self.running_signal.emit(False)

    def handle_start(self, checked=False):
        """Метод для запуску з головної панелі керування"""
        self.start()

    def handle_stop(self):
        """Метод для зупинки з головної панелі керування"""
        self.stop()

    # ---------- Utils ----------
    def _on_tab_change(self, *_):
        is_plannable = self.tabs.currentIndex() in (self.TAB_VIDEOS, self.TAB_SHORTS)
        self.btn_start_plan.setEnabled(is_plannable)
        self.btn_stop_plan.setEnabled(is_plannable)
        self._apply_filter()
        self._update_selected_count()
        self._update_planned_count()

    def _log(self, msg: str):
        # Відправляємо повідомлення через сигнал
        self.log_signal.emit(msg)

    def _create_table(self) -> QTableWidget:
        t = QTableWidget()
        t.setWordWrap(False)
        t.setColumnCount(8)
        t.setHorizontalHeaderLabels([
            "☑", "🖼 Прев'ю", "📄 Назва", "📝 Опис",
            "⏱ Тривалість", "👁 Перегляди", "📊 Статус", "📅 Заплановано на"
        ])
        header = t.horizontalHeader()
        header.setSectionResizeMode(self.COL_TITLE, QHeaderView.Stretch)
        header.setSectionResizeMode(self.COL_DESC, QHeaderView.Stretch)
        for col in [self.COL_CHECK, self.COL_THUMB, self.COL_DURATION, self.COL_VIEWS, self.COL_STATUS, self.COL_SCHEDULED_AT]:
            header.setSectionResizeMode(col, QHeaderView.ResizeToContents)

        t.setSelectionBehavior(QAbstractItemView.SelectRows)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.verticalHeader().setDefaultSectionSize(44)
        t.verticalHeader().hide()
        t.setAlternatingRowColors(True)
        return t

    # ---------- Google API ----------
    def _authorize(self):
        try:
            self.youtube, self.email, _ = authorize_google(self.client_secret_file)
            if self.youtube:
                self._load_channel_info()
                self._load_videos()
            else:
                 self._log(f"❌ Авторизація не вдалась. Перевірте client_secret.json.")
                 QMessageBox.warning(self, "YouTube", f"Не вдалося авторизуватись. Перевірте налаштування API.")

        except Exception as e:
            self._log(f"❌ ПОМИЛКА авторизації: {e}")
            QMessageBox.critical(self, "YouTube", f"Не вдалося авторизуватись:\n{e}")

    def _upload_json(self):
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(self, "Виберіть client_secret.json", "", "JSON Files (*.json)")
        if path:
            self.client_secret_file = path
            self._log(f"📂 Завантажено client_secret.json: {os.path.basename(path)}")

    def _revoke(self):
        if revoke_token():
            QMessageBox.information(self, "YouTube", "Токени видалено")
            self.youtube = None
            self.email = None
            self.channel_lbl.setText("Канал: (не авторизовано)")
            self.stats_lbl.setText("📊 —")
            self.avatar_lbl.clear()
            if hasattr(self, "channel_stats_text"):
                del self.channel_stats_text

    def _load_channel_info(self):
        if not self.youtube:
            return
        try:
            r = self.youtube.channels().list(part="snippet,statistics", mine=True).execute()
            if not r.get("items"):
                return
            info = r["items"][0]
            title = info["snippet"]["title"]
            stats = info.get("statistics", {})
            subs = _fmt_count(stats.get("subscriberCount", 0))
            vids = _fmt_count(stats.get("videoCount", 0))
            views = _fmt_count(stats.get("viewCount", 0))
            self.channel_lbl.setText(f"{title} ({self.email or 'акаунт'})")
            
            # Store base stats text to avoid parsing the label later
            self.channel_stats_text = f"👥 {subs} підписників | ▶ {vids} відео | 👁 {views} переглядів"
            self.stats_lbl.setText(self.channel_stats_text)

            thumb_url = info["snippet"]["thumbnails"].get("default", {}).get("url")
            if thumb_url:
                # Завантаження в окремому потоці, щоб не блокувати UI
                self.image_loader = ImageLoader(thumb_url)
                self.image_loader.finished.connect(self.avatar_lbl.setPixmap)
                self.image_loader.start()
        except Exception as e:
            self._log(f"ПОМИЛКА отримання даних каналу: {e}")

    # ---------- Fetch library ----------
    def _fetch_full_library(self):
        """Повна вибірка: uploads-плейлист + search.forMine, деталі пачками."""
        if not self.youtube:
            return {"videos": [], "shorts": [], "streams": [], "stream_records": []}
        try:
            ch = self.youtube.channels().list(part="contentDetails", mine=True).execute()
            uploads_id = ch["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

            all_ids = set()
            for source in ['playlist', 'search']:
                token = None
                while True:
                    if source == 'playlist':
                        req = self.youtube.playlistItems().list(part="contentDetails", maxResults=50, playlistId=uploads_id, pageToken=token)
                        result = req.execute()
                        items = result.get("items", [])
                        all_ids.update(it["contentDetails"]["videoId"] for it in items if it.get("contentDetails", {}).get("videoId"))
                    else: # search
                        req = self.youtube.search().list(part="id", forMine=True, type="video", order="date", maxResults=50, pageToken=token)
                        result = req.execute()
                        items = result.get("items", [])
                        all_ids.update(it["id"]["videoId"] for it in items if it.get("id", {}).get("videoId"))

                    token = result.get("nextPageToken")
                    if not token:
                        break

            if not all_ids:
                return {"videos": [], "shorts": [], "streams": [], "stream_records": []}

            items, all_ids_list = [], list(all_ids)
            for i in range(0, len(all_ids_list), 50):
                chunk = all_ids_list[i:i + 50]
                vr = self.youtube.videos().list(
                    part="snippet,contentDetails,statistics,status,liveStreamingDetails",
                    id=",".join(chunk)
                ).execute()
                items.extend(vr.get("items", []))

            videos, shorts, streams, stream_records = [], [], [], []
            for it in items:
                sn, st, cd, lsd = it.get("snippet", {}), it.get("status", {}), it.get("contentDetails", {}), it.get("liveStreamingDetails", {})
                secs = _iso8601_to_seconds(cd.get("duration"))
                live_bc = (sn.get("liveBroadcastContent") or "none").lower()
                v = {
                    "id": it.get("id"), "title": sn.get("title", ""), "description": sn.get("description", ""),
                    "duration": cd.get("duration"), "viewCount": int((it.get("statistics", {}) or {}).get("viewCount", 0) or 0),
                    "privacyStatus": st.get("privacyStatus"), "publishAt": st.get("publishAt"),
                    "publishedAt": sn.get("publishedAt"), "thumbnails": sn.get("thumbnails", {}),
                    "tags": sn.get("tags", []), "liveBC": live_bc, "lsd": lsd or {}
                }
                if live_bc in ("live", "upcoming"): streams.append(v)
                elif lsd and secs >= STREAM_MIN_SEC: stream_records.append(v)
                elif secs <= SHORTS_MAX_SEC: shorts.append(v)
                else: videos.append(v)

            self._log(f"Отримано {len(items)} елементів: {len(videos)} відео, {len(shorts)} shorts, {len(streams)} стрімів, {len(stream_records)} записів.")
            return {"videos": videos, "shorts": shorts, "streams": streams, "stream_records": stream_records}
        except Exception as e:
            self._log(f"❌ ПОМИЛКА отримання відео: {e}")
            return {"videos": [], "shorts": [], "streams": [], "stream_records": []}


    def _load_videos(self, manual=False):
        if not self.youtube:
            if manual:
                QMessageBox.information(self, "YouTube", "Спочатку потрібно авторизуватись.")
            return
        self._log("🔎 Завантаження відеотеки…")
        data = self._fetch_full_library()

        self.base_videos = sorted(data.get("videos", []), key=lambda x: x.get('publishedAt') or 'z', reverse=True)
        self.base_shorts = sorted(data.get("shorts", []), key=lambda x: x.get('publishedAt') or 'z', reverse=True)
        self.base_streams = sorted(data.get("streams", []), key=lambda x: (x.get('lsd',{}).get('scheduledStartTime') or 'z'), reverse=True)
        self.base_stream_records = sorted(data.get("stream_records", []), key=lambda x: x.get('publishedAt') or 'z', reverse=True)

        self._apply_len_limit()
        self._apply_filter()
        self._update_tab_badges()
        self._update_header_counters()

        self._log(f"📥 У таблиці: Відео={len(self.all_videos)} | Shorts={len(self.all_shorts)} | "
                  f"Стріми={len(self.all_streams)} | Записи={len(self.all_stream_records)}")

    # ---------- Класифікація з урахуванням ліміту довжини ----------
    def _apply_len_limit(self):
        limit = int(self.video_length_limit_sec)
        vids_ok, vids_too_long = [], []
        for v in self.base_videos:
            secs = _iso8601_to_seconds(v.get("duration"))
            if limit > 0 and secs >= limit:
                v["_forced_record"] = True
                vids_too_long.append(v)
            else:
                v.pop("_forced_record", None)
                vids_ok.append(v)

        self.all_videos = vids_ok
        self.all_shorts = list(self.base_shorts)
        self.all_streams = list(self.base_streams)
        self.all_stream_records = list(self.base_stream_records) + vids_too_long

    # ---------- Таблиці / стан ----------
    def _status_text(self, v):
        lbc = v.get("liveBC", "none").lower()
        if lbc == "live": return "🔴 Live"
        if lbc == "upcoming": return "🔴 Очікується"
        if v.get("_forced_record"): return f"📼 Дуже довге (> {_fmt_mmss(self.video_length_limit_sec)})"
        if v.get("lsd"): return "📼 Запис стріму"
        if v.get("publishAt"): return "📅 Заплановано"
        status_map = {"public": "🟢 Публічне", "private": "🔒 Приватне", "unlisted": "🔗 За посиланням"}
        return status_map.get(v.get("privacyStatus"), "—")


    def _date_cell_text(self, v):
        lbc = v.get("liveBC", "none").lower()
        lsd = v.get("lsd", {})
        if lbc in ("live", "upcoming"):
            return _fmt_date(lsd.get("scheduledStartTime") or lsd.get("actualStartTime"))
        if v.get("publishAt"):
            return _fmt_date(v["publishAt"])
        if v.get("privacyStatus") == "public":
            return _fmt_date(v.get("publishedAt"))
        return "—"

    def _populate_table(self, table: QTableWidget, items):
        table.setRowCount(0)
        table.setRowCount(len(items))
        for row, v in enumerate(items):
            # Checkbox
            chk_container = QWidget()
            chk_layout = QHBoxLayout(chk_container)
            chk_layout.setContentsMargins(0,0,0,0)
            chk_layout.setAlignment(Qt.AlignCenter)
            chk = QCheckBox()
            chk.stateChanged.connect(self._update_selected_count)
            chk_layout.addWidget(chk)
            table.setCellWidget(row, self.COL_CHECK, chk_container)

            # Title
            it_title = QTableWidgetItem(v.get("title") or "")
            it_title.setData(Qt.UserRole, v.get("id"))
            table.setItem(row, self.COL_TITLE, it_title)

            # Description
            desc_full = (v.get("description") or "").strip()
            desc_short = (desc_full[:200] + "…") if len(desc_full) > 200 else desc_full
            table.setItem(row, self.COL_DESC, QTableWidgetItem(desc_short))

            # Other cells
            table.setItem(row, self.COL_DURATION, _make_centered_item(parse_duration(v.get("duration")), "⏱"))
            table.setItem(row, self.COL_VIEWS, _make_centered_item(_fmt_count(v.get("viewCount", 0)), "👁"))
            table.setItem(row, self.COL_STATUS, _make_centered_item(self._status_text(v)))
            table.setItem(row, self.COL_SCHEDULED_AT, _make_centered_item(self._date_cell_text(v), "📅"))
        table.resizeColumnsToContents()
        table.horizontalHeader().setSectionResizeMode(self.COL_TITLE, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(self.COL_DESC, QHeaderView.Stretch)


    def _current_table(self):
        return self.tabs.currentWidget()

    def _toggle_all(self, state: bool):
        table = self._current_table()
        for r in range(table.rowCount()):
            w = table.cellWidget(r, self.COL_CHECK)
            if w:
                chk = w.findChild(QCheckBox)
                if chk: chk.setChecked(state)
        self._update_selected_count()

    def _update_selected_count(self):
        table = self._current_table()
        if not table: return
        cnt = 0
        for r in range(table.rowCount()):
            w = table.cellWidget(r, self.COL_CHECK)
            if w and w.findChild(QCheckBox).isChecked():
                cnt += 1
        self.selected_label.setText(f"Виділено: {cnt}")

    def _update_planned_count(self):
        table = self._current_table()
        if not table: return
        cnt = sum(1 for r in range(table.rowCount()) if table.item(r, self.COL_SCHEDULED_AT) and table.item(r, self.COL_SCHEDULED_AT).text().strip() not in ("—", "📅 —"))
        self.planned_label.setText(f"Заплановано: {cnt}")

    # ---------- Фільтрація за статусом ----------
    def _apply_filter(self):
        mode = self.combo_filter.currentData() or "all"

        def _is_scheduled(v):
            lbc = (v.get("liveBC") or "none").lower()
            lsd = v.get("lsd") or {}
            return bool(v.get("publishAt")) or (lbc in ("live", "upcoming") and bool(lsd.get("scheduledStartTime")))

        def _is_unpublished(v):
            lbc = (v.get("liveBC") or "none").lower()
            started = v.get("lsd", {}).get("actualStartTime") if lbc in ("live", "upcoming") else None
            return (v.get("privacyStatus") != "public") and (not v.get("publishAt")) and not started

        def _filter(items):
            if mode == "scheduled": return [x for x in items if _is_scheduled(x)]
            if mode == "unpublished": return [x for x in items if _is_unpublished(x)]
            return items

        self._populate_table(self.table_videos, _filter(self.all_videos))
        self._populate_table(self.table_shorts, _filter(self.all_shorts))
        self._populate_table(self.table_streams, _filter(self.all_streams))
        self._populate_table(self.table_stream_records, _filter(self.all_stream_records))
        self._update_selected_count()
        self._update_planned_count()

    # ---------- Бейджі / counters ----------
    def _update_tab_badges(self):
        self.tabs.setTabText(self.TAB_VIDEOS, f"▶ Відео ({len(self.all_videos)})")
        self.tabs.setTabText(self.TAB_SHORTS, f"🎬 Shorts ({len(self.all_shorts)})")
        self.tabs.setTabText(self.TAB_STREAMS, f"🔴 Трансляції ({len(self.all_streams)})")
        self.tabs.setTabText(self.TAB_STREAM_RECORDS, f"📼 Записи ({len(self.all_stream_records)})")


    def _update_header_counters(self):
        if not hasattr(self, 'channel_stats_text'):
            return 
            
        total = len(self.all_videos) + len(self.all_shorts) + len(self.all_streams) + len(self.all_stream_records)
        
        self.stats_lbl.setText(
            f"{self.channel_stats_text} | "
            f"Відображено: {total} ("
            f"Відео: {len(self.all_videos)}, "
            f"Shorts: {len(self.all_shorts)}, "
            f"Live: {len(self.all_streams)}, "
            f"Записи: {len(self.all_stream_records)})"
        )


    # ---------- Часи (піллюлі) ----------
    def _init_times_grid(self):
        self.times_area = QScrollArea()
        self.times_area.setWidgetResizable(True)
        self.times_widget = QWidget()
        self.times_grid = QGridLayout(self.times_widget)
        self.times_area.setWidget(self.times_widget)
        self.times = []
        self.times_area.setFrameShape(QFrame.NoFrame)

    def _add_time(self, t=None):
        if not isinstance(t, QTime):
            t = QTime.currentTime()

        row, col = divmod(len(self.times), 5) # 5 колонок для кращого вигляду

        edit = QTimeEdit(t)
        edit.setDisplayFormat("HH:mm" if self.combo_format.currentText() == "24h" else "hh:mm AP")

        self.times_grid.addWidget(edit, row, col)
        self.times.append(edit)

    def _del_time(self):
        if not self.times: return
        widget_to_remove = self.times.pop()
        self.times_grid.removeWidget(widget_to_remove)
        widget_to_remove.deleteLater()


    def _collect_times(self):
        return [e.time() for e in self.times if isinstance(e, QTimeEdit)] or [QTime(10, 0)]

    def _apply_time_format(self):
        fmt = "HH:mm" if self.combo_format.currentText() == "24h" else "hh:mm AP"
        for edit in self.times:
            edit.setDisplayFormat(fmt)

    def _tz_zone(self):
        return ZoneInfo("Europe/Kiev") if self.rb_europe.isChecked() else ZoneInfo("America/New_York")

    # ---------- Фільтр довжини — обробники ----------
    def _on_len_limit_change(self, *_):
        h = int(self.spin_max_hours.value())
        m = int(self.spin_max_minutes.value())
        self.video_length_limit_sec = h * 3600 + m * 60
        self._apply_len_limit()
        self._apply_filter()
        self._update_tab_badges()
        self._update_header_counters()

    def _reset_len_limit(self):
        self.spin_max_hours.setValue(DEFAULT_VIDEO_MAX_HOURS)
        self.spin_max_minutes.setValue(0)
        self._on_len_limit_change()

    # ---------- Планування ----------
    def _plan(self, mode: str):
        if not self.youtube:
            QMessageBox.warning(self, "Помилка", "Спочатку потрібно авторизуватись.")
            return
        if self.tabs.currentIndex() not in (self.TAB_VIDEOS, self.TAB_SHORTS):
            self._log("ℹ Планування доступне лише для Відео/Shorts")
            return

        table = self._current_table()
        rows_to_plan = [r for r in range(table.rowCount()) if (
            mode == "all" or (w := table.cellWidget(r, self.COL_CHECK)) and w.findChild(QCheckBox).isChecked()
        )]

        if not rows_to_plan:
            QMessageBox.information(self, "Планування", "Не вибрано жодного відео для планування.")
            return

        times = sorted(self._collect_times())
        start_dt = self.date_start.dateTime().toPython()
        interval_days = int(self.spin_interval.value())
        per_day = min(self.spin_perday.value(), len(times)) or 1
        tz = self._tz_zone()

        current_date = start_dt.date()
        time_idx, day_count = 0, 0
        total = len(rows_to_plan)

        self._log(f"🚀 Починаємо планування {total} відео...")

        for i, row_idx in enumerate(rows_to_plan):
            if not self.is_running:
                self._log("⛔ Планування перервано користувачем")
                break
                
            vid = table.item(row_idx, self.COL_TITLE).data(Qt.UserRole)
            if not vid: continue

            if day_count >= per_day:
                current_date += timedelta(days=interval_days)
                day_count, time_idx = 0, 0

            pub_time = times[time_idx]
            local_dt = datetime.combine(current_date, pub_time.toPython()).replace(tzinfo=tz)
            pub_utc_iso = local_dt.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')

            try:
                set_video_schedule(self.youtube, vid, pub_utc_iso)
                new_text = local_dt.strftime("%d.%m.%Y %H:%M")
                table.setItem(row_idx, self.COL_SCHEDULED_AT, _make_centered_item(new_text, "📅"))
                self._log(f"[{i+1}/{total}] ✅ {vid} заплановано на {new_text}")
                
                # Оновлюємо прогрес
                progress = int((i + 1) / total * 100)
                self.progress_signal.emit(progress, "Планування")
                
            except Exception as e:
                self._log(f"[{i+1}/{total}] ❌ ПОМИЛКА планування {vid}: {e}")
                table.item(row_idx, self.COL_SCHEDULED_AT).setText("❌ Помилка")

            day_count += 1
            time_idx = (time_idx + 1) % len(times)

            if self.cb_throttle.isChecked():
                QApplication.processEvents()
                QThread.msleep(2000)

        self._log(f"🎉 Планування завершено.")
        self.is_running = False
        self.running_signal.emit(False)
        self.progress_signal.emit(0, "")
        self._update_planned_count()
        QMessageBox.information(self, "Завершено", f"Планування {total} відео завершено.")


    # ---------- Автооновлення ----------
    def _toggle_auto_refresh(self):
        if self.timer.isActive():
            self.timer.stop()
            self.btn_auto.setText("⏱ Старт автооновлення (1 хв)")
            self.btn_auto.setChecked(False)
        else:
            self.timer.start()
            self.btn_auto.setText("⏸ Зупинити автооновлення")
            self.btn_auto.setChecked(True)
            self._load_videos(manual=False)


class ImageLoader(QThread):
    finished = Signal(QPixmap)
    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        try:
            data = requests.get(self.url, timeout=10).content
            pixmap = QPixmap()
            pixmap.loadFromData(data)
            self.finished.emit(pixmap.scaled(84, 84, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        except Exception as e:
            print(f"Помилка завантаження зображення: {e}")


# --- Головний запуск ---
if __name__ == '__main__':
    app = QApplication(sys.argv)

    # Завантаження та застосування стилів з файлу
    try:
        with open("dark_modern.qss", "r", encoding="utf-8") as f:
            stylesheet = f.read()
        app.setStyleSheet(stylesheet)
    except FileNotFoundError:
        print("ПОПЕРЕДЖЕННЯ: Файл стилів 'dark_modern.qss' не знайдено. Буде використано стандартний вигляд.")

    window = QMainWindow()
    planner_widget = PlannerTab()

    central_container = QWidget()
    container_layout = QVBoxLayout(central_container)
    container_layout.setContentsMargins(15, 15, 15, 15)
    container_layout.addWidget(planner_widget)

    window.setCentralWidget(central_container)
    window.setWindowTitle("YouTube Planner")
    window.resize(1400, 900)
    window.show()

    sys.exit(app.exec())