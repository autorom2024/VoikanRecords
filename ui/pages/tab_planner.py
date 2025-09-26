# tab_planner.py
import os
import re
import time
import requests
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QHBoxLayout, QTabWidget, QCheckBox, QSpinBox, QDateTimeEdit, QComboBox,
    QMessageBox, QHeaderView, QAbstractItemView, QScrollArea, QGridLayout,
    QTimeEdit, QRadioButton, QButtonGroup, QGraphicsOpacityEffect, QGroupBox,
    QSizePolicy, QAbstractScrollArea, QApplication, QFrame, QHBoxLayout as HBox
)
from PySide6.QtCore import Qt, QTimer, QDateTime, QTime, QPropertyAnimation, QThread
from PySide6.QtGui import QPixmap, QColor

from google_api import authorize_google, set_video_schedule, revoke_token
from helpers_youtube import parse_duration


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

    def __init__(self, parent=None):
        super().__init__(parent)

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
        self.channel_lbl.setStyleSheet("font-size: 18px; font-weight: 700;")
        self.stats_lbl = QLabel("📊 —")
        self.stats_lbl.setStyleSheet("font-size: 13px; color: #ccc;")
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
        planner_grp.setObjectName("PlannerGroup")
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

        # Часи публікацій (піллюлі)
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
        self.btn_start_plan.setMinimumHeight(44)
        self.btn_stop_plan = QPushButton("⛔ Зупинити")
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

        # >>> Фільтр довжини для вкладки «Відео»
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

        # нові сигнали фільтра довжини
        self.spin_max_hours.valueChanged.connect(self._on_len_limit_change)
        self.spin_max_minutes.valueChanged.connect(self._on_len_limit_change)
        self.btn_len_reset.clicked.connect(self._reset_len_limit)

        self.timer = QTimer(self)
        self.timer.setInterval(60000)
        self.timer.timeout.connect(lambda: self._load_videos(manual=False))

        # дефолтний час для планувальника
        self._add_time(QTime.currentTime())

        self._apply_global_qss()
        self._on_tab_change()

    # ---------- Integration ----------
    def start(self):
        self._log("▶ Старт планування")
        table = self._current_table()
        has_sel = any(
            isinstance(table.cellWidget(r, self.COL_CHECK), QCheckBox)
            and table.cellWidget(r, self.COL_CHECK).isChecked()
            for r in range(table.rowCount())
        )
        mode = "selected" if has_sel else "all"
        self._plan(mode=mode)

    def stop(self):
        self._log("⛔ Зупинено вручну")

    # ---------- Utils ----------
    def _on_tab_change(self, *_):
        # Планувальник лише для Відео/Shorts
        self.btn_start_plan.setEnabled(self.tabs.currentIndex() in (self.TAB_VIDEOS, self.TAB_SHORTS))
        self._apply_filter()
        self._update_selected_count()
        self._update_planned_count()

    def _log(self, msg: str):
        mw = self.window()
        if hasattr(mw, "log"):
            mw.log(self, msg)
        else:
            print(msg)

    def _create_table(self) -> QTableWidget:
        t = QTableWidget()
        t.setWordWrap(False)
        t.setColumnCount(8)
        t.setHorizontalHeaderLabels([
            "☑", "🖼 Прев’ю", "📄 Назва", "📝 Опис",
            "⏱ Тривалість", "👁 Перегляди", "📊 Статус", "📅 Заплановано на"
        ])
        header = t.horizontalHeader()
        header.setSectionResizeMode(self.COL_TITLE, QHeaderView.Stretch)
        header.setSectionResizeMode(self.COL_DESC, QHeaderView.Stretch)
        header.setSectionResizeMode(self.COL_DURATION, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self.COL_VIEWS, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self.COL_STATUS, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self.COL_SCHEDULED_AT, QHeaderView.ResizeToContents)

        t.setSelectionBehavior(QAbstractItemView.SelectRows)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.verticalHeader().setDefaultSectionSize(44)
        t.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        t.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        return t

    # ---------- Google API ----------
    def _authorize(self):
        try:
            self.youtube, email, _ = authorize_google(self.client_secret_file)
            self.email = email
            self._load_channel_info()
            self._load_videos()
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

    def _load_channel_info(self):
        if not self.youtube:
            return
        try:
            r = self.youtube.channels().list(part="snippet,statistics,contentDetails", mine=True).execute()
            if not r.get("items"):
                return
            info = r["items"][0]
            title = info["snippet"]["title"]
            subs = _fmt_count(info["statistics"].get("subscriberCount", 0))
            vids = _fmt_count(info["statistics"].get("videoCount", 0))
            views = _fmt_count(info["statistics"].get("viewCount", 0))
            self.channel_lbl.setText(f"{title} ({self.email or 'account'})")
            self.stats_lbl.setText(f"👥 {subs} підписників | ▶ {vids} відео | 👁 {views} переглядів")
            thumb = info["snippet"]["thumbnails"].get("default", {}).get("url")
            if thumb:
                pm = QPixmap()
                pm.loadFromData(requests.get(thumb, timeout=8).content)
                self.avatar_lbl.setPixmap(pm.scaled(84, 84, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        except Exception as e:
            self._log(f"ПОМИЛКА отримання даних каналу: {e}")

    # ---------- Fetch library ----------
    def _fetch_full_library(self):
        """Повна вибірка: uploads-плейлист + search.forMine, деталі пачками."""
        if not self.youtube:
            return {"videos": [], "shorts": [], "streams": [], "stream_records": []}
        try:
            # 1) всі ID з uploads
            ch = self.youtube.channels().list(part="contentDetails", mine=True).execute()
            uploads = ch["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
            ids_up, token = [], None
            while True:
                pl = self.youtube.playlistItems().list(
                    part="contentDetails", maxResults=50, playlistId=uploads, pageToken=token
                ).execute()
                ids_up.extend(it["contentDetails"]["videoId"]
                              for it in pl.get("items", [])
                              if it.get("contentDetails", {}).get("videoId"))
                token = pl.get("nextPageToken")
                if not token:
                    break

            # 2) додатково — все з пошуку (щоб не втратити заплановані/приватні)
            ids_search, token = [], None
            while True:
                sr = self.youtube.search().list(
                    part="id", forMine=True, type="video", order="date", maxResults=50, pageToken=token
                ).execute()
                ids_search.extend(it["id"]["videoId"]
                                  for it in sr.get("items", [])
                                  if it.get("id", {}).get("videoId"))
                token = sr.get("nextPageToken")
                if not token:
                    break

            all_ids = list(dict.fromkeys(ids_up + ids_search))
            if not all_ids:
                return {"videos": [], "shorts": [], "streams": [], "stream_records": []}

            # 3) деталі
            items = []
            for i in range(0, len(all_ids), 50):
                chunk = all_ids[i:i + 50]
                vr = self.youtube.videos().list(
                    part="snippet,contentDetails,statistics,status,liveStreamingDetails",
                    id=",".join(chunk)
                ).execute()
                items.extend(vr.get("items", []))

            # 4) початкова класифікація
            videos, shorts, streams, stream_records = [], [], [], []
            for it in items:
                sn = it.get("snippet", {}) or {}
                st = it.get("status", {}) or {}
                cd = it.get("contentDetails", {}) or {}
                lsd = it.get("liveStreamingDetails", {}) or {}
                secs = _iso8601_to_seconds(cd.get("duration"))
                live_bc = (sn.get("liveBroadcastContent") or "none").lower()

                v = {
                    "id": it.get("id"),
                    "title": sn.get("title", ""),
                    "description": sn.get("description", ""),
                    "duration": cd.get("duration"),
                    "viewCount": int((it.get("statistics", {}) or {}).get("viewCount", 0) or 0),
                    "privacyStatus": st.get("privacyStatus"),
                    "publishAt": st.get("publishAt"),
                    "publishedAt": sn.get("publishedAt"),
                    "thumbnails": sn.get("thumbnails", {}),
                    "tags": sn.get("tags", []),
                    "liveBC": live_bc,
                    "lsd": lsd or {},
                }

                if live_bc in ("live", "upcoming"):
                    streams.append(v)
                elif lsd and secs >= STREAM_MIN_SEC:
                    # завершений стрім (за ознаками API)
                    stream_records.append(v)
                elif secs <= SHORTS_MAX_SEC:
                    shorts.append(v)
                else:
                    videos.append(v)

            self._log(f"[W1] Отримано [{_make_bar(100)}] 100.0% | Total {len(items)} | "
                      f"Відео:{len(videos)} | Shorts:{len(shorts)} | Стріми:{len(streams)} | Записи:{len(stream_records)}")

            return {"videos": videos, "shorts": shorts, "streams": streams, "stream_records": stream_records}
        except Exception as e:
            self._log(f"❌ ПОМИЛКА отримання відео: {e}")
            return {"videos": [], "shorts": [], "streams": [], "stream_records": []}

    def _load_videos(self, manual=False):
        if not self.youtube:
            return
        self._log("🔎 Завантаження відеотеки…")
        data = self._fetch_full_library()

        self.base_videos = data.get("videos", [])
        self.base_shorts = data.get("shorts", [])
        self.base_streams = data.get("streams", [])
        self.base_stream_records = data.get("stream_records", [])

        self._apply_len_limit()
        self._apply_filter()
        self._update_tab_badges()
        self._update_header_counters()

        self._log(f"📥 У таблиці: Відео={len(self.all_videos)} | Shorts={len(self.all_shorts)} | "
                  f"Стріми={len(self.all_streams)} | Записи={len(self.all_stream_records)}")

    # ---------- Класифікація з урахуванням ліміту довжини ----------
    def _apply_len_limit(self):
        """
        Формує self.all_* на основі базових списків і користувацького ліміту довжини
        для вкладки «Відео». Все, що довше ліміту, з «Відео» прибираємо
        і показуємо у «Записах стрімів» як «Дуже довге відео».
        """
        limit = int(self.video_length_limit_sec)

        # Відео: лише коротші за ліміт
        vids_ok = []
        vids_too_long = []
        for v in self.base_videos:
            secs = _iso8601_to_seconds(v.get("duration"))
            if limit > 0 and secs >= limit:
                vv = dict(v)
                vv["_forced_record"] = True
                vids_too_long.append(vv)
            else:
                vids_ok.append(v)

        # Скомпонувати вихідні масиви
        self.all_videos = vids_ok
        self.all_shorts = list(self.base_shorts)
        self.all_streams = list(self.base_streams)
        self.all_stream_records = list(self.base_stream_records) + vids_too_long

    # ---------- Таблиці / стан ----------
    def _status_text(self, v):
        lbc = (v.get("liveBC") or "none").lower()
        if lbc == "live":
            return "🔴 Live"
        if lbc == "upcoming":
            return "🔴 Очікується"

        # Якщо примусово перенесено з Відео через ліміт
        if v.get("_forced_record"):
            return f"📼 Дуже довге відео (>{self.spin_max_hours.value()}ч)"

        if v.get("lsd"):
            # запис стріму (за даними API)
            return "📼 Запис стріму"

        if v.get("publishAt"):
            return "📅 Заплановано"

        p = v.get("privacyStatus")
        if p == "public":
            return "Публік."
        if p == "private":
            return "🔒 Приватне"
        if p == "unlisted":
            return "👥 Для друзів"
        return "—"

    def _date_cell_text(self, v):
        lbc = (v.get("liveBC") or "none").lower()
        lsd = v.get("lsd") or {}
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
            chk = QCheckBox()
            chk.stateChanged.connect(self._update_selected_count)
            table.setCellWidget(row, self.COL_CHECK, chk)

            it_title = QTableWidgetItem(v.get("title") or "")
            it_title.setData(Qt.UserRole, v.get("id"))
            table.setItem(row, self.COL_TITLE, it_title)

            desc_full = (v.get("description") or "").strip()
            table.setItem(row, self.COL_DESC, QTableWidgetItem((desc_full[:200] + "…") if len(desc_full) > 200 else desc_full))

            table.setItem(row, self.COL_DURATION, _make_centered_item(parse_duration(v.get("duration")), "⏱"))
            table.setItem(row, self.COL_VIEWS, _make_centered_item(_fmt_count(v.get("viewCount", 0)), "👁"))
            table.setItem(row, self.COL_STATUS, _make_centered_item(self._status_text(v)))
            table.setItem(row, self.COL_SCHEDULED_AT, _make_centered_item(self._date_cell_text(v), "📅"))

    def _current_table(self):
        idx = self.tabs.currentIndex()
        return [self.table_videos, self.table_shorts, self.table_streams, self.table_stream_records][idx]

    def _toggle_all(self, state: bool):
        table = self._current_table()
        for r in range(table.rowCount()):
            w = table.cellWidget(r, self.COL_CHECK)
            if isinstance(w, QCheckBox):
                w.setChecked(state)
        self._update_selected_count()

    def _update_selected_count(self):
        table = self._current_table()
        cnt = 0
        for r in range(table.rowCount()):
            w = table.cellWidget(r, self.COL_CHECK)
            if isinstance(w, QCheckBox) and w.isChecked():
                cnt += 1
        self.selected_label.setText(f"Виділено: {cnt}")

    def _update_planned_count(self):
        table = self._current_table()
        cnt = 0
        for r in range(table.rowCount()):
            it = table.item(r, self.COL_SCHEDULED_AT)
            if it and (it.text() or "").strip() not in ("", "—"):
                cnt += 1
        self.planned_label.setText(f"Заплановано: {cnt}")

    # ---------- Фільтрація за статусом ----------
    def _apply_filter(self):
        mode = (self.combo_filter.currentData() or "all")

        def _is_scheduled(v):
            lbc = (v.get("liveBC") or "none").lower()
            lsd = v.get("lsd") or {}
            return bool(v.get("publishAt")) or (lbc in ("live", "upcoming") and bool(lsd.get("scheduledStartTime")))

        def _is_unpublished(v):
            lbc = (v.get("liveBC") or "none").lower()
            started = v.get("lsd", {}).get("actualStartTime") if lbc in ("live", "upcoming") else None
            return (v.get("privacyStatus") != "public") and (not v.get("publishAt")) and not started

        def _filter(items):
            if mode == "scheduled":
                return [x for x in items if _is_scheduled(x)]
            if mode == "unpublished":
                return [x for x in items if _is_unpublished(x)]
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
        self.tabs.setTabText(self.TAB_STREAM_RECORDS, f"📼 Записи стрімів ({len(self.all_stream_records)})")

    def _update_header_counters(self):
        total = len(self.all_videos) + len(self.all_shorts) + len(self.all_streams) + len(self.all_stream_records)
        base = self.stats_lbl.text().split(" | ")
        prefix = " | ".join(base[:2]) if len(base) >= 2 else self.stats_lbl.text()
        self.stats_lbl.setText(
            f"{prefix} | ▶ Відео:{len(self.all_videos)} | 🎬 Shorts:{len(self.all_shorts)} | "
            f"🔴 Live:{len(self.all_streams)} | 📼 Записи:{len(self.all_stream_records)} | Разом:{total}"
        )

    # ---------- Часи (піллюлі) ----------
    def _init_times_grid(self):
        self.times_area = QScrollArea()
        self.times_area.setWidgetResizable(True)
        self.times_widget = QWidget()
        self.times_grid = QGridLayout(self.times_widget)
        self.times_grid.setHorizontalSpacing(10)
        self.times_grid.setVerticalSpacing(10)
        self.times_grid.setContentsMargins(4, 4, 4, 4)
        self.times_area.setWidget(self.times_widget)
        self.times = []

    def _add_time(self, t=None):
        if not isinstance(t, QTime):
            t = QTime.currentTime()
        idx = len(self.times) + 1
        row, col = divmod(len(self.times), 4)
        card = QFrame()
        card.setObjectName("timeCard")
        card.setFixedWidth(210)
        h = HBox(card)
        h.setContentsMargins(10, 6, 10, 6)
        h.setSpacing(8)
        lbl = QLabel(f"#{idx}")
        lbl.setObjectName("timeBadge")
        lbl.setFixedWidth(28)
        lbl.setAlignment(Qt.AlignCenter)
        edit = QTimeEdit(t)
        edit.setObjectName("timeEdit")
        edit.setDisplayFormat("HH:mm" if self.combo_format.currentText() == "24h" else "hh:mm AP")
        edit.setAlignment(Qt.AlignCenter)
        edit.setButtonSymbols(QTimeEdit.UpDownArrows)
        h.addWidget(lbl)
        h.addWidget(edit, 1)
        self.times_grid.addWidget(card, row, col)
        self.times.append((card, lbl, edit))

    def _del_time(self):
        if not self.times:
            return
        card, lbl, edit = self.times.pop()
        card.deleteLater()

    def _collect_times(self):
        times = [e.time() for _, _, e in self.times if isinstance(e, QTimeEdit)]
        return times or [QTime(10, 0)]

    def _apply_time_format(self):
        fmt = "HH:mm" if self.combo_format.currentText() == "24h" else "hh:mm AP"
        for _, __, edit in self.times:
            edit.setDisplayFormat(fmt)

    def _tz_zone(self):
        return ZoneInfo("Europe/Kiev") if self.rb_europe.isChecked() else ZoneInfo("America/New_York")

    def _apply_global_qss(self):
        self.setStyleSheet("""
        QWidget { font-size: 13px; color: #e8e8ee; }
        QLabel { color: #cfd2e3; }
        QGroupBox#PlannerGroup { border: 1px solid #2a2a36; border-radius: 12px; margin-top: 12px; padding: 10px 12px; }
        QGroupBox#PlannerGroup::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; color: #cfd2e3; }
        QSpinBox, QComboBox, QDateTimeEdit, QTimeEdit {
            background: #2a2a3a; border: 1px solid #3c3c4f; border-radius: 8px; padding: 6px 10px;
        }
        QPushButton { background: #2b2b40; color: #e8e8ee; border-radius: 10px; padding: 8px 14px; font-weight: 600; }
        QPushButton:hover { background: #3b3b57; }
        QTableWidget { background: #1c1c2a; gridline-color: #33384d; border: none; }
        QHeaderView::section { background: #26263a; padding: 6px; border: none; font-weight: 600; color: #cfd2e3; }
        QFrame#timeCard { background: #2a2a3a; border: 1px solid #3c3c4f; border-radius: 14px; }
        QLabel#timeBadge { background: #3a3a52; border-radius: 8px; padding: 4px 0; color: #e8e8ee; font-weight: 700; }
        QTimeEdit#timeEdit { font-size: 22px; font-weight: 700; background: transparent; border: none; padding: 2px 6px; min-height: 34px; }
        """)

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

    # ---------- Планування ----------
    def _plan(self, mode: str):
        if self.tabs.currentIndex() not in (self.TAB_VIDEOS, self.TAB_SHORTS):
            self._log("ℹ Планування доступне лише для Відео/Shorts")
            return

        table = self._current_table()
        rows = list(range(table.rowCount())) if mode == "all" else [
            r for r in range(table.rowCount())
            if isinstance(table.cellWidget(r, self.COL_CHECK), QCheckBox)
            and table.cellWidget(r, self.COL_CHECK).isChecked()
        ]

        times = self._collect_times()
        start_dt = self.date_start.dateTime().toPython()
        interval = int(self.spin_interval.value())
        per_day = min(self.spin_perday.value(), len(times)) or 1

        tz = self._tz_zone()
        idx_time = 0
        count_today = 0
        day_idx = 0
        total = len(rows)
        done = 0
        t0 = time.time()

        for row in rows:
            it_title = table.item(row, self.COL_TITLE)
            if not it_title:
                continue
            vid = it_title.data(Qt.UserRole)
            if not vid:
                continue

            day_date = (start_dt + timedelta(days=day_idx * interval)).date()
            qtime = times[idx_time]
            local_dt = datetime.combine(day_date, qtime.toPython()).replace(tzinfo=tz)
            pub_utc = local_dt.astimezone(timezone.utc)

            try:
                set_video_schedule(self.youtube, vid, pub_utc.isoformat())
                table.setItem(row, self.COL_SCHEDULED_AT,
                              _make_centered_item(pub_utc.astimezone().strftime("%d.%m.%Y %H:%M"), "📅"))
            except Exception as e:
                self._log(f"❌ ПОМИЛКА планування {vid}: {e}")

            done += 1
            idx_time = (idx_time + 1) % max(1, len(times))
            count_today += 1
            if count_today >= per_day:
                count_today = 0
                day_idx += 1

            if self.cb_throttle.isChecked():
                QApplication.processEvents()
                QThread.msleep(2000)  # 2 c/відео

        self._log(f"[W1] Планування завершено [{_make_bar(100)}] 100.0% | {_fmt_mmss(int(time.time()-t0))} | Total {done}/{total}")
        self._update_planned_count()

    # ---------- Автооновлення ----------
    def _toggle_auto_refresh(self):
        if self.timer.isActive():
            self.timer.stop()
            self.btn_auto.setText("⏱ Старт автооновлення (1 хв)")
        else:
            self.timer.start()
            self.btn_auto.setText("⏸ Зупинити автооновлення")
