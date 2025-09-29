# -*- coding: utf-8 -*-
# ui/pages/tab_autofill.py — v4.6 (FULL) - Адаптовано для 15-дюймового монітора
# Нове у v4.6:
# - Фікс: додано _save_preset_to_db та _load_preset_from_db (помилка AttributeError виправлена).
# - Переклад: title завжди ОРИГІНАЛ (keep_title=True), перекладаються лише description + (якщо є в тексті) хештеги.
# - Плейлісти: мультивибір (діалог із галочками), автододавання у ВСІ обрані після Autofill/Translate + масове «➕ Усі».
# - Табличні колонки: «Плейлісти» (список обраних) та «У плейлістах» (галочка + підказка x/y).
# - Аналіз каналу: оновлює Seed із топ-10 та (за потреби) ставить Тему; прогрес і повідомлення.
# - Центрування чекбоксів у таблиці; компактні кнопки; help-діалог; JSON-менеджер; завантаження client_secret.json.

from __future__ import annotations
import os, re, json, time, sqlite3, requests, traceback, glob, shutil
from datetime import datetime, timezone
from typing import List, Tuple

VERSION = "4.6"

# ====== GPT & фільтри ======
try:
    from .gpt.gpt_generator import gpt_autofill_metadata as gptx_autofill
except Exception:
    try:
        from gpt.gpt_generator import gpt_autofill_metadata as gptx_autofill
    except Exception:
        from gpt_generator import gpt_autofill_metadata as gptx_autofill

try:
    from .filters_manager import (
        apply_fast_filter as apply_filter_rows,
        is_published as is_pub,
        compute_status as compute_status_ext,
    )
except Exception:
    try:
        from filters_manager import apply_fast_filter as apply_filter_rows, is_published as is_pub, compute_status as compute_status_ext
    except Exception:
        # Локальні заглушки
        def compute_status_ext(v:dict)->str:
            privacy=(v.get("privacyStatus") or v.get("privacy") or "—").lower()
            if privacy=="public": return "Public"
            if privacy=="private": return "Private"
            if privacy=="unlisted": return "Unlisted"
            return "Draft/Other"
        def is_pub(v:dict)->bool:
            return compute_status_ext(v)=="Public"
        def apply_filter_rows(table, mode:str)->None:
            COL_STATUS=12
            for row in range(table.rowCount()):
                st_item=table.item(row,COL_STATUS)
                st=st_item.text() if st_item else "—"
                hide=False
                if mode=="Опубліковані": hide = (st!="Public")
                elif mode=="Неопубліковані": hide = (st=="Public")
                table.setRowHidden(row,hide)

# ====== Qt ======
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QTabWidget, QCheckBox, QComboBox, QLineEdit, QTextEdit,
    QSpinBox, QGroupBox, QGridLayout, QMessageBox, QWidget as QW, QProgressBar,
    QSizePolicy, QFileDialog, QGraphicsOpacityEffect, QDialog, QDialogButtonBox, QTextBrowser,
    QListWidget, QListWidgetItem, QScrollArea
)
from PySide6.QtCore import Qt, QTimer, Signal, QThread, QSettings
from PySide6.QtGui import QPixmap, QFont

from google_api_autofill import authorize_google_autofill, get_videos_split, TOKEN_FILE
try:
    from google_api_autofill import CLIENT_SECRET_FILE
except Exception:
    CLIENT_SECRET_FILE = os.path.join(os.getcwd(), "client_secret.json")

from helpers_youtube import parse_duration

APP_NAME = "AutoFill"
ORG = "Voikan"
APP = "MultimediaPanel"
CATEGORY_MUSIC = 10
DB_PATH = os.path.join(os.getcwd(), "autofill.db")
JSON_DIR = os.path.join(os.getcwd(), "json")
os.makedirs(JSON_DIR, exist_ok=True)

# -------------------- helpers / ui --------------------
def _flag(code: str) -> str:
    m = {
        "en":"🇬🇧","zh":"🇨🇳","hi":"🇮🇳","es":"🇪🇸","fr":"🇫🇷",
        "ar":"🇸🇦","bn":"🇧🇩","pt":"🇵🇹",
        "ru":"🇷🇺","ur":"🇵🇰","id":"🇮🇩","de":"🇩🇪","ja":"🇯🇵","sw":"🇰🇪","mr":"🇮🇳","te":"🇮🇳",
        "tr":"🇹🇷","ta":"🇮🇳","vi":"🇻🇳","ko":"🇰🇷","it":"🇮🇹","pl":"🇵🇱","uk":"🇺🇦","nl":"🇳🇱",
        "el":"🇬🇷","he":"🇮🇱","cs":"🇨🇿","ro":"🇷🇴","hu":"🇭🇺","th":"🇹🇭",
    }
    return m.get(code, "🏳️")

LANGS_TOP30 = [
    ("English","en"),("Chinese","zh"),("Hindi","hi"),("Spanish","es"),("French","fr"),
    ("Arabic","ar"),("Bengali","bn"),("Portuguese","pt"),("Russian","ru"),("Urdu","ur"),
    ("Indonesian","id"),("German","de"),("Japanese","ja"),("Swahili","sw"),("Marathi","mr"),
    ("Telugu","te"),("Turkish","tr"),("Tamil","ta"),("Vietnamese","vi"),("Korean","ko"),
    ("Italian","it"),("Polish","pl"),("Ukrainian","uk"),("Dutch","nl"),("Greek","el"),
    ("Hebrew","he"),("Czech","cs"),("Romanian","ro"),("Hungarian","hu"),("Thai","th"),
]

def _fmt_count(value) -> str:
    try: n = int(value)
    except Exception: return str(value or "0")
    if n < 1_000: return str(n)
    if n < 1_000_000: v=n/1_000.0; s=f"{v:.1f}".rstrip("0").rstrip("."); return f"{s}K"
    if n < 1_000_000_000: v=n/1_000_000.0; s=f"{v:.1f}".rstrip("0").rstrip("."); return f"{s}M"
    v=n/1_000_000_000.0; s=f"{v:.1f}".rstrip("0").rstrip("."); return f"{s}B"

class SortItem(QTableWidgetItem):
    def __init__(self, text: str, sort_key):
        super().__init__(text); self._key = sort_key
        self.setFlags(self.flags() & ~Qt.ItemIsEditable)
    def __lt__(self, other):
        a = getattr(self, "_key", self.text()); b = getattr(other, "_key", other.text())
        try:    return a < b
        except: return str(a) < str(b)

def _make_centered_item(text: str, sort_key=None, fallback="—"):
    t = text if (text and str(text).strip()) else fallback
    it = SortItem(t, sort_key if sort_key is not None else t); it.setTextAlignment(Qt.AlignCenter); return it

# ---- статус ----
def _status_sort_key(v: dict) -> tuple:
    order = {"Scheduled":0, "Private":1, "Unlisted":2, "Public":3, "Draft/Other":4}
    status = compute_status_ext(v)
    ts = v.get("publishAt") or v.get("scheduledPublishTime") or v.get("scheduled") or (v.get("status") or {}).get("publishAt")
    try:
        if ts:
            if isinstance(ts, (int, float)): dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            else: dt = datetime.fromisoformat(str(ts).replace("Z","+00:00"))
            tkey = int(dt.timestamp())
        else:
            tkey = 2**31
    except Exception:
        tkey = 2**31
    return (order.get(status, 9), tkey)

def trim_tags_for_youtube(tags):
    if not tags: return []
    out, seen, total = [], set(), 0
    for t in tags:
        clean = (" ".join(str(t).split())).strip(",;# ")
        if not clean: continue
        key = clean.lower()
        if key in seen: continue
        add_len = len(clean) + (1 if out else 0)
        if total + add_len > 480: break
        out.append(clean); seen.add(key); total += add_len
        if len(out) >= 30: break
    return out

# -------------------- OpenAI helpers --------------------
def _openai_chat(api_key: str, messages: list, model="gpt-4o-mini", temperature=0.2) -> str:
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": model, "messages": messages, "temperature": temperature}
    r = requests.post(url, headers=headers, json=payload, timeout=60)
    if r.status_code == 401: raise RuntimeError("OpenAI: 401 Unauthorized — недійсний ключ API")
    r.raise_for_status(); return r.json()["choices"][0]["message"]["content"]

def _json_loose(text: str) -> dict:
    s = (text or "").strip()
    i, j = s.find("{"), s.rfind("}")
    if i >= 0 and j > i: s = s[i:j+1]
    s = re.sub(r",\s*(\]|})", r"\1", s)
    try: return json.loads(s)
    except Exception: return json.loads(s.replace("'", '"'))

def _looks_like_placeholder(s: str) -> bool:
    s = (s or "").strip()
    if not s: return False
    low = s.lower()
    import re as _re
    if _re.fullmatch(r"(title|name|назва)\s*\d*", low): return True
    if _re.fullmatch(r"[\d\s/\\\-–—\.,()]+", s): return True
    if len(s) <= 3 and any(ch.isdigit() for ch in s): return True
    return False

# ===== Аналіз top10: зібрати seed і тему =====
VIBE_WORDS = {
    "chill","chillout","deep","deep chill","tropical","tropical house","lounge","ocean","sea",
    "sunset","night","paradise","beach","coast","breeze","vibes","relax","relaxation",
    "study","meditation","ambient","soft","slow","calm","evening","late night","cozy"
}

def _normalize_tokens(text: str) -> list[str]:
    if not text: return []
    text = re.sub(r"[^\w\s\-]", " ", text.lower())
    toks = []
    for w in text.split():
        w = w.strip("-_ ")
        if len(w) < 3: continue
        toks.append(w)
    return toks

def build_seed_from_top10(samples: list[dict], base_seed: str, max_len: int = 500) -> tuple[str, str]:
    """
    Повертає (new_seed, detected_theme).
    Беремо теги та слова з тайтлів, нормалізуємо, дедуплікуємо, сортуємо за частотою.
    """
    freq = {}
    # теги
    for s in samples:
        for t in (s.get("tags") or []):
            t = (" ".join(str(t).split())).strip(",;# ").lower()
            if not t or len(t) < 3: continue
            freq[t] = freq.get(t, 0) + 3  # теги важать більше
    # слова з тайтлів
    for s in samples:
        for w in _normalize_tokens(s.get("title", "")):
            if w in {"the","and","for","with","your","this","that"}: continue
            freq[w] = freq.get(w, 0) + 1

    # + базовий seed
    for w in [x.strip() for x in (base_seed or "").split(",") if x.strip()]:
        lw = w.lower()
        freq[lw] = freq.get(lw, 0) + 2

    # відсортуємо
    items = sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))
    # зберемо у рядок, поки не вийдемо за max_len
    out, used = [], set()
    acc = ""
    for w, _ in items:
        if w in used: continue
        cand = (", " if out else "") + w
        if len(acc) + len(cand) > max_len: break
        out.append(w); used.add(w); acc += cand
    new_seed = ", ".join(out)

    # тема: 3–5 найчастіших з VIBE_WORDS
    vibes = [w for w, _ in items if w in VIBE_WORDS]
    dedup = []
    for v in vibes:
        if v not in dedup: dedup.append(v)
        if len(dedup) >= 5: break
    theme = ", ".join(dedup) if dedup else ""
    return new_seed, theme

