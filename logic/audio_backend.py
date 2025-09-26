# -*- coding: utf-8 -*-
"""
logic/audio_backend.py — KIE/Suno backend for ui/pages/audio_page.py

Залежності:
  pip install requests mutagen

Можливості:
- run_suno_pipeline(...): створює задачу в KIE, чекає (тик кожні 5с до 500с),
  показує охайні логи (без секундних тиков), тягне 2 аудіо на один POST,
  додає префікс MM.SS, зберігає .txt для лірики (у режимі «Лірика»/«GPT»).
- build_albums_pipeline(...): формує альбоми з чистими логами.
- kie_fetch_models(...): тягне доступні моделі (кілька можливих ендпоїнтів).

Стиль/лірику в логах маскуємо.
"""

from __future__ import annotations

import os
import re
import json
import time
import shutil
import random
import contextlib
import wave
from typing import Any, Dict, List, Optional, Callable, Iterable

# ========== queue / progress / pretty logs ==========

def _qput(q, payload: Dict[str, Any]) -> None:
    try:
        if q is not None:
            q.put(payload)
    except Exception:
        pass

def _log(q, msg: str) -> None:
    _qput(q, {"type": "log", "msg": msg})

def _progress(q, val: int, label: str = "") -> None:
    _qput(q, {"type": "progress", "value": max(0, min(100, int(val))), "label": label})

def _cancelled(ev) -> bool:
    try:
        return bool(ev and getattr(ev, "is_set", lambda: False)())
    except Exception:
        return False

def _bar(pct: float, width: int = 16, filled: str = "█", empty: str = "░") -> str:
    p = max(0.0, min(100.0, float(pct)))
    k = int(round(width * p / 100.0))
    return filled * k + empty * (width - k)

# ========== filenames / text utils ==========

SAFE_RE = re.compile(r'[^0-9A-Za-zА-Яа-яҐґЄєІіЇї _\-\.\(\)\[\]]+', re.UNICODE)

def sanitize_filename(name: str) -> str:
    name = (name or "").strip().replace("/", "-").replace("\\", "-")
    name = SAFE_RE.sub("", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name or "untitled"

def unique_path(path: str) -> str:
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    n = 2
    while True:
        cand = f"{base} ({n}){ext}"
        if not os.path.exists(cand):
            return cand
        n += 1

def _tokens_from_style(style: str) -> List[str]:
    toks = re.findall(r"[A-Za-zА-Яа-яІіЇїЄєҐґ']+", style or "", re.UNICODE)
    return [t for t in toks if len(t) >= 3]

def _unique_names(names: List[str]) -> List[str]:
    seen: Dict[str, int] = {}
    out: List[str] = []
    for n in names:
        key = (n or "").casefold()
        if key not in seen:
            seen[key] = 1; out.append(n)
        else:
            seen[key] += 1; out.append(f"{n} ({seen[key]})")
    return out

def _gen_titles_from_style(style: str, kind: str, n: int) -> List[str]:
    toks = _tokens_from_style(style)
    base = " ".join(toks[:3]).title() if toks else ("Music" if kind == "album" else "Track")
    res: List[str] = []
    for i in range(1, n + 1):
        res.append(f"{base} Album {i}" if kind == "album" else f"{base} {i:02d}")
    return _unique_names(res)

# ========== audio duration ==========

def try_get_duration_seconds(path: str) -> Optional[float]:
    try:
        from mutagen import File as MF  # type: ignore
        mf = MF(path)
        if mf and getattr(mf, "info", None) and getattr(mf.info, "length", None):
            return float(mf.info.length)
    except Exception:
        pass
    try:
        if path.lower().endswith(".wav"):
            with contextlib.closing(wave.open(path, "rb")) as wf:
                frames = wf.getnframes(); rate = wf.getframerate()
                return frames/float(rate) if rate>0 else None
    except Exception:
        pass
    return None

def fmt_mmss_dot(secs: float) -> str:
    s = int(max(0, round(secs)))
    return f"{s//60:02d}.{s%60:02d}"

# ========== local audio scan ==========

DEFAULT_EXTS = (".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac")

def collect_audio_files(folder: str, exts: Iterable[str] = DEFAULT_EXTS) -> List[str]:
    out: List[str] = []
    try:
        for root, _, files in os.walk(folder):
            for n in files:
                if n.lower().endswith(tuple(exts)):
                    out.append(os.path.join(root, n))
    except Exception:
        pass
    out.sort()
    return out

# ========== HTTP ==========

class _NoRequests(Exception): ...
def _require_requests():
    try:
        import requests  # noqa
        return requests
    except Exception as e:
        raise _NoRequests("Встанови пакет 'requests' (pip install requests)") from e

# ========== KIE endpoints/help ==========

KIE_GEN_URL = "https://api.kie.ai/api/v1/generate"
KIE_INFO_URLS = [
    "https://api.kie.ai/api/v1/generate/record-info",
    "https://api.kie.ai/api/v1/generate/recordInfo",
    "https://api.kie.ai/api/v1/generate/info",
    "https://api.kie.ai/api/v1/task/info",
]

WAIT_MAX_SEC   = int(os.environ.get("KIE_WAIT_MAX_SEC", 500))
POLL_STEP_SEC  = int(os.environ.get("KIE_POLL_STEP_SEC", 5))
POLL_ERR_EVERY = int(os.environ.get("KIE_POLL_ERR_EVERY", 60))

LOG_WAIT_TICKS = os.environ.get("KIE_WAIT_TICKS_TO_LOG", "0") != "0"

AUTO_VOCAL_NUDGE = os.environ.get("KIE_AUTO_PROMPT", "Pop vocal")
DEFAULT_KIE_CALLBACK = os.environ.get("KIE_CALLBACK_URL", "https://postman-echo.com/post")

def _mask_payload_for_log(payload: Dict[str, Any]) -> Dict[str, Any]:
    masked = dict(payload)
    if masked.get("prompt"): masked["prompt"] = "«...masked...»"
    if masked.get("style"):  masked["style"]  = "«...masked...»"
    return masked

# ======== MODELS: fetch + sorting ========

def _model_sort_key(name: str) -> tuple[int, int, int, str]:
    """Порівнювач моделей: V5 > V4_5PLUS > V4_5 > V4."""
    s = (name or "").upper()
    m = re.search(r'V?(\d+)(?:[._-]?(\d+))?', s)
    major = int(m.group(1)) if m and m.group(1) else 0
    minor = int(m.group(2)) if m and m.group(2) else 0
    suffix_score = 0
    if "TURBO" in s: suffix_score = 3
    elif "PLUS" in s: suffix_score = 2
    elif "PRO" in s: suffix_score = 1
    return (major, minor, suffix_score, s)

def kie_fetch_models(api_key: str) -> List[str]:
    """
    Тягне перелік моделей від KIE/Suno.
    Повертає список рядків; у разі помилки — [].
    """
    requests = _require_requests()
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "User-Agent": "suno-qt/1.0",
    }
    candidates = [
        "https://api.kie.ai/api/v1/models",
        "https://api.kie.ai/api/v1/generate/models",
        "https://api.kie.ai/api/v1/generate/modelList",
        "https://api.kie.ai/api/v1/model/list",
    ]
    for url in candidates:
        try:
            r = requests.get(url, headers=headers, timeout=20)
            if r.status_code >= 400:
                continue
            js = r.json() or {}
            models: List[str] = []
            if isinstance(js, dict):
                for key in ("models", "data", "result", "list", "modelList"):
                    v = js.get(key)
                    if isinstance(v, list):
                        models = [str(x) for x in v if isinstance(x, str)]
                        break
                if not models:
                    for key in ("models", "data"):
                        v = js.get(key)
                        if isinstance(v, list) and v and isinstance(v[0], dict):
                            models = [str(d.get("name") or d.get("model") or "") for d in v]
                            models = [m for m in models if m]
                            break
            elif isinstance(js, list):
                models = [str(x) for x in js if isinstance(x, str)]
            models = [m.strip() for m in models if isinstance(m, str) and m.strip()]
            if models:
                seen=set(); uniq=[]
                for m in models:
                    if m not in seen:
                        seen.add(m); uniq.append(m)
                uniq.sort(key=_model_sort_key, reverse=True)
                return uniq
        except Exception:
            pass
    return []