# -------------------- SQLite --------------------
class PresetDB:
    def __init__(self, path: str):
        self.path = path; self._ensure()
    def _conn(self): return sqlite3.connect(self.path)
    def _ensure(self):
        con = self._conn(); cur = con.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS channel_preset(
            channel_id TEXT PRIMARY KEY,
            base_prompt TEXT, extra_prompt TEXT, seed TEXT, theme TEXT,
            tags_count INTEGER, hash_count INTEGER, desc_limit INTEGER,
            strip_years INTEGER, default_lang TEXT, updated_at TEXT
        )""")
        cur.execute("""
        CREATE TABLE IF NOT EXISTS channel_langs(
            channel_id TEXT, code TEXT, selected INTEGER,
            PRIMARY KEY(channel_id, code)
        )""")
        cur.execute("""
        CREATE TABLE IF NOT EXISTS generated_cache(
            channel_id TEXT, video_id TEXT, mode TEXT,
            title TEXT, description TEXT, tags TEXT, keywords TEXT, updated_at TEXT,
            PRIMARY KEY(channel_id, video_id, mode)
        )""")
        con.commit(); con.close()
    def save_preset(self, channel_id: str, data: dict):
        con = self._conn(); cur = con.cursor()
        cur.execute("""
        INSERT INTO channel_preset(channel_id, base_prompt, extra_prompt, seed, theme, tags_count, hash_count, desc_limit, strip_years, default_lang, updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(channel_id) DO UPDATE SET
        base_prompt=excluded.base_prompt, extra_prompt=excluded.extra_prompt, seed=excluded.seed, theme=excluded.theme,
        tags_count=excluded.tags_count, hash_count=excluded.hash_count, desc_limit=excluded.desc_limit,
        strip_years=excluded.strip_years, default_lang=excluded.default_lang, updated_at=excluded.updated_at
        """, (
            channel_id, data.get("base_prompt",""), data.get("extra_prompt",""),
            data.get("seed",""), data.get("theme",""),
            int(data.get("tags_count",20)), int(data.get("hash_count",6)), int(data.get("desc_limit",1000)),
            1 if data.get("strip_years",True) else 0, data.get("default_lang","en"),
            datetime.utcnow().isoformat()
        ))
        con.commit(); con.close()
    def load_preset(self, channel_id: str) -> dict|None:
        con = self._conn(); cur = con.cursor()
        cur.execute("SELECT base_prompt,extra_prompt,seed,theme,tags_count,hash_count,desc_limit,strip_years,default_lang FROM channel_preset WHERE channel_id=?",(channel_id,))
        r = cur.fetchone(); con.close()
        if not r: return None
        return {"base_prompt":r[0] or "","extra_prompt":r[1] or "","seed":r[2] or "","theme":r[3] or "",
                "tags_count":int(r[4] or 20),"hash_count":int(r[5] or 6),"desc_limit":int(r[6] or 1000),
                "strip_years":bool(r[7]),"default_lang":r[8] or "en"}
    def save_langs(self, channel_id: str, selected:set[str]):
        con = self._conn(); cur = con.cursor()
        for _, code in LANGS_TOP30:
            cur.execute("""INSERT INTO channel_langs(channel_id,code,selected) VALUES(?,?,?)
                           ON CONFLICT(channel_id,code) DO UPDATE SET selected=excluded.selected""",
                        (channel_id, code, 1 if code in selected else 0))
        con.commit(); con.close()
    def load_langs(self, channel_id: str) -> set[str]:
        con = self._conn(); cur = con.cursor()
        cur.execute("SELECT code FROM channel_langs WHERE channel_id=? AND selected=1",(channel_id,))
        rows = cur.fetchall(); con.close()
        return {r[0] for r in rows}
    def upsert_generated(self, channel_id: str, video_id: str, mode: str, title: str, description: str, tags: list, keywords: str):
        con = self._conn(); cur = con.cursor()
        cur.execute("""
        INSERT INTO generated_cache(channel_id,video_id,mode,title,description,tags,keywords,updated_at)
        VALUES(?,?,?,?,?,?,?,?)
        ON CONFLICT(channel_id,video_id,mode) DO UPDATE SET
        title=excluded.title,description=excluded.description,tags=excluded.tags,keywords=excluded.keywords,updated_at=excluded.updated_at
        """,(channel_id,video_id,mode,title,description,json.dumps(tags or []),keywords or "",datetime.utcnow().isoformat()))
        con.commit(); con.close()

    def get_generated_for_videos(self, channel_id: str, ids:list[str]|None=None) -> list[dict]:
        con = self._conn(); cur = con.cursor()
        if ids:
            cur.execute(f"SELECT video_id,mode,title,description,tags,keywords FROM generated_cache WHERE channel_id=? AND video_id IN ({','.join('?'*len(ids))})",[channel_id,*ids])
        else:
            cur.execute("SELECT video_id,mode,title,description,tags,keywords FROM generated_cache WHERE channel_id=?",(channel_id,))
        rows = cur.fetchall(); con.close()
        out=[]
        for vid,mode,t,d,tg,kw in rows:
            try: tags=json.loads(tg or "[]")
            except Exception: tags=[]
            out.append({"videoId":vid,"mode":mode,"title":t or "","description":d or "","tags":tags,"keywords":kw or ""})
        return out

# -------------------- GPT wrappers --------------------
def gpt_autofill_metadata(*args, **kwargs):
    return gptx_autofill(*args, **kwargs)

# -------------------- Переклад --------------------
def gpt_translate_meta(api_key: str, title: str, description: str, target_lang_name: str, target_code: str, tags=None):
    tags = tags or []
    sys = (
        f"You are a STRICT, literal translator. "
        f"Translate ONLY the given fields into {target_lang_name} ({target_code}). "
        "Do NOT invent, rename, summarize or reorder. "
        "Preserve numbers, emojis, punctuation, URLs and hashtags. "
        "If a field is empty, return it empty. "
        "Return JSON with exactly these keys: title, description, tags.")
    user = (
        "Translate each field independently.\n"
        f"title: {title}\n"
        f"description: {description}\n"
        f"tags: {', '.join(tags)}\n"
        'Output JSON: {"title":"...", "description":"...", "tags":["..."]}')
    content = _openai_chat(api_key, [
        {"role": "system", "content": sys},
        {"role": "user", "content": user}
    ], "gpt-4o-mini", 0.0)
    obj = _json_loose(content)
    if not isinstance(obj, dict):
        return title, description, (tags or [])
    tt = str(obj.get("title", title) or title).strip()
    dd = str(obj.get("description", description) or description).strip()
    tg = obj.get("tags", tags)
    if isinstance(tg, str):
        tg_list = [t.strip() for t in tg.split(",") if t.strip()]
    elif isinstance(tg, list):
        tg_list = [str(t).strip() for t in tg if str(t).strip()]
    else:
        tg_list = list(tags or [])
    # Перекладач не має права генерувати нові назви та описи - тільки перекладати
    # Якщо переклад виглядає як заглушка, повертаємо оригінал
    if _looks_like_placeholder(tt): tt = title
    if _looks_like_placeholder(dd): dd = description
    return tt, dd, tg_list

try:
    from .gpt.gpt_translate_utils import gpt_translate_only as gptx_translate_only
except Exception:
    try:
        from gpt.gpt_translate_utils import gpt_translate_only as gptx_translate_only
    except Exception:
        try:
            from gpt_translate_utils import gpt_translate_only as gptx_translate_only
        except Exception:
            def gptx_translate_only(api_key, title, description, target_lang_name, target_code, tags=None, keep_title=False):
                tt, dd, tg = gpt_translate_meta(api_key, title, description, target_lang_name, target_code, tags)
                if keep_title: tt = title
                return tt, dd, tg

# -------------------- Workers --------------------
class TranslateWorker(QThread):
    sig_log=Signal(str); sig_progress=Signal(int); sig_video_done=Signal(int,str)
    sig_update_table=Signal(int,str,str,list); sig_error=Signal(str); sig_finished=Signal(int)
    def __init__(self,youtube,api_key,rows,targets,primary,channel_id,db,playlist_ids=None,parent=None):
        super().__init__(parent)
        self.youtube=youtube; self.api_key=api_key; self.rows=rows
        self.targets=targets; self.primary=primary; self.db=db; self.channel_id=channel_id
        self.playlist_ids = playlist_ids or []
        self.stop_requested = False
    def _retry(self,fn,attempts=5,base=0.9):
        for i in range(1,attempts+1):
            try:return fn()
            except Exception:
                if i==attempts: raise
                time.sleep(base*(1.7**(i-1)))
    def request_stop(self):
        self.stop_requested = True
    def _add_to_playlists(self, video_id: str):
        for pid in self.playlist_ids:
            try:
                self._retry(lambda: self.youtube.playlistItems().insert(
                    part="snippet",
                    body={"snippet": {"playlistId": pid, "resourceId": {"kind": "youtube#video", "videoId": video_id}}}
                ).execute(), attempts=4, base=0.8)
                self.sig_log.emit(f"videoId={video_id}: додано до плейлісту {pid}")
            except Exception as e:
                self.sig_log.emit(f"videoId={video_id}: помилка додавання у {pid}: {e}")
    def run(self):
        try:
            total=max(1,len(self.rows)*max(1,len(self.targets))); cur=0; done=0
            for (row,vid,v) in self.rows:
                if self.stop_requested: break
                base_title=v.get("title",""); base_desc=v.get("description",""); base_tags=v.get("tags") or []
                cat_id=v.get("categoryId") or CATEGORY_MUSIC
                self.sig_log.emit(f"=== ПЕРЕКЛАД: {base_title} [{vid}] ===")
                # 1) primary не чіпаємо (тільки фіксуємо defaultLanguage)
                try:
                    self._retry(lambda: self.youtube.videos().update(part="snippet",body={"id":vid,"snippet":{
                        "title":base_title,"description":base_desc,"tags":trim_tags_for_youtube(base_tags),
                        "defaultLanguage":self.primary,"categoryId":str(cat_id)}}).execute())
                    self.sig_log.emit(f"videoId={vid}: defaultLanguage={self.primary} встановлено")
                    if not self.stop_requested and self.playlist_ids:
                        self._add_to_playlists(vid)
                except Exception as e:
                    self.sig_log.emit(f"videoId={vid}: prelim skip: {e}")
                # 2) Локалізації (TITLE — ОРИГІНАЛ, description — переклад)
                loc={}
                for (name,code) in self.targets:
                    if code == self.primary:
                        self.sig_log.emit(f"skip {code} (primary)")
                        continue
                    if self.stop_requested: break
                    try:
                        tt,dd,tg=self._retry(lambda: gptx_translate_only(
                            self.api_key, base_title, base_desc, name, code, base_tags, keep_title=True  # <— title лишається оригіналом
                        ),attempts=4,base=0.8)
                        if code!=self.primary:
                            loc[code]={"title":base_title, "description":dd}  # підкреслюємо, що беремо оригінальний title
                        self.db.upsert_generated(self.channel_id,vid,"translate",base_title,dd,tg,"")
                        self.sig_log.emit(f"videoId={vid}: → {code} OK")
                    except Exception as e:
                        self.sig_log.emit(f"videoId={vid}: → {code} ERROR: {e}")
                    cur+=1; self.sig_progress.emit(int(cur/total*100)); time.sleep(0.1)
                if loc and not self.stop_requested:
                    try:
                        self._retry(lambda: self.youtube.videos().update(part="localizations",body={"id":vid,"localizations":loc}).execute(),attempts=5,base=1.0)
                        self.sig_log.emit(f"videoId={vid}: локалізації застосовано: {', '.join(loc.keys())}")
                    except Exception as e:
                        self.sig_log.emit(f"videoId={vid}: помилка локалізацій: {e}")
                self.sig_update_table.emit(row,base_title,base_desc,base_tags); done+=1
                self.sig_video_done.emit(row,"translate"); time.sleep(0.05)
            self.sig_finished.emit(done)
        except Exception as e:
            self.sig_error.emit(f"Translate worker fatal: {e}\n{traceback.format_exc()}")

class AutofillWorker(QThread):
    sig_log=Signal(str); sig_progress=Signal(int); sig_video_done=Signal(int,str)
    sig_update_table=Signal(int,str,str,list); sig_error=Signal(str); sig_finished=Signal(int)
    def __init__(self,youtube,api_key,rows,base_prompt,extra_prompt,theme,strip_years,tags_count,hash_count,desc_chars,seed,channel_id,db,only_json=False,playlist_ids=None,parent=None):
        super().__init__(parent)
        self.youtube=youtube; self.api_key=api_key; self.rows=rows
        self.base_prompt=base_prompt; self.extra_prompt=extra_prompt; self.theme=theme
        self.strip_years=strip_years; self.tags_count=tags_count; self.hash_count=hash_count; self.desc_chars=desc_chars
        self.seed=seed or []; self.channel_id=channel_id; self.db=db; self.only_json=only_json
        self.playlist_ids = playlist_ids or []
        self.stop_requested = False
    def _retry(self,fn,attempts=5,base=1.0):
        for i in range(1,attempts+1):
            try:return fn()
            except Exception:
                if i==attempts: raise
                time.sleep(base*(1.7**(i-1)))
    def request_stop(self):
        self.stop_requested = True
    def _add_to_playlists(self, video_id: str):
        for pid in self.playlist_ids:
            try:
                self._retry(lambda: self.youtube.playlistItems().insert(
                    part="snippet",
                    body={"snippet": {"playlistId": pid, "resourceId": {"kind": "youtube#video", "videoId": video_id}}}
                ).execute(), attempts=4, base=1.0)
                self.sig_log.emit(f"videoId={video_id}: додано до плейлісту {pid}")
            except Exception as e:
                self.sig_log.emit(f"videoId={video_id}: помилка додавання у {pid}: {e}")
    def run(self):
        try:
            total=max(1,len(self.rows))
            for i,(row,vid,v) in enumerate(self.rows,1):
                if self.stop_requested: break
                t0=v.get("title",""); d0=v.get("description",""); tags0=v.get("tags") or []
                cat_id=v.get("categoryId") or CATEGORY_MUSIC
                self.sig_log.emit(f"=== АВТОЗАПОВНЕННЯ: {t0} [{vid}] ===")
                try:
                    t,d,_tags_ignored,hashtags,kw=self._retry(lambda: gpt_autofill_metadata(
                        self.api_key,self.base_prompt,self.extra_prompt,self.theme,
                        t0,d0,self.tags_count,self.hash_count,self.desc_chars,
                        self.strip_years,self.seed or tags0
                    ),attempts=5,base=1.0)
                    tags_src = self.seed or tags0
                    tags = trim_tags_for_youtube(tags_src)
                    if self.tags_count: tags = tags[: self.tags_count]
                    kw = ", ".join(tags)
                except Exception as e:
                    self.sig_log.emit(f"videoId={vid}: GPT error: {e}"); continue
                final_desc = d.strip() + ( "\n\n" + " ".join("#"+h for h in (hashtags or [])) if (hashtags or []) else "" ).strip()
                self.db.upsert_generated(self.channel_id,vid,"autofill",t,final_desc,tags or [],kw or "")
                if not self.only_json and not self.stop_requested:
                    try:
                        self._retry(lambda: self.youtube.videos().update(part="snippet",body={"id":vid,"snippet":{
                            "title":t,"description":final_desc,"tags": tags,"categoryId":str(cat_id)}}).execute(),attempts=6,base=1.2)
                        self.sig_log.emit(f"Оновлено snippet: {vid}")
                        if self.playlist_ids: self._add_to_playlists(vid)
                    except Exception as e:
                        self.sig_log.emit(f"videoId={vid}: update error: {e} (збережено в JSON-кеші)")
                self.sig_update_table.emit(row,t,final_desc,tags or []); self.sig_video_done.emit(row,"autofill")
                self.sig_progress.emit(int(i/total*100)); time.sleep(0.05)
            self.sig_finished.emit(len(self.rows))
        except Exception as e:
            self.sig_error.emit(f"Autofill worker fatal: {e}\n{traceback.format_exc()}")

# -------------------- Playlist Picker Dialog --------------------
class PlaylistPickerDialog(QDialog):
    def __init__(self, parent, playlists: list[tuple[str,str]], selected_ids: list[str]):
        super().__init__(parent)
        self.setWindowTitle("Обрати плейлісти")
        self.resize(380, 450)  # Зменшено розмір
        v=QVBoxLayout(self)
        self.list=QListWidget()
        self.list.setAlternatingRowColors(True)
        for title,pid in playlists:
            it=QListWidgetItem(title)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            it.setCheckState(Qt.Checked if pid in selected_ids else Qt.Unchecked)
            it.setData(Qt.UserRole, pid)
            self.list.addItem(it)
        v.addWidget(QLabel("Відміть галочками плейлісти, куди додавати відео:"))
        v.addWidget(self.list,1)
        btns=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject)
        v.addWidget(btns)
    def result_ids(self)->list[str]:
        out=[]
        for i in range(self.list.count()):
            it=self.list.item(i)
            if it.checkState()==Qt.Checked:
                out.append(it.data(Qt.UserRole))
        return out

# -------------------- UI --------------------
class AnalyzeWorker(QThread):
    sig_log=Signal(str)
    sig_done=Signal(str,str,str,str)  # base, extra, seed, theme
    sig_error=Signal(str)
    def __init__(self, samples: list[dict], base_tpl:str, extra_tpl:str, seed_tpl:str, parent=None):
        super().__init__(parent); self.samples=samples; self.base_tpl=base_tpl; self.extra_tpl=extra_tpl; self.seed_tpl=seed_tpl
    def run(self):
        try:
            self.sig_log.emit("Аналіз: збираю seed із топ-10…")
            new_seed, theme = build_seed_from_top10(self.samples, self.seed_tpl, max_len=500)
            self.sig_done.emit(self.base_tpl, self.extra_tpl, new_seed, theme)
        except Exception as e:
            self.sig_error.emit(f"Аналіз помилка: {e}")

class AutoFillTab(QWidget):
    sig_log=Signal(str)

    # Дві нові колонки для плейлістів
    COL_CHECK=0; COL_DONE=1; COL_THUMB=2; COL_TITLE=3; COL_DESC=4; COL_TAGS=5
    COL_KEYS=6; COL_LANGS=7; COL_DURATION=8; COL_VIEWS=9; COL_PL_NAMES=10; COL_PL_STATE=11; COL_STATUS=12

    def __init__(self,parent=None):
        super().__init__(parent)
        self.youtube=None; self.channel_id=None; self._all_items_cache=[]
        self.db=PresetDB(DB_PATH)
        self._running_worker = None
        self._playlists = {}              # title -> id
        self._selected_playlist_ids = []  # для авто/масових дій

        # Встановлюємо компактний шрифт для всіх елементів
        compact_font = QFont()
        compact_font.setPointSize(8)  # Зменшений розмір шрифту
        
        root=QVBoxLayout(self)
        root.setSpacing(4)  # Зменшений проміжок між елементами
        root.setContentsMargins(6, 6, 6, 6)  # Зменшені поля

        # ==== Help ====
        self.btn_help=QPushButton("❓")
        self.btn_help.setToolTip("Коротка довідка: як працюють кнопки, ключі, джонсони, плейлісти")
        self.btn_help.clicked.connect(self._show_help)
        self.btn_help.setFont(compact_font)
        self.btn_help.setFixedSize(30, 25)  # Компактна кнопка

        # ==== Панель кнопок ====
        bar=QHBoxLayout(); root.addLayout(bar)
        bar.setSpacing(4)
        
        def style_btn(btn: QPushButton, bg: str, fg: str="white", sz: str="sm"):
            pad = "2px 6px" if sz=="sm" else "4px 8px"
            h   = 24 if sz=="sm" else 28
            btn.setFixedHeight(h)
            btn.setFont(compact_font)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {bg};
                    color: {fg};
                    border: none;
                    border-radius: 6px;
                    padding: {pad};
                    font-weight: 600;
                    font-size: 9px;
                }}
                QPushButton:hover {{ filter: brightness(1.05); }}
                QPushButton:disabled {{ background-color: #334155; color: #94a3b8; }}
            """)

        self.btn_auth=QPushButton("Авторизуватись");        style_btn(self.btn_auth,"#22c55e", "sm")
        self.btn_revoke=QPushButton("Видалити токени");      style_btn(self.btn_revoke,"#ef4444", "sm")
        self.btn_refresh=QPushButton("Оновити список");      style_btn(self.btn_refresh,"#3b82f6", "sm")
        self.btn_gpt=QPushButton("Автозаповнити (GPT)");     style_btn(self.btn_gpt,"#06b6d4", "sm")
        self.btn_loc=QPushButton("Перекласти");              style_btn(self.btn_loc,"#f59e0b","black", "sm")
        self.btn_analyze=QPushButton("Аналіз каналу");       style_btn(self.btn_analyze,"#a78bfa", "sm")
        self.btn_save_preset=QPushButton("Зберегти пресет"); style_btn(self.btn_save_preset,"#64748b", "sm")
        self.btn_export_json=QPushButton("Експорт JSON");    style_btn(self.btn_export_json,"#10b981", "sm")
        self.btn_import_json=QPushButton("Імпорт JSON");     style_btn(self.btn_import_json,"#14b8a6", "sm")
        self.btn_stop=QPushButton("Стоп");                   style_btn(self.btn_stop,"#dc2626", "sm"); self.btn_stop.setVisible(False)
        self.btn_load_client_secret = QPushButton("Завантажити ключ"); style_btn(self.btn_load_client_secret, "#9333ea", "sm")

        bar.addStretch()
        for b in (self.btn_help,self.btn_auth,self.btn_revoke,self.btn_analyze,self.btn_save_preset,self.btn_export_json,self.btn_import_json,self.btn_load_client_secret,self.btn_stop):
            bar.addWidget(b)

        # ==== OpenAI key ====
        s=QSettings(ORG,APP); saved_key=s.value("openai_key","",type=str) or ""
        self.ed_key=QLineEdit(saved_key); 
        self.ed_key.setPlaceholderText("OpenAI API Key"); 
        self.ed_key.setEchoMode(QLineEdit.Password)
        self.ed_key.setFont(compact_font)
        self.ed_key.setFixedHeight(24)
        
        self.btn_eye=QPushButton("👁"); 
        self.btn_eye.setCheckable(True)
        self.btn_eye.setFixedSize(24, 24)
        self.btn_eye.setFont(compact_font)
        
        self.btn_check_key=QPushButton("Перевірити ключ"); 
        style_btn(self.btn_check_key,"#0ea5e9","white","sm")
        self.lbl_key_status=QLabel("Ключ: невідомий"); 
        self.lbl_key_status.setStyleSheet("color:#e2e8f0; font-size: 9px;")
        self.btn_eye.toggled.connect(lambda ch: self.ed_key.setEchoMode(QLineEdit.Normal if ch else QLineEdit.Password))
        self.btn_check_key.clicked.connect(self._check_key)
        
        keyrow=QHBoxLayout(); 
        keyrow.setSpacing(4)
        keyrow.addWidget(self.ed_key,2); 
        keyrow.addWidget(self.btn_eye); 
        keyrow.addWidget(self.btn_check_key); 
        keyrow.addWidget(self.lbl_key_status); 
        keyrow.addStretch()

        # ==== Інфо каналу ====
        head=QHBoxLayout(); 
        root.addLayout(head)
        head.setSpacing(6)
        
        self.avatar_lbl=QLabel(); 
        self.avatar_lbl.setFixedSize(48,48);  # Зменшений аватар
        self.avatar_lbl.setScaledContents(True)
        
        self.channel_lbl=QLabel(f"Канал: (не авторизовано) · v{VERSION}"); 
        self.channel_lbl.setStyleSheet("font-size:12px;font-weight:700;")
        
        self.stats_lbl=QLabel("—"); 
        self.stats_lbl.setStyleSheet("color:#94a3b8; font-size: 10px;")
        
        head.addWidget(self.avatar_lbl); 
        col=QVBoxLayout(); 
        col.addWidget(self.channel_lbl); 
        col.addWidget(self.stats_lbl)
        head.addLayout(col); 
        head.addStretch(); 
        head.addLayout(keyrow)

        # ==== Тема / стиль + Аналіз ====
        theme_row=QHBoxLayout(); 
        root.addLayout(theme_row)
        theme_row.setSpacing(4)
        
        self.ed_theme=QLineEdit(); 
        self.ed_theme.setPlaceholderText("Тема каналу / стиль (напр.: 'chill r&b, ambient, lofi')")
        self.ed_theme.setFont(compact_font)
        self.ed_theme.setFixedHeight(24)
        
        theme_row.addWidget(QLabel("Тема:")); 
        theme_row.addWidget(self.ed_theme,1)
        self.btn_analyze.setToolTip("Збирає Seed з топ-10 відео, ставить Тему якщо порожньо, зберігає у пресеті")
        theme_row.addWidget(self.btn_analyze)

        # ==== GPT / Переклад ====
        g=QGroupBox("GPT / Переклад"); 
        g.setFont(compact_font)
        root.addWidget(g,2)
        
        grid=QGridLayout(g); 
        grid.setColumnStretch(0,2); 
        grid.setColumnStretch(1,2); 
        grid.setColumnStretch(2,2); 
        grid.setColumnStretch(3,1)
        grid.setSpacing(4)
        
        self.txt_base=QTextEdit(); 
        self.txt_base.setMinimumHeight(120)  # Зменшена висота
        self.txt_base.setFont(compact_font)
        
        self.txt_extra=QTextEdit(); 
        self.txt_extra.setMinimumHeight(120)
        self.txt_extra.setFont(compact_font)
        
        self.ed_seed_tags=QTextEdit(); 
        self.ed_seed_tags.setMinimumHeight(120)
        self.ed_seed_tags.setFont(compact_font)
        
        self.txt_base.setToolTip("Базовий промт (строгі правила для Title/Description/Hashtags)")
        self.txt_extra.setToolTip("Додатковий стиль/нотатки")
        self.ed_seed_tags.setToolTip("Seed/ключові слова/теги. У фінал ідуть теги з таблиці/seed (не від GPT).")
        
        # Дефолтні промти та seed
        self.txt_base.setPlainText(
            "You are a professional creative copywriter for a YouTube channel about Chillout / Deep Chill / Tropical House / Lounge mixes.\n"
            "Your job is to generate UNIQUE, CLICKBAIT-STYLE, CREATIVE and SEO-optimized titles and descriptions that sound human, poetic and atmospheric.\n\n"
            "STRICT RULES:\n\n"
            "1. TITLE:\n"
            "- Max 98 characters.\n"
            "- Every title must be DIFFERENT. Alternate between at least 4 styles:\n"
            "  • SCENIC (e.g., \"Whispers of Paradise 🌴 – Sunset Chill Escape\")\n"
            "  • EMOTIONAL (e.g., \"Feel the Horizon Glow 🌅 – Deep Chill Journey\")\n"
            "  • PLACE-BASED (e.g., \"Moonlit Shores 🌙 – Tropical Lounge Vibes\")\n"
            "  • POETIC (e.g., \"Golden Waves of Silence ✨ – Chillout Ocean Escape\")\n"
            "- Use vibe words: Chill, Deep Chill, Tropical, Ocean, Sunset, Night, Paradise, Lounge, Escape.\n"
            "- Include exactly 1 emoji 🌅🌙🌴🌊✨🍹 (placed naturally).\n"
            "- Do not repeat structure or wording from the last 40 outputs. Each title must feel fresh and original.\n"
            "- Avoid years (2024/2025) and banned words: unlock, secrets, magic.\n\n"
            "2. DESCRIPTION:\n"
            "- Up to 1200 characters.\n"
            "- Must be ORIGINAL for each video — never reuse sentences.\n"
            "- Write in 4 paragraphs: Hook; Music; Unique Scene; SEO block.\n"
            "- End with a block of hashtags.\n\n"
            "3. TAGS: do not generate (from table).\n"
            "4. HASHTAGS: exactly 30, all start with #, no duplicates.\n"
            "5. KEYWORDS: from seed list (max 500 chars).\n"
            "STYLE: poetic, cinematic, imaginative; no clichés; vary rhythm & imagery.\n"
            "OUTPUT JSON: {\"title\":\"...\",\"description\":\"...\",\"hashtags\":\"...\"}\n"
        )
        self.txt_extra.setPlainText(
            "Write naturally and visually. Keep a consistent chill/lounge aura without clichés. "
            "Prefer sensory verbs, soft motion, warm color words. Avoid generic SEO fluff."
        )
        self.ed_seed_tags.setPlainText(
            "chillout music, deep chill mix, tropical house vibes, ocean sunset chill, lounge escape, beach chillout, "
            "relaxing deep house, night lounge mix, tropical relaxation music, chill study vibes, calm ocean sounds, "
            "soulful chillout, sunset lounge, deep chill playlist, background tropical beats, late night chill, "
            "cozy beach vibes, meditation chillout, tropical evening lounge, study chill mix"
        )

        # Мови
        self.cbx_default_lang=QComboBox()
        self.cbx_default_lang.setFont(compact_font)
        for name,code in LANGS_TOP30: 
            self.cbx_default_lang.addItem(f"{_flag(code)} {name} ({code})",userData=code)
        for i,(_,code) in enumerate(LANGS_TOP30):
            if code=="en": self.cbx_default_lang.setCurrentIndex(i); break
            
        lang_panel=QW(); 
        lang_grid=QGridLayout(lang_panel); 
        self._lang_checks={}
        cols=3
        for i,(name,code) in enumerate(LANGS_TOP30):
            cb=QCheckBox(f"{_flag(code)} {name} ({code})")
            cb.setFont(compact_font)
            if code in ("en","uk","es","de","fr"): cb.setChecked(True)
            self._lang_checks[code]=cb; r,c=divmod(i,cols); lang_grid.addWidget(cb,r,c); cb.toggled.connect(self._update_lang_counter)
            
        self.lbl_lang_counter=QLabel("Вибрано 5 мов"); 
        self.lbl_lang_counter.setFont(compact_font)
        self._apply_lang_opacity()
        
        grid.addWidget(QLabel("Base prompt:"),0,0); 
        grid.addWidget(QLabel("Extra prompt:"),0,1); 
        grid.addWidget(QLabel("Ключові/seed:"),0,2); 
        grid.addWidget(QLabel("Мови / Default:"),0,3)
        grid.addWidget(self.txt_base,1,0); 
        grid.addWidget(self.txt_extra,1,1); 
        grid.addWidget(self.ed_seed_tags,1,2)
        
        rb=QVBoxLayout(); 
        rb.addWidget(QLabel("Default:")); 
        rb.addWidget(self.cbx_default_lang); 
        rb.addWidget(lang_panel); 
        rb.addWidget(self.lbl_lang_counter); 
        rb.addStretch()
        w=QW(); 
        w.setLayout(rb); 
        grid.addWidget(w,1,3)

        # Параметри
        row2=QHBoxLayout(); 
        root.addLayout(row2)
        row2.setSpacing(4)
        
        self.sp_tags=QSpinBox(); 
        self.sp_tags.setRange(0,30); 
        self.sp_tags.setValue(20)
        self.sp_tags.setFont(compact_font)
        self.sp_tags.setFixedHeight(22)
        
        self.sp_hash=QSpinBox(); 
        self.sp_hash.setRange(0,30); 
        self.sp_hash.setValue(6)
        self.sp_hash.setFont(compact_font)
        self.sp_hash.setFixedHeight(22)
        
        self.sp_desc=QSpinBox(); 
        self.sp_desc.setRange(300,5000); 
        self.sp_desc.setValue(1000)
        self.sp_desc.setFont(compact_font)
        self.sp_desc.setFixedHeight(22)
        
        self.chk_strip_years=QCheckBox("Прибрати роки (2024/2025) з title"); 
        self.chk_strip_years.setChecked(True)
        self.chk_strip_years.setFont(compact_font)
        
        row2.addWidget(QLabel("Tags:")); 
        row2.addWidget(self.sp_tags); 
        row2.addWidget(QLabel("Hashtags:")); 
        row2.addWidget(self.sp_hash)
        row2.addStretch(); 
        row2.addWidget(QLabel("Макс. опис:")); 
        row2.addWidget(self.sp_desc); 
        row2.addWidget(self.chk_strip_years)

        # Прогрес
        self.progress=QProgressBar(); 
        self.progress.setRange(0,100); 
        self.progress.setValue(0); 
        self.progress.setFixedHeight(16)
        root.addWidget(self.progress)

        # Верхня панель дій
        mid=QHBoxLayout(); 
        root.addLayout(mid)
        mid.setSpacing(4)
        
        mid.addWidget(self.btn_refresh); 
        mid.addWidget(self.btn_gpt); 
        mid.addWidget(self.btn_loc); 
        mid.addStretch()

        # ====== Плейлісти (мультивибір) ======
        self.lbl_pl_summary = QLabel("Плейлісти: (не вибрано)")
        self.lbl_pl_summary.setFont(compact_font)
        
        self.btn_pick_playlists = QPushButton("Обрати…"); 
        style_btn(self.btn_pick_playlists,"#475569","white","sm")
        
        self.btn_add_all_to_playlists = QPushButton("➕ Усі"); 
        style_btn(self.btn_add_all_to_playlists,"#22c55e","white","sm")
        
        self.lbl_pl_summary.setToolTip("Список обраних плейлістів для авто/масових дій")
        mid.addWidget(self.lbl_pl_summary); 
        mid.addWidget(self.btn_pick_playlists); 
        mid.addWidget(self.btn_add_all_to_playlists)

        # Таблиці
        self.tabs=QTabWidget(); 
        self.tabs.setFont(compact_font)
        root.addWidget(self.tabs,2)
        
        self.table_videos=self._create_table(); 
        self.table_shorts=self._create_table()
        self.tabs.addTab(self.table_videos,"Відео"); 
        self.tabs.addTab(self.table_shorts,"Shorts")

        # Нижня панель
        bottom=QHBoxLayout(); 
        root.addLayout(bottom)
        bottom.setSpacing(4)
        
        self.cmb_filter_fast=QComboBox(); 
        self.cmb_filter_fast.addItems(["Всі","Неопубліковані","Опубліковані"])
        self.cmb_filter_fast.setFont(compact_font)
        self.cmb_filter_fast.setFixedHeight(22)
        
        self.btn_select_all=QPushButton("Вибрати всі"); 
        self.btn_unselect_all=QPushButton("Зняти всі")
        style_btn(self.btn_select_all,"#475569","white","sm"); 
        style_btn(self.btn_unselect_all,"#475569","white","sm")
        
        self.selected_label=QLabel("Виділено: 0"); 
        self.selected_label.setFont(compact_font)
        
        self.planned_label=QLabel("Заплановано: 0")
        self.planned_label.setFont(compact_font)
        
        bottom.addWidget(self.btn_select_all); 
        bottom.addWidget(self.btn_unselect_all); 
        bottom.addStretch()
        bottom.addWidget(QLabel("Фільтр:")); 
        bottom.addWidget(self.cmb_filter_fast); 
        bottom.addWidget(self.selected_label); 
        bottom.addWidget(self.planned_label)

        # ====== JSON-менеджер ======
        json_row=QHBoxLayout(); 
        root.addLayout(json_row)
        json_row.setSpacing(4)
        
        json_row.addWidget(QLabel("JSON:"))
        self.cmb_json = QComboBox(); 
        self.cmb_json.setMinimumWidth(200);  # Зменшена ширина
        self.cmb_json.setFont(compact_font)
        self.cmb_json.setFixedHeight(22)
        json_row.addWidget(self.cmb_json)
        
        def cap(btn: QPushButton): 
            btn.setMaximumWidth(120)  # Зменшена максимальна ширина
            btn.setMinimumWidth(80)   # Зменшена мінімальна ширина
            
        self.btn_json_add = QPushButton("Додати JSON"); 
        self.btn_json_add_db = QPushButton("➕ Новий")
        self.btn_json_apply = QPushButton("Застосувати"); 
        self.btn_json_refresh = QPushButton("Оновити")
        self.btn_json_load_cache = QPushButton("Завантажити кеш"); 
        self.btn_json_delete = QPushButton("Видалити JSON")
        
        for btn,color in [(self.btn_json_add,"#8b5cf6"),(self.btn_json_add_db,"#7c3aed"),(self.btn_json_apply,"#0ea5e9"),
                          (self.btn_json_refresh,"#64748b"),(self.btn_json_load_cache,"#0ea5e9"),(self.btn_json_delete,"#ef4444")]:
            style_btn(btn,color,"white","sm"); 
            cap(btn); 
            json_row.addWidget(btn)

        # Сигнали
        self.btn_check_key.clicked.connect(self._check_key)
        self.btn_auth.clicked.connect(self._auth); 
        self.btn_revoke.clicked.connect(self._revoke)
        self.btn_refresh.clicked.connect(self._load_videos)
        self.btn_save_preset.clicked.connect(self._save_preset_to_db)
        self.btn_export_json.clicked.connect(self._export_json); 
        self.btn_import_json.clicked.connect(self._import_json)
        self.btn_analyze.clicked.connect(self._start_analyze)
        self.btn_gpt.clicked.connect(self._start_autofill); 
        self.btn_loc.clicked.connect(self._start_translate)
        self.btn_stop.clicked.connect(self._stop_worker)
        self.cmb_filter_fast.currentIndexChanged.connect(self._apply_fast_filter)
        self.btn_select_all.clicked.connect(lambda: self._bulk_select(True)); 
        self.btn_unselect_all.clicked.connect(lambda: self._bulk_select(False))
        self.tabs.currentChanged.connect(self._update_counts)
        self.btn_add_all_to_playlists.clicked.connect(self._add_all_visible_to_playlists)
        self.btn_pick_playlists.clicked.connect(self._open_playlist_picker)
        self.btn_json_refresh.clicked.connect(self._refresh_json_list)
        self.btn_json_load_cache.clicked.connect(self._load_selected_json)
        self.btn_json_delete.clicked.connect(self._delete_selected_json)
        self.btn_json_add.clicked.connect(self._add_json_to_list)
        self.btn_json_add_db.clicked.connect(self._add_json_to_db)
        self.btn_json_apply.clicked.connect(self._apply_selected_json)
        self.btn_load_client_secret.clicked.connect(self._install_client_secret)

        # таймер оновлення лічильників
        self._counter_timer=QTimer(self); 
        self._counter_timer.setInterval(800)
        self._counter_timer.timeout.connect(self._update_counts); 
        self._counter_timer.start()

        # JSON-список та збережені плейлісти
        self._refresh_json_list()
        self._load_saved_playlists_selection()

    # ---- HELP ----
    def _show_help(self):
        dlg=QDialog(self); dlg.setWindowTitle("Довідка / Help")
        dlg.resize(600, 400)  # Зменшений розмір
        lay=QVBoxLayout(dlg); tb=QTextBrowser(); tb.setOpenExternalLinks(True)
        tb.setHtml(f"""
        <h3>AutoFill v{VERSION} — коротка довідка</h3>
        <ul>
          <li><b>Плейлісти</b>: натисни <i>Обрати…</i> і постав галочки на кількох плейлістах. Вони використовуються для авто-додавання після оновлення та для кнопки «➕ Усі».</li>
          <li>Колонка «Плейлісти» показує обрані плейлісти; «У плейлістах» — галочка, якщо відео є у <i>всіх</i> обраних; підказка показує <code>x / y</code>.</li>
          <li><b>Аналіз каналу</b>: збирає Seed з топ-10 відео й (за потреби) заповнює «Тему». Все зберігається у пресеті.</li>
          <li>Інше: JSON-менеджер, переклади (оригінал title не змінюється), автозаповнення GPT, Shorts фолбек (≤60с).</li>
        </ul>""")
        lay.addWidget(tb); btns=QDialogButtonBox(QDialogButtonBox.Ok); btns.accepted.connect(dlg.accept); lay.addWidget(btns)
        dlg.exec()

    # ---- misc utils ----
    def _g(self,msg:str):
        ts=datetime.now().strftime("%H:%M:%S"); self.sig_log.emit(f"[{ts}] {msg}")

    def _centered_check_widget(self, checked:bool=False, enabled:bool=True) -> QW:
        wrap = QW(); lay = QHBoxLayout(wrap); lay.setContentsMargins(0,0,0,0); lay.setAlignment(Qt.AlignCenter)
        cb = QCheckBox(); cb.setChecked(checked); cb.setEnabled(enabled); lay.addWidget(cb); wrap._cb = cb
        return wrap

    def _apply_lang_opacity(self):
        try:
            for _, code in LANGS_TOP30:
                cb = self._lang_checks.get(code)
                if not cb: continue
                eff = cb.graphicsEffect()
                if not isinstance(eff, QGraphicsOpacityEffect):
                    eff = QGraphicsOpacityEffect(cb); cb.setGraphicsEffect(eff)
                eff.setOpacity(1.0 if cb.isChecked() else 0.45)
        except Exception: pass

    def _update_lang_counter(self):
        cnt=sum(1 for _,code in LANGS_TOP30 if self._lang_checks.get(code) and self._lang_checks[code].isChecked())
        self.lbl_lang_counter.setText(f"Вибрано {cnt} мов"); self._apply_lang_opacity()

    def _create_table(self)->QTableWidget:
        t=QTableWidget(); t.setColumnCount(13)
        t.setHorizontalHeaderLabels(["☑","✓","Прев’ю","Назва","Опис","Теги","К-ть ключових","К-ть мов","Тривалість","Перегляди","Плейлісти","У плейлістах","Статус"])
        t.setSelectionBehavior(QAbstractItemView.SelectRows); t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        
        # Компактні розміри колонок для 15-дюймового монітора
        header=t.horizontalHeader(); 
        header.setSectionResizeMode(self.COL_TITLE,QHeaderView.Stretch); 
        header.setSectionResizeMode(self.COL_DESC,QHeaderView.Stretch)
        
        t.setColumnWidth(self.COL_CHECK,30);     # Зменшено
        t.setColumnWidth(self.COL_DONE,20);      # Зменшено
        t.setColumnWidth(self.COL_THUMB,70);     # Зменшено
        t.setColumnWidth(self.COL_TAGS,150);     # Зменшено
        t.setColumnWidth(self.COL_KEYS,80);      # Зменшено
        t.setColumnWidth(self.COL_LANGS,80);     # Зменшено
        t.setColumnWidth(self.COL_DURATION,70);  # Зменшено
        t.setColumnWidth(self.COL_VIEWS,70);     # Зменшено
        t.setColumnWidth(self.COL_PL_NAMES,150); # Зменшено
        t.setColumnWidth(self.COL_PL_STATE,80);  # Зменшено
        t.setColumnWidth(self.COL_STATUS,120);   # Зменшено
        
        # Компактні рядки
        t.verticalHeader().setDefaultSectionSize(24)  # Зменшена висота рядків
        
        t._items=[]; 
        t.setMinimumHeight(8*24+30)  # Зменшена мінімальна висота
        t.setSortingEnabled(True); 
        
        # Компактний шрифт для таблиці
        font = QFont()
        font.setPointSize(8)
        t.setFont(font)
        
        return t

    # ---- auth & channel ----
    def _auth(self):
        try:
            yt,_,_=authorize_google_autofill(); self.youtube=yt
            self._g("Авторизація виконана"); self._load_channel_info(); self._load_videos(); self._load_preset_from_db(); self._refresh_playlists_ui()
        except Exception as e:
            QMessageBox.critical(self,APP_NAME,f"Помилка авторизації: {e}"); self._g(f"Помилка авторизації: {e}")

    def _revoke(self):
        try:
            if os.path.exists(TOKEN_FILE): os.remove(TOKEN_FILE); self._g("Токен AutoFill видалено")
        except Exception as e: self._g(f"Помилка видалення токена: {e}")
        self.youtube=None; self.channel_id=None; self.avatar_lbl.clear()
        self.channel_lbl.setText(f"Канал: (не авторизовано) · v{VERSION}"); self.stats_lbl.setText("—")
        self.table_videos.setRowCount(0); self.table_shorts.setRowCount(0); self._update_counts()
        self._playlists.clear(); self._selected_playlist_ids=[]; self._refresh_playlists_ui()

    def _check_key(self):
        key=(self.ed_key.text() or os.getenv("OPENAI_API_KEY","")).strip()
        if not key:
            self.lbl_key_status.setText("Ключ: порожній"); self._g("Перевірка ключа: ключ порожній"); return
        try:
            ping=_openai_chat(key,[{"role":"system","content":"ping"},{"role":"user","content":"Reply with OK"}],"gpt-4o-mini",0.0)
            if "OK" in ping.upper():
                QSettings(ORG,APP).setValue("openai_key",key)
                self.lbl_key_status.setText("Ключ: валідний"); self.lbl_key_status.setStyleSheet("color:#22c55e;")
                self._g("Ключ OpenAI валідний (збережено)")
            else:
                self.lbl_key_status.setText("Ключ: нетипова відповідь"); self.lbl_key_status.setStyleSheet("color:#f59e0b;"); self._g(f"Ключ OpenAI відповів нетипово: {ping!r}")
        except Exception as e:
            self.lbl_key_status.setText("Ключ: помилка"); self.lbl_key_status.setStyleSheet("color:#ef4444;"); self._g(f"Ключ OpenAI помилка: {e}")

    def _install_client_secret(self):
        path, _ = QFileDialog.getOpenFileName(self, "Вибрати client_secret.json", "", "JSON (*.json)")
        if not path: return
        try:
            dest = CLIENT_SECRET_FILE or os.path.join(os.getcwd(), "client_secret.json")
            shutil.copyfile(path, dest)
            try:
                if os.path.exists(TOKEN_FILE):
                    os.remove(TOKEN_FILE); self._g(f"Видалено старий токен: {TOKEN_FILE}")
            except Exception as te:
                self._g(f"Не вдалося видалити токен: {te}")
            self._g(f"Ключ встановлено: {dest}")
            QMessageBox.information(self, "YouTube ключ", "Новий ключ встановлено.\nНатисніть «Авторизуватись» для входу в Google.")
        except Exception as e:
            QMessageBox.critical(self, "YouTube ключ", f"Не вдалося встановити ключ: {e}")
            self._g(f"Помилка встановлення ключа: {e}")

    def _load_channel_info(self):
        if not self.youtube: return
        try:
            r=self.youtube.channels().list(part="id,snippet,statistics",mine=True).execute()
            items=r.get("items", [])
            if not items: return
            info=items[0]; self.channel_id=info.get("id")
            sn=info.get("snippet",{}) or {}
            self.channel_lbl.setText(f"Канал: {sn.get('title','')} · v{VERSION}")
            subs=_fmt_count(info.get("statistics",{}).get("subscriberCount",0))
            vids=_fmt_count(info.get("statistics",{}).get("videoCount",0))
            views=_fmt_count(info.get("statistics",{}).get("viewCount",0))
            self.stats_lbl.setText(f"Subs {subs} | Videos {vids} | Views {views}")
            thumb=(sn.get("thumbnails",{}) or {}).get("default",{}).get("url")
            if thumb:
                try:
                    raw=requests.get(thumb,timeout=8).content; pm=QPixmap(); pm.loadFromData(raw)
                    self.avatar_lbl.setPixmap(pm.scaled(48,48,Qt.KeepAspectRatio,Qt.SmoothTransformation))
                except Exception: pass
            self._load_playlists()
        except Exception as e: self._g(f"Помилка даних каналу: {e}")

    # ---- Playlists ----
    def _load_playlists(self):
        if not self.youtube: return
        try:
            self._playlists.clear()
            page=None
            while True:
                res=self.youtube.playlists().list(part="snippet", mine=True, maxResults=50, pageToken=page).execute()
                for item in res.get("items", []) or []:
                    title = (item.get("snippet", {}) or {}).get("title", "") or "(без назви)"
                    pid = item.get("id")
                    if pid: self._playlists[title]=pid
                page=res.get("nextPageToken")
                if not page: break
            self._g(f"Плейлісти оновлено: {len(self._playlists)}")
            self._refresh_playlists_ui()
            self._refresh_playlist_membership()
        except Exception as e:
            self._g(f"Помилка завантаження плейлістів: {e}")

    def _refresh_playlists_ui(self):
        titles=self._selected_playlist_titles()
        if titles:
            view=", ".join(titles[:2]) + (f" +{len(titles)-2}" if len(titles)>2 else "")
            self.lbl_pl_summary.setText(f"Плейлісти: {view}")
        else:
            self.lbl_pl_summary.setText("Плейлісти: (не вибрано)")

    def _open_playlist_picker(self):
        if not self._playlists:
            QMessageBox.information(self,APP_NAME,"Плейлісти не завантажені. Авторизуйтесь/оновіть."); return
        pairs=sorted([(t,p) for t,p in self._playlists.items()], key=lambda x:x[0].lower())
        dlg=PlaylistPickerDialog(self,pairs,self._selected_playlist_ids)
        if dlg.exec():
            self._selected_playlist_ids = dlg.result_ids()
            QSettings(ORG,APP).setValue("active_playlist_ids", json.dumps(self._selected_playlist_ids))
            self._refresh_playlists_ui(); self._refresh_playlist_membership()

    def _selected_playlist_titles(self)->list[str]:
        rev = {v:k for k,v in self._playlists.items()}
        return [rev.get(pid,"?") for pid in self._selected_playlist_ids if pid in rev]

    def _load_saved_playlists_selection(self):
        try:
            s = QSettings(ORG,APP).value("active_playlist_ids","[]",type=str) or "[]"
            self._selected_playlist_ids = [p for p in json.loads(s) if isinstance(p,str)]
            self._refresh_playlists_ui()
        except Exception:
            self._selected_playlist_ids=[]; self._refresh_playlists_ui()

    def _get_playlist_video_ids(self, pid:str) -> set[str]:
        ids=set()
        if not self.youtube or not pid: return ids
        try:
            page=None
            while True:
                res=self.youtube.playlistItems().list(part="contentDetails",playlistId=pid,maxResults=50,pageToken=page).execute()
                for it in (res.get("items") or []):
                    vid=(it.get("contentDetails") or {}).get("videoId")
                    if vid: ids.add(vid)
                page=res.get("nextPageToken")
                if not page: break
        except Exception as e:
            self._g(f"Помилка читання складу плейліста {pid}: {e}")
        return ids

    def _refresh_playlist_membership(self):
        """Оновити колонку «У плейлістах»: галочка = у всіх; підказка 'x / y'."""
        if not self._selected_playlist_ids:
            title_txt="—"
            for table in (self.table_videos,self.table_shorts):
                for row in range(table.rowCount()):
                    table.setItem(row,self.COL_PL_NAMES,_make_centered_item(title_txt))
                    w=table.cellWidget(row,self.COL_PL_STATE)
                    if isinstance(w,QW) and hasattr(w,"_cb"): w._cb.setChecked(False); w.setToolTip("0 / 0")
            return

        present_map = {pid: self._get_playlist_video_ids(pid) for pid in self._selected_playlist_ids}
        titles=self._selected_playlist_titles()
        title_txt=", ".join(titles[:2]) + (f" +{len(titles)-2}" if len(titles)>2 else "")
        for table in (self.table_videos,self.table_shorts):
            for row in range(table.rowCount()):
                table.setItem(row,self.COL_PL_NAMES,_make_centered_item(title_txt))
                vid=table.item(row,self.COL_TITLE).data(Qt.UserRole)
                count=sum(1 for pid in self._selected_playlist_ids if vid in present_map.get(pid,set()))
                w=table.cellWidget(row,self.COL_PL_STATE)
                if isinstance(w,QW) and hasattr(w,"_cb"):
                    w._cb.setChecked(count==len(self._selected_playlist_ids))
                    w._cb.setEnabled(False)
                    w.setToolTip(f"{count} / {len(self._selected_playlist_ids)}")

    # ---- videos ----
    @staticmethod
    def _is_published(v:dict)->bool:
        try: return is_pub(v)
        except Exception: return False

    def _augment_shorts_via_search(self, existing_ids:set[str]) -> list:
        if not self.youtube or not self.channel_id: return []
        out=[]
        try:
            page_token=None; collected_ids=[]
            for _ in range(3):
                res=self.youtube.search().list(part="id", channelId=self.channel_id, type="video",
                    maxResults=50, order="date", videoDuration="short", pageToken=page_token).execute()
                vids=[(it.get("id") or {}).get("videoId") for it in (res.get("items") or [])]
                vids=[v for v in vids if v and v not in existing_ids]
                collected_ids.extend(vids); page_token=res.get("nextPageToken")
                if not page_token: break
            chunks=[collected_ids[i:i+50] for i in range(0,len(collected_ids),50)]
            for ch in chunks:
                if not ch: continue
                det=self.youtube.videos().list(part="snippet,contentDetails,statistics,status", id=",".join(ch)).execute()
                for it in (det.get("items") or []):
                    cd=it.get("contentDetails",{}) or {}; dur=cd.get("duration") or ""; secs=self._parse_dur_secs(dur)
                    if secs<=60:
                        sn=it.get("snippet",{}) or {}; st=it.get("status",{}) or {}; stats=it.get("statistics",{}) or {}
                        out.append({"id":it.get("id"), "videoId":it.get("id"), "title":sn.get("title",""),
                                    "description":sn.get("description",""), "tags":sn.get("tags") or [],
                                    "duration":dur, "viewCount":stats.get("viewCount",0),
                                    "privacyStatus":st.get("privacyStatus",""),
                                    "publishAt":(st.get("publishAt") or (st.get("publishTime") if "publishTime" in st else sn.get("publishedAt")))})
        except Exception as e:
            self._g(f"Shorts фолбек помилка: {e}")
        return out

    def _load_videos(self):
        if not self.youtube:
            QMessageBox.warning(self,APP_NAME,"Спочатку авторизуйтесь"); return
        try:
            data=get_videos_split(self.youtube,max_results=500,unpublished_only=False)
            videos_all=data.get("videos",[]); shorts_all=data.get("shorts",[])
            existing_ids={ (v.get("id") or v.get("videoId")) for v in shorts_all }
            extra_shorts=self._augment_shorts_via_search(existing_ids)
            by_id={ (v.get("id") or v.get("videoId")): v for v in shorts_all }
            for it in extra_shorts:
                vid=it.get("id") or it.get("videoId")
                if vid and vid not in by_id: by_id[vid]=it
            shorts_all=list(by_id.values())
            self._all_items_cache=videos_all+shorts_all
            self._populate_table(self.table_videos,videos_all); self._populate_table(self.table_shorts,shorts_all)
            self._apply_fast_filter(); self._refresh_playlist_membership()
            self._g(f"Списки оновлено: videos={len(videos_all)}, shorts={len(shorts_all)} (фолбек +{len(extra_shorts)})")
        except Exception as e:
            QMessageBox.critical(self,APP_NAME,f"Не вдалося отримати список відео: {e}"); self._g(f"Помилка списку: {e}")

    def _populate_table(self,table:QTableWidget,items):
        table.setSortingEnabled(False); table.setRowCount(0); table._items=list(items) if items else []
        table.setRowCount(len(table._items))
        for row,v in enumerate(table._items):
            wrap_cb = self._centered_check_widget(False, True); wrap_cb._cb.stateChanged.connect(self._update_counts)
            table.setCellWidget(row,self.COL_CHECK,wrap_cb)
            table.setItem(row,self.COL_DONE,_make_centered_item("")); table.setItem(row,self.COL_THUMB,_make_centered_item(""))
            ti=QTableWidgetItem((v.get("title") or "").strip()); ti.setData(Qt.UserRole,v.get("id") or v.get("videoId")); ti.setFlags(ti.flags() & ~Qt.ItemIsEditable)
            table.setItem(row,self.COL_TITLE,ti)
            table.setItem(row,self.COL_DESC,QTableWidgetItem((v.get("description") or "").strip()))
            table.setItem(row,self.COL_TAGS,QTableWidgetItem(", ".join(v.get("tags") or [])))
            keys_len=len(v.get("keywords") or []); loc_len=len(v.get("translations") or v.get("localizations") or {})
            table.setItem(row,self.COL_KEYS,_make_centered_item(str(keys_len),sort_key=keys_len))
            table.setItem(row,self.COL_LANGS,_make_centered_item(str(loc_len),sort_key=loc_len))
            dur_txt=parse_duration(v.get("duration")); secs=self._parse_dur_secs(v.get("duration"))
            table.setItem(row,self.COL_DURATION,_make_centered_item(dur_txt or "—",sort_key=secs))
            views=int(v.get("viewCount") or v.get("views") or 0)
            table.setItem(row,self.COL_VIEWS,_make_centered_item(_fmt_count(views),sort_key=views))
            # плейлісти
            table.setItem(row,self.COL_PL_NAMES,_make_centered_item("—"))
            table.setCellWidget(row,self.COL_PL_STATE,self._centered_check_widget(False, False))
            # статус
            table.setItem(row,self.COL_STATUS,_make_centered_item(self._fmt_status(v),sort_key=_status_sort_key(v)))
        table.setSortingEnabled(True)

    def _parse_dur_secs(self, iso:str)->int:
        try:
            if not iso: return 0
            h=m=s=0
            for n,u in re.findall(r"(\d+)([HMS])",iso):
                if u=="H": h=int(n)
                if u=="M": m=int(n)
                if u=="S": s=int(n)
            return h*3600+m*60+s
        except Exception: return 0

    def _fmt_status(self,v:dict)->str:
        try: return compute_status_ext(v)
        except Exception:
            ts=v.get("publishAt") or v.get("scheduledPublishTime") or v.get("scheduled") or (v.get("status") or {}).get("publishAt")
            if ts:
                try:
                    if isinstance(ts,(int,float)): dt=datetime.fromtimestamp(ts,tz=timezone.utc)
                    else: dt=datetime.fromisoformat(str(ts).replace("Z","+00:00"))
                    if dt>datetime.now(tz=timezone.utc): return dt.strftime("%Y-%m-%d %H:%M")
                except Exception: pass
            return (v.get("privacyStatus") or v.get("privacy") or "—").capitalize()

    # ---- filters & selects ----
    def _apply_fast_filter(self):
        mode=self.cmb_filter_fast.currentText()
        for t in (self.table_videos,self.table_shorts): apply_filter_rows(t, mode)
        self._update_counts()
    def _bulk_select(self,state:bool):
        table=self._current_table()
        for row in range(table.rowCount()):
            if table.isRowHidden(row): continue
            w=table.cellWidget(row,self.COL_CHECK)
            if isinstance(w,QW) and hasattr(w,"_cb"): w._cb.setChecked(state)
        self._update_counts()
    def _current_table(self): return self.table_videos if self.tabs.currentIndex()==0 else self.table_shorts
    def _update_counts(self):
        table=self._current_table(); selected=planned=0
        for row in range(table.rowCount()):
            if table.isRowHidden(row): continue
            w=table.cellWidget(row,self.COL_CHECK)
            if isinstance(w,QW) and hasattr(w,"_cb") and w._cb.isChecked(): selected+=1
            st_item=table.item(row,self.COL_STATUS); st=st_item.text() if st_item else ""
            if st and st not in ("Public","—"): planned+=1
        self.selected_label.setText(f"Виділено: {selected}"); self.planned_label.setText(f"Заплановано: {planned}")

    # ---- масове додавання у вибрані плейлісти ----
    def _add_all_visible_to_playlists(self):
        if not self.youtube:
            QMessageBox.warning(self,APP_NAME,"Авторизуйтесь спершу"); return
        if not self._selected_playlist_ids:
            QMessageBox.information(self,APP_NAME,"Спочатку оберіть плейлісти (кнопка «Обрати…»)"); return
        table=self._current_table()
        count=0
        for row in range(table.rowCount()):
            if table.isRowHidden(row): continue
            vid=table.item(row,self.COL_TITLE).data(Qt.UserRole)
            if not vid: continue
            for pid in self._selected_playlist_ids:
                try:
                    self.youtube.playlistItems().insert(part="snippet",
                        body={"snippet":{"playlistId":pid,"resourceId":{"kind":"youtube#video","videoId":vid}}}).execute()
                    count+=1
                except Exception as e:
                    self._g(f"Помилка додавання {vid} у {pid}: {e}")
        self._refresh_playlist_membership()
        QMessageBox.information(self,APP_NAME,f"Додано у плейлісти: {count} записів")

    # ---- запуск воркерів ----
    def _rows_selected_or_all(self):
        rows=list(self._iter_selected_rows())
        if rows: return rows
        table=self._current_table(); items=getattr(table,"_items",[])
        out=[]
        for row in range(table.rowCount()):
            if table.isRowHidden(row): continue
            vid=table.item(row,self.COL_TITLE).data(Qt.UserRole)
            out.append((row,vid,items[row] if row < len(items) else {}))
        return out
    def _disable_ui(self,on:bool):
        for w in (self.btn_help,self.btn_auth,self.btn_revoke,self.btn_refresh,self.btn_gpt,self.btn_loc,self.btn_select_all,self.btn_unselect_all,self.btn_save_preset,self.btn_export_json,self.btn_import_json,self.btn_analyze,self.btn_json_refresh,self.btn_json_load_cache,self.btn_json_delete,self.btn_json_add,self.btn_json_add_db,self.btn_json_apply,self.btn_add_all_to_playlists,self.btn_load_client_secret,self.btn_pick_playlists):
            w.setEnabled(not on)
        self.btn_stop.setVisible(on)
    def _stop_worker(self):
        if self._running_worker is not None:
            self._running_worker.request_stop(); self.btn_stop.setEnabled(False)

    def _start_translate(self):
        if not self.youtube: QMessageBox.warning(self,"YouTube","Спочатку авторизуйтесь."); return
        if not self.channel_id: QMessageBox.warning(self,"YouTube","Немає channelId."); return
        key=(self.ed_key.text() or QSettings(ORG,APP).value("openai_key","",type=str) or "").strip()
        if not key: QMessageBox.critical(self,"GPT","Введіть / збережіть OpenAI API Key."); return
        targets=[(name,code) for (name,code) in LANGS_TOP30 if self._lang_checks.get(code) and self._lang_checks[code].isChecked()]
        if not targets: QMessageBox.warning(self,"Локалізації","Оберіть мови."); return
        rows=self._rows_selected_or_all()
        if not rows: QMessageBox.information(self,"Локалізації","Немає відео у таблиці."); return
        primary=self._selected_lang_code()
        targets=[(n,c) for (n,c) in targets if c != primary]
        pids=list(self._selected_playlist_ids)
        self._g(f"Переклад: primary={primary}; targets={', '.join([f'{n}({c})' for n,c in targets])}; playlists={len(pids)}")
        self._disable_ui(True); self.progress.setValue(0)
        wrk=TranslateWorker(self.youtube,key,rows,targets,primary,self.channel_id,self.db,pids,self)
        wrk.sig_log.connect(self._g); wrk.sig_progress.connect(self.progress.setValue)
        wrk.sig_update_table.connect(self._apply_table_update)
        wrk.sig_video_done.connect(lambda row,mode:self._mark_done(row,mode))
        wrk.sig_error.connect(lambda e:(self._g(e),QMessageBox.critical(self,"Переклад",e)))
        wrk.sig_finished.connect(lambda n:(self._disable_ui(False), self._refresh_playlist_membership(), QMessageBox.information(self,"Локалізації",f"Готово! Оновлено: {n}.")))
        self._running_worker=wrk; wrk.start()

    def _start_autofill(self):
        if not self.youtube: QMessageBox.warning(self,APP_NAME,"Спочатку авторизуйтесь."); return
        if not self.channel_id: QMessageBox.warning(self,APP_NAME,"Немає channelId."); return
        key=(self.ed_key.text() or QSettings(ORG,APP).value("openai_key","",type=str) or "").strip()
        if not key: QMessageBox.critical(self,"GPT","Введіть / збережіть OpenAI API Key."); return
        rows=self._rows_selected_or_all()
        if not rows: QMessageBox.information(self,"GPT","Немає відео у таблиці."); return
        seed=[s.strip() for s in self.ed_seed_tags.toPlainText().replace("\n",",").split(",") if s.strip()]
        pids=list(self._selected_playlist_ids)
        self._disable_ui(True); self.progress.setValue(0)
        self._g(f"— Автозаповнення; плейлісти: {len(pids)} —")
        wrk=AutofillWorker(self.youtube,key,rows,self.txt_base.toPlainText(),self.txt_extra.toPlainText(),self.ed_theme.text(),
                           self.chk_strip_years.isChecked(),self.sp_tags.value(),self.sp_hash.value(),self.sp_desc.value(),
                           seed,self.channel_id,self.db,False,pids,self)
        wrk.sig_log.connect(self._g); wrk.sig_progress.connect(self.progress.setValue)
        wrk.sig_update_table.connect(self._apply_table_update)
        wrk.sig_video_done.connect(lambda row,mode:self._mark_done(row,mode))
        wrk.sig_error.connect(lambda e:(self._g(e),QMessageBox.critical(self,"Автозаповнення",e)))
        wrk.sig_finished.connect(lambda n:(self._disable_ui(False), self._refresh_playlist_membership(), QMessageBox.information(self,"Автозаповнення",f"Готово! Оновлено: {n}.\n(Дані також у JSON-кеші)")))
        self._running_worker=wrk; wrk.start()

    def _start_analyze(self):
        all_items=list(self._all_items_cache) if self._all_items_cache else (self.table_videos._items + self.table_shorts._items)
        if not all_items: QMessageBox.information(self,APP_NAME,"Немає відео для аналізу."); return
        try:
            top10=sorted(all_items,key=lambda x:int(x.get("viewCount") or x.get("views") or 0),reverse=True)[:10]
        except Exception:
            top10=(all_items)[:10]
        self._disable_ui(True); self.progress.setValue(15)
        base_tpl=self.txt_base.toPlainText(); extra_tpl=self.txt_extra.toPlainText(); seed_tpl=self.ed_seed_tags.toPlainText()
        wrk=AnalyzeWorker(top10, base_tpl, extra_tpl, seed_tpl, self)
        wrk.sig_log.connect(self._g)
        def _apply(base,extra,seed,theme):
            if base: self.txt_base.setPlainText(base)
            if extra: self.txt_extra.setPlainText(extra)
            if seed: self.ed_seed_tags.setPlainText(seed)
            if theme and not (self.ed_theme.text() or "").strip(): self.ed_theme.setText(theme)
            self.progress.setValue(100); self._disable_ui(False); self._save_preset_to_db()
            QMessageBox.information(self, "Аналіз каналу", "Готово.\nSeed оновлено з топ-10 відео.")
        wrk.sig_done.connect(_apply)
        wrk.sig_error.connect(lambda e:(self._g(e),self._disable_ui(False),QMessageBox.critical(self,"Аналіз",e)))
        wrk.start()

    # ---- preset save/load ----
    def _save_preset_to_db(self):
        """Зберегти налаштування каналу (промти/мови/ліміти/дефолтну мову) у SQLite + вибрані плейлісти в QSettings."""
        if not self.channel_id:
            QMessageBox.information(self, APP_NAME, "Немає channelId.")
            return
        selected_langs = {code for _, code in LANGS_TOP30 if self._lang_checks.get(code) and self._lang_checks[code].isChecked()}
        self.db.save_langs(self.channel_id, selected_langs)
        self.db.save_preset(self.channel_id, {
            "base_prompt": self.txt_base.toPlainText(),
            "extra_prompt": self.txt_extra.toPlainText(),
            "seed": self.ed_seed_tags.toPlainText(),
            "theme": self.ed_theme.text(),
            "tags_count": self.sp_tags.value(),
            "hash_count": self.sp_hash.value(),
            "desc_limit": self.sp_desc.value(),
            "strip_years": self.chk_strip_years.isChecked(),
            "default_lang": self._selected_lang_code(),
        })
        try:
            QSettings(ORG, APP).setValue("active_playlist_ids", json.dumps(list(self._selected_playlist_ids or [])))
        except Exception:
            QSettings(ORG, APP).setValue("active_playlist_ids", "[]")
        self._g("Пресет збережено до бази")

    def _load_preset_from_db(self):
        """Підтягнути пресет з бази і застосувати до UI."""
        if not self.channel_id:
            return
        p = self.db.load_preset(self.channel_id)
        if p:
            self.txt_base.setPlainText(p.get("base_prompt", "") or "")
            self.txt_extra.setPlainText(p.get("extra_prompt", "") or "")
            self.ed_seed_tags.setPlainText(p.get("seed", "") or "")
            self.ed_theme.setText(p.get("theme", "") or "")
            try: self.sp_tags.setValue(int(p.get("tags_count", 20) or 20))
            except Exception: pass
            try: self.sp_hash.setValue(int(p.get("hash_count", 6) or 6))
            except Exception: pass
            try: self.sp_desc.setValue(int(p.get("desc_limit", 1000) or 1000))
            except Exception: pass
            self.chk_strip_years.setChecked(bool(p.get("strip_years", True)))
            def_lang = p.get("default_lang", "en")
            for i in range(self.cbx_default_lang.count()):
                if self.cbx_default_lang.itemData(i) == def_lang:
                    self.cbx_default_lang.setCurrentIndex(i)
                    break
            selected = self.db.load_langs(self.channel_id)
            for _, code in LANGS_TOP30:
                if self._lang_checks.get(code):
                    self._lang_checks[code].setChecked(code in selected)
            self._update_lang_counter()
            self._g("Пресет підвантажено з бази")
        else:
            self._g("Пресета для каналу ще немає")

        self._load_saved_playlists_selection()
        self._refresh_playlists_ui()
        self._refresh_playlist_membership()

    # ---- table ops ----
    def _apply_table_update(self,row:int,title:str,desc:str,tags:list):
        table=self._current_table()
        if 0<=row<table.rowCount():
            table.item(row,self.COL_TITLE).setText((title or "")[:200])
            table.item(row,self.COL_DESC).setText((desc or "")[:5000])
            table.item(row,self.COL_TAGS).setText(", ".join(tags or []))
    def _mark_done(self,row:int,mode:str):
        table=self._current_table(); item=_make_centered_item("✔"); table.setItem(row,self.COL_DONE,item)
        ti=table.item(row,self.COL_TITLE)
        if ti and ti.text() and not ti.text().startswith("✔ "): ti.setText("✔ "+ti.text())
        self._update_counts()
    def _iter_selected_rows(self):
        table=self._current_table(); items=getattr(table,"_items",[])
        for row in range(table.rowCount()):
            if table.isRowHidden(row): continue
            w=table.cellWidget(row,self.COL_CHECK)
            if isinstance(w,QW) and hasattr(w,"_cb") and w._cb.isChecked():
                vid=table.item(row,self.COL_TITLE).data(Qt.UserRole)
                yield row,vid,items[row] if row<len(items) else {}

    def _selected_lang_code(self)->str:
        data=self.cbx_default_lang.currentData()
        if isinstance(data,str) and data: return data
        txt=(self.cbx_default_lang.currentText() or "").lower()
        for _,code in LANGS_TOP30:
            if f"({code})" in txt: return code
        return "en"

    # ---- JSON I/O ----
    def _export_json(self):
        if not self.channel_id: QMessageBox.information(self,APP_NAME,"Немає channelId"); return
        rows=list(self._iter_selected_rows()); ids=[vid for _,vid,_ in rows] if rows else None
        data={"channelId":self.channel_id,"generated":self.db.get_generated_for_videos(self.channel_id,ids)}
        if not data["generated"]: QMessageBox.information(self,APP_NAME,"Немає згенерованих даних у кеші."); return
        default=f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        path,_=QFileDialog.getSaveFileName(self,"Експорт JSON",os.path.join(JSON_DIR,default),"JSON (*.json)")
        if not path: path=os.path.join(JSON_DIR,default)
        with open(path,"w",encoding="utf-8") as f: json.dump(data,f,ensure_ascii=False,indent=2)
        self._g(f"JSON збережено: {path} ({len(data['generated'])} записів)")
        self._refresh_json_list()

    def _import_json(self):
        if not self.youtube: QMessageBox.warning(self,APP_NAME,"Спочатку авторизуйтесь"); return
        selected_path=self.cmb_json.currentData() if self.cmb_json.count()>0 else None
        if selected_path and os.path.isfile(selected_path): path=selected_path
        else:
            path,_=QFileDialog.getOpenFileName(self,"Імпорт JSON → YouTube",JSON_DIR,"JSON (*.json)")
            if not path: return
        try:
            with open(path,"r",encoding="utf-8") as f: data=json.load(f)
            items=data.get("generated") or []; cnt=0
            for it in items:
                vid=it.get("videoId"); title=it.get("title") or ""; desc=it.get("description") or ""; tags=it.get("tags") or []
                try:
                    self.youtube.videos().update(part="snippet",body={"id":vid,"snippet":{"title":title,"description":desc,"tags":trim_tags_for_youtube(tags)}}).execute()
                    self._g(f"Імпорт → оновлено snippet: {vid}"); cnt+=1
                except Exception as e: self._g(f"Імпорт → помилка для {vid}: {e}")
            QMessageBox.information(self,APP_NAME,f"Імпорт завершено. Оновлено: {cnt}")
        except Exception as e:
            QMessageBox.critical(self,APP_NAME,f"Помилка імпорту JSON: {e}"); self._g(f"Помилка імпорту JSON: {e}")

    def _refresh_json_list(self):
        self.cmb_json.clear()
        files=sorted(glob.glob(os.path.join(JSON_DIR,"*.json")), key=lambda p: os.path.getmtime(p), reverse=True)
        if not files:
            self.cmb_json.addItem("— (нема JSON у ./json) —", userData=None); return
        for p in files:
            name=os.path.basename(p); ts=datetime.fromtimestamp(os.path.getmtime(p)).strftime("%Y-%m-%d %H:%M")
            self.cmb_json.addItem(f"{name}  ·  {ts}", userData=p)

    def _load_json_into_cache(self, path:str) -> int:
        with open(path,"r",encoding="utf-8") as f: data=json.load(f)
        items=data.get("generated") or []; cnt=0
        ch_id = data.get("channelId") or (self.channel_id or "")
        for it in items:
            vid=it.get("videoId"); title=it.get("title") or ""; desc=it.get("description") or ""; tags=it.get("tags") or []; kw=it.get("keywords") or ""; mode=it.get("mode") or "autofill"
            self.db.upsert_generated(ch_id, vid, mode, title, desc, tags, kw); cnt+=1
        return cnt

    def _load_selected_json(self):
        path=self.cmb_json.currentData()
        if not path or not os.path.isfile(path):
            QMessageBox.information(self,APP_NAME,"Оберіть JSON у списку."); return
        try:
            cnt=self._load_json_into_cache(path); self._g(f"JSON кеш оновлено з: {os.path.basename(path)}; записів: {cnt}")
            QMessageBox.information(self,APP_NAME,f"Кеш оновлено з JSON. Записів: {cnt}")
        except Exception as e:
            QMessageBox.critical(self,APP_NAME,f"Помилка читання JSON: {e}")

    def _delete_selected_json(self):
        path=self.cmb_json.currentData()
        if not path or not os.path.isfile(path):
            QMessageBox.information(self,APP_NAME,"Оберіть JSON у списку."); return
        try:
            os.remove(path); self._g(f"JSON видалено: {path}"); self._refresh_json_list()
        except Exception as e:
            QMessageBox.critical(self,APP_NAME,f"Не вдалося видалити: {e}")

    def _add_json_to_list(self):
        path, _ = QFileDialog.getOpenFileName(self, "Додати JSON у список", "", "JSON (*.json)")
        if not path: return
        try:
            base = os.path.basename(path); dest = os.path.join(JSON_DIR, base)
            if os.path.abspath(path) == os.path.abspath(dest): self._refresh_json_list(); return
            if os.path.exists(dest):
                stamp = datetime.now().strftime("%Y%m%d_%H%M%S"); name, ext = os.path.splitext(base)
                dest = os.path.join(JSON_DIR, f"{name}_{stamp}{ext}")
            shutil.copyfile(path, dest); self._g(f"JSON додано у список: {dest}")
            self._refresh_json_list()
            for i in range(self.cmb_json.count()):
                if self.cmb_json.itemData(i) == dest: self.cmb_json.setCurrentIndex(i); break
            QMessageBox.information(self, APP_NAME, "JSON додано у список.\nТепер можна «Завантажити у кеш» або «Імпорт → YouTube».")
        except Exception as e:
            QMessageBox.critical(self, APP_NAME, f"Не вдалося додати JSON: {e}")

    def _add_json_to_db(self):
        path, _ = QFileDialog.getOpenFileName(self, "Обрати JSON (у базу)", "", "JSON (*.json)")
        if not path: return
        try:
            cnt=self._load_json_into_cache(path); self._g(f"JSON додано у БАЗУ: {os.path.basename(path)}; записів: {cnt}")
            QMessageBox.information(self, APP_NAME, f"Новий джонсон додано у БАЗУ (SQLite).\nЗаписів: {cnt}")
        except Exception as e:
            QMessageBox.critical(self, APP_NAME, f"Не вдалося додати у базу: {e}")

    def _apply_selected_json(self):
        path = self.cmb_json.currentData()
        if not path or not os.path.isfile(path):
            QMessageBox.information(self, APP_NAME, "Оберіть JSON у списку."); return
        try:
            cnt=self._load_json_into_cache(path)
            QSettings(ORG,APP).setValue("active_json", path)
            self._g(f"Активний JSON: {path} (оновлено у кеш: {cnt})")
            QMessageBox.information(self, APP_NAME, f"Активний JSON встановлено:\n{os.path.basename(path)}\n(оновлено у кеш: {cnt})")
        except Exception as e:
            QMessageBox.critical(self, APP_NAME, f"Помилка застосування JSON: {e}")