# ========== URL pickers ==========

def choose_ext_from_headers(content_type: Optional[str], url: str) -> str:
    if content_type:
        ct = content_type.lower()
        if "mpeg" in ct: return ".mp3"
        if "wav" in ct or "x-wav" in ct or "wave" in ct: return ".wav"
        if "aac" in ct: return ".aac"
        if "ogg" in ct: return ".ogg"
        if "flac" in ct: return ".flac"
    for ext in (".mp3",".wav",".aac",".ogg",".flac"):
        if url.lower().split("?")[0].endswith(ext): return ext
    return ".mp3"

def _extract_items(js: Dict) -> List[Dict]:
    if not isinstance(js, dict): return []
    found: List[List[Dict]] = []
    def walk(x: Any):
        if isinstance(x, list) and x and all(isinstance(it, dict) for it in x):
            found.append(x)
        elif isinstance(x, dict):
            for v in x.values(): walk(v)
        elif isinstance(x, list):
            for v in x: walk(v)
    walk(js)
    for lst in found:
        if any(_pick_urls(it) for it in lst): return lst
    return []

def _pick_urls(item: Dict) -> List[str]:
    out: List[str] = []
    prefer=("audioUrl","sourceAudioUrl","streamAudioUrl","sourceStreamAudioUrl","mp3Url","mp3_url","audio_url","url")
    for k in prefer:
        v=item.get(k)
        if isinstance(v,str) and v.strip().startswith("http"): out.append(v.strip())
    def deep(x):
        if isinstance(x,dict):
            for vv in x.values(): deep(vv)
        elif isinstance(x,list):
            for vv in x: deep(vv)
        elif isinstance(x,str):
            s=x.strip().lower()
            if s.startswith("http") and any(ext in s for ext in (".mp3",".wav",".aac",".ogg",".flac")):
                out.append(x.strip())
    deep(item)
    seen=set(); res=[]
    for u in out:
        if u not in seen: seen.add(u); res.append(u)
    return res

# ========== HTTP helpers ==========

def _make_session(api_key: str):
    requests = _require_requests()
    s = requests.Session()
    s.headers.update({
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "suno-qt/1.0",
    })
    return s

def _post_generate(session, payload: Dict[str, Any], q, cancel_event=None, retries: int=2) -> Dict[str, Any]:
    for attempt in range(retries+1):
        if _cancelled(cancel_event): raise KeyboardInterrupt("cancelled")
        try:
            r = session.post(KIE_GEN_URL, data=json.dumps(payload), timeout=60)
            if r.status_code == 200: return r.json() or {}
            try: js = r.json() or {}
            except Exception: js = {"code": r.status_code, "msg": r.text[:300]}
            msg = str(js)
            if r.status_code in (400,422) and ("callBackUrl" in msg or "callbackUrl" in msg or "Please enter callBackUrl" in msg):
                payload = dict(payload)
                payload.setdefault("callBackUrl", DEFAULT_KIE_CALLBACK)
                payload.setdefault("callbackUrl", DEFAULT_KIE_CALLBACK)
                _log(q, "ℹ️ Додав callBackUrl і повторюю запит…")
                continue
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:500]}")
        except Exception as e:
            if attempt < retries:
                _log(q, f"⚠️ POST повтор {attempt+2}/{retries+1}: {e}")
                time.sleep(1.0 + attempt)
                continue
            raise

def _get_info(session, task_id: str, q, *,
              cancel_event=None,
              on_wait: Optional[Callable[[int, int], None]]=None,
              poll_interval: int=POLL_STEP_SEC,
              max_wait_sec: int=WAIT_MAX_SEC) -> Dict[str, Any]:
    t0=time.time(); idx=0; last_err_log=-999
    while True:
        if _cancelled(cancel_event): raise KeyboardInterrupt("cancelled")
        elapsed = int(time.time() - t0)
        if on_wait:
            try: on_wait(min(elapsed, max_wait_sec), max_wait_sec)
            except Exception: pass
        if elapsed > max_wait_sec:
            raise TimeoutError("Перевищено час очікування задачі.")
        url = KIE_INFO_URLS[idx%len(KIE_INFO_URLS)]; idx+=1
        try:
            r = session.get(url, params={"taskId": task_id}, timeout=45)
            if r.status_code >= 400:
                now = int(time.time())
                if now - last_err_log >= P0LL_ERR_EVERY:  # noqa: name fixed below
                    last_err_log = now
                    _log(q, "ℹ️ сервер готує аудіо… (чекаємо)")
            else:
                data = r.json() or {}
                items = _extract_items(data)
                if items: return data
        except Exception:
            now = int(time.time())
            if now - last_err_log >= P0LL_ERR_EVERY:
                last_err_log = now
                _log(q, "ℹ️ мережа/сервер недоступні на мить… (продовжую чекати)")
        time.sleep(poll_interval)
# fix typo
P0LL_ERR_EVERY = POLL_ERR_EVERY

def _stream_download(session, url: str, dst_path: str, q, cancel_event=None) -> None:
    requests = _require_requests()
    with session.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        total = int(r.headers.get("Content-Length", "0") or 0)
        os.makedirs(os.path.dirname(dst_path) or ".", exist_ok=True)
        done=0; chunk=1024*64
        with open(dst_path, "wb") as f:
            for part in r.iter_content(chunk_size=chunk):
                if _cancelled(cancel_event): raise KeyboardInterrupt("cancelled")
                if not part: continue
                f.write(part); done += len(part)
                if total>0:
                    pct = max(1,min(99,int(done*100/total)))
                    _progress(q, pct, label=f"⬇️ [{_bar(pct)}] {os.path.basename(dst_path)}")

# ========== PUBLIC: tracks ==========

def run_suno_pipeline(
    *,
    api_key: str,
    model: str,
    style_text: str,
    mode: str,  # "auto" | "manual"
    lyrics_text: Optional[str],
    user_titles: Optional[List[str]],
    instrumental: bool,
    output_dir: str,
    save_lyrics_to_file: bool,
    add_time_prefix: bool,
    batches: int,
    length_minutes: int,
    status_queue=None,
    cancel_event=None,
    title_generator: Optional[Callable[[str, str, int], List[str]]] = None,
) -> int:
    if not api_key:  _log(status_queue, "❌ Вкажіть KIE API Key."); return 1
    if not output_dir: _log(status_queue, "❌ Вкажіть папку збереження."); return 1
    os.makedirs(output_dir, exist_ok=True)

    total_tracks = max(1, int(batches)*2)

    titles: List[str] = []
    if user_titles:
        titles = list(user_titles)[:total_tracks]
    elif title_generator:
        try:
            titles = list(title_generator(style_text, "track", total_tracks))[:total_tracks]
        except Exception as e:
            _log(status_queue, f"⚠️ Не вдалося отримати назви від GPT: {e}")
    if not titles:
        titles = _gen_titles_from_style(style_text, "track", total_tracks)
    titles = _unique_names([sanitize_filename(t) for t in titles])

    try:
        session = _make_session(api_key)
    except _NoRequests as e:
        _log(status_queue, f"❌ {e}"); return 1

    _progress(status_queue, 0, label="")
    mode_label = "Лірика" if (mode=="manual" and lyrics_text and not instrumental) else ("Авто/Інструментал" if instrumental else "Авто/Вокал")
    _log(status_queue, f"▶ Старт • треків: {total_tracks} • модель: {model} • режим: {mode_label}")
    _log(status_queue, "🧾 Параметри: назви від " + ("користувача" if user_titles else ("GPT" if title_generator else "style")))

    made = 0
    last_progress = 0
    rounds = int(batches)

    for ri in range(rounds):
        if _cancelled(cancel_event):
            _log(status_queue, "🛑 Зупинено."); return 1

        title_for_round = titles[made] if made < len(titles) else f"Track {made+1}"

        payload = {
            "model": model,
            "style": (style_text or "").strip(),
            "instrumental": bool(instrumental),
            "duration": max(1, int(length_minutes)),
            "customMode": True,
            "callBackUrl": DEFAULT_KIE_CALLBACK,
            "callbackUrl": DEFAULT_KIE_CALLBACK,
            "title": title_for_round,
        }
        if mode == "manual" and lyrics_text and not instrumental:
            payload["prompt"] = (lyrics_text or "").strip()
        else:
            payload["prompt"] = "" if instrumental else AUTO_VOCAL_NUDGE

        _log(status_queue, f"🛰️ Створюю задачу ({ri+1}/{rounds})…")
        try:
            resp_json = _post_generate(session, payload, status_queue, cancel_event=cancel_event)
        except KeyboardInterrupt:
            _log(status_queue, "🛑 Зупинено."); return 1
        except Exception as e:
            _log(status_queue, f"❌ POST помилка: {e}"); return 1

        def _find_task_id(o: Any) -> Optional[str]:
            if isinstance(o, dict):
                for k,v in o.items():
                    if k in ("taskId","task_id","id") and isinstance(v,(str,int)): return str(v)
                    t=_find_task_id(v)
                    if t: return t
            elif isinstance(o, list):
                for it in o:
                    t=_find_task_id(it)
                    if t: return t
            return None
        task_id = _find_task_id(resp_json)
        if not task_id:
            _log(status_queue, f"❌ Відповідь без taskId: {resp_json}"); return 1

        _log(status_queue, f"🛰️ Створив задачу • taskId={task_id}")

        start_f = (made / max(1, total_tracks)) * 100.0
        end_f   = ((made + 2) / max(1, total_tracks)) * 100.0
        wait_cap_f = start_f + (end_f - start_f) * 0.80
        song_idx = made + 1

        def on_wait(elapsed: int, max_wait: int):
            nonlocal last_progress
            cur_overall = int(start_f + (wait_cap_f - start_f) * (elapsed / max(1, max_wait)))
            pct_local = int(elapsed * 100 / max(1, max_wait))
            label = f"⏳ [{_bar(pct_local)}] Очікування {elapsed}/{max_wait}с • трек {song_idx}/{total_tracks}"
            if cur_overall > last_progress:
                last_progress = cur_overall
                _progress(status_queue, cur_overall, label=label)

        try:
            info_json = _get_info(session, task_id, status_queue,
                                  cancel_event=cancel_event,
                                  on_wait=on_wait,
                                  poll_interval=POLL_STEP_SEC,
                                  max_wait_sec=WAIT_MAX_SEC)
        except KeyboardInterrupt:
            _log(status_queue, "🛑 Зупинено."); return 1
        except Exception as e:
            _log(status_queue, f"❌ Помилка очікування: {e}"); return 1

        items = _extract_items(info_json)
        if not items:
            _log(status_queue, "❌ Відповідь без items."); return 1

        for it in items[:2]:
            if _cancelled(cancel_event):
                _log(status_queue, "🛑 Зупинено."); return 1
            urls = _pick_urls(it)
            if not urls:
                _log(status_queue, "⚠️ У елементі немає аудіо-URL."); continue

            base_title = titles[made] if made < len(titles) else (it.get("title") or f"Track {made+1}")
            base_title = sanitize_filename(str(base_title))
            url = urls[0]
            ext = ".mp3"
            tmp = unique_path(os.path.join(output_dir, f"__downloading__ {base_title}{ext}"))
            final = unique_path(os.path.join(output_dir, f"{base_title}{ext}"))

            try:
                with session.get(url, stream=True, timeout=30) as r0:
                    r0.raise_for_status()
                    ext = choose_ext_from_headers(r0.headers.get("Content-Type"), url)
                tmp = os.path.splitext(tmp)[0] + ext
                final = os.path.splitext(final)[0] + ext

                idx = made + 1
                _log(status_queue, f"⬇️ Завантаження [{idx}/{total_tracks}] — {base_title}")
                _stream_download(session, url, tmp, status_queue, cancel_event)
            except KeyboardInterrupt:
                _log(status_queue, "🛑 Зупинено під час завантаження.")
                try: os.remove(tmp)
                except Exception: pass
                return 1
            except Exception as e:
                _log(status_queue, f"❌ Помилка завантаження: {e}")
                try: os.remove(tmp)
                except Exception: pass
                return 1

            try: os.replace(tmp, final)
            except Exception: shutil.move(tmp, final)

            if save_lyrics_to_file and (mode=="manual") and lyrics_text and not instrumental:
                try:
                    with open(os.path.splitext(final)[0]+".txt","w",encoding="utf-8") as f:
                        f.write((lyrics_text or "").strip()+"\n")
                except Exception as e:
                    _log(status_queue, f"⚠️ Не вдалося зберегти текст: {e}")

            if add_time_prefix:
                dur = try_get_duration_seconds(final) or (int(length_minutes)*60)
                pref = fmt_mmss_dot(dur)
                ren = unique_path(os.path.join(output_dir, f"{pref} {os.path.basename(final)}"))
                try: os.replace(final, ren); final = ren
                except Exception: pass

            display_name = os.path.basename(final)
            _log(status_queue, f"✅ Збережено [{idx}/{total_tracks}] — {display_name}")

            made += 1
            last_progress = max(last_progress, int((made/total_tracks)*100.0))
            _progress(status_queue, last_progress, label=f"✅ {display_name}")

        last_progress = max(last_progress, int(end_f))
        _progress(status_queue, last_progress, label="")

    _progress(status_queue, 100, label="")
    _log(status_queue, "✅ Всі треки збережено.")
    return 0

# ========== PUBLIC: albums ==========

def _format_schema(schema: str, track_no: int, track_title: str, ext: str) -> str:
    def pad(m):
        try: width=int(m.group(1))
        except Exception: width=2
        return f"{track_no:0{width}d}"
    out = re.sub(r"\{track_no:(\d+)\}", pad, schema)
    out = out.replace("{track_no}", str(track_no)).replace("{track_title}", track_title).replace("{ext}", ext)
    out = re.sub(r"\{[^}]+\}", "", out)
    return out

def build_albums_pipeline(
    *,
    src_dir: str,
    out_root: str,
    num_albums: int,
    tracks_per: int,
    selection_mode: str,   # "random" | "seq"
    unique_between: bool,
    copy_mode: str,        # "move" | "copy"
    schema: str,           # "{track_no:02} - {track_title}{ext}"
    title_limit: int,
    style_prompt: str,
    status_queue=None,
    cancel_event=None,
    album_title_generator: Optional[Callable[[str, str, int], List[str]]] = None,
    track_title_generator: Optional[Callable[[str, str, int], List[str]]] = None,
) -> int:
    if not (src_dir and os.path.isdir(src_dir)): _log(status_queue,"❌ Невірна папка джерела."); return 1
    if not out_root: _log(status_queue,"❌ Невірна папка призначення."); return 1
    os.makedirs(out_root, exist_ok=True)

    files = collect_audio_files(src_dir)
    if not files: _log(status_queue,"⚠️ У джерелі не знайдено аудіофайлів."); return 1

    n_alb=max(1,int(num_albums)); n_per=max(1,int(tracks_per))
    sel_mode=(selection_mode or "seq").lower(); cp_mode=(copy_mode or "move").lower()

    _progress(status_queue, 0, label="")
    _log(status_queue, f"📀 Початок формування: альбомів {n_alb} × треків {n_per}")

    try:
        alb_titles = list(album_title_generator(style_prompt,"album",n_alb)) if album_title_generator else _gen_titles_from_style(style_prompt,"album",n_alb)
    except Exception:
        alb_titles = _gen_titles_from_style(style_prompt,"album",n_alb)
    alb_titles = _unique_names([sanitize_filename(t) for t in alb_titles])

    used: set[str] = set()
    total_steps = n_alb * n_per
    done_steps = 0
    last_sidebar_ts = 0.0
    SIDEBAR_TICK = 5.0

    for ai in range(n_alb):
        if _cancelled(cancel_event): _log(status_queue,"🛑 Зупинено."); return 1

        alb_title = sanitize_filename(alb_titles[ai] if ai < len(alb_titles) else f"Album {ai+1}")
        alb_dir = unique_path(os.path.join(out_root, alb_title[:max(10, title_limit)]))
        os.makedirs(alb_dir, exist_ok=True)
        _log(status_queue, f"📁 Альбом [{ai+1}/{n_alb}] — {os.path.basename(alb_dir)}")

        available = [p for p in files if p not in used] if unique_between else list(files)
        if not available:
            _log(status_queue, "⚠️ Закінчилися доступні треки."); break
        if sel_mode=="random": random.shuffle(available)
        selected = available[:n_per]
        if unique_between: used.update(selected)

        try:
            trk_titles = list(track_title_generator(style_prompt,"track",len(selected))) if track_title_generator else _gen_titles_from_style(style_prompt,"track",len(selected))
        except Exception:
            trk_titles = _gen_titles_from_style(style_prompt,"track",len(selected))
        trk_titles = _unique_names([sanitize_filename(t) for t in trk_titles])

        for i, src in enumerate(selected, start=1):
            if _cancelled(cancel_event): _log(status_queue,"🛑 Зупинено."); return 1
            base = trk_titles[i-1] if i-1<len(trk_titles) else os.path.splitext(os.path.basename(src))[0]
            base = sanitize_filename(base)[:max(5,title_limit)]
            ext = os.path.splitext(src)[1]
            name = _format_schema(schema, track_no=i, track_title=base, ext=ext)
            if not name.lower().endswith(ext.lower()): name += ext
            dst = unique_path(os.path.join(alb_dir, sanitize_filename(name)))

            try:
                if cp_mode=="copy": shutil.copy2(src, dst)
                else: shutil.move(src, dst)
            except Exception as e:
                _log(status_queue, f"⚠️ Пропущено [{i}/{n_per}] — {os.path.basename(src)} • {e}")
            else:
                _log(status_queue, f"✅ [{i}/{n_per}] {os.path.basename(dst)}")

            done_steps += 1
            now = time.time()
            if now - last_sidebar_ts >= SIDEBAR_TICK or done_steps == total_steps:
                pct = int(done_steps * 100 / max(1, total_steps))
                _progress(status_queue, pct, label=f"📁 {os.path.basename(alb_dir)}")
                last_sidebar_ts = now

        _log(status_queue, f"🏁 Готово — {os.path.basename(alb_dir)}")

    _progress(status_queue, 100, label="")
    _log(status_queue, "✅ Альбоми сформовано.")
    return 0


__all__ = ["run_suno_pipeline", "build_albums_pipeline", "kie_fetch_models"]
