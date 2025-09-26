# -*- coding: utf-8 -*-
from __future__ import annotations
import os
import threading
import queue
from typing import Any, Dict, Optional

# Імпортуємо бекенд
from logic.video_backend import start_video_jobs, stop_all_jobs

class _ProcessState:
    def __init__(self):
        self.cancel_event = threading.Event()
        self.status_q: "queue.Queue[dict]" = queue.Queue()
        self.settings_applied: bool = False
        self._host = None  # ін'єнктиться зовні (UI/сторінка)

    # Хелпери для логів/очисток — сумісні з різними UI
    def _append_log(self, text: str):
        try:
            if self._host and hasattr(self._host, "append_log"):
                self._host.append_log(self, text)
        except Exception:
            pass

    def _clear_host_logs(self):
        try:
            if self._host and hasattr(self._host, "clear_logs"):
                self._host.clear_logs(self)
        except Exception:
            pass

    def cleanup_temp(self):
        # Місце для тимчасових файлів, якщо треба
        pass

    def _set_start_enabled(self, enabled: bool):
        try:
            if self._host and hasattr(self._host, "set_start_enabled"):
                self._host.set_start_enabled(self, enabled)
        except Exception:
            pass


class VideoLogic:
    """
    Зв'язок між UI і бекендом: збирає cfg з UI та керує старт/стоп.
    """
    def __init__(self, host: Optional[Any] = None):
        self.p = _ProcessState()
        self.p._host = host

    # --- Публічні дії ---
    def start(self, auto_mode: bool = False):
        # 1) зупиняємо будь-які старі воркери
        try:
            stop_all_jobs(self.p.cancel_event)
        except Exception:
            pass

        # 2) свіжий Event для нового запуску
        self.p.cancel_event = threading.Event()

        # 3) автозбереження налаштувань (за бажанням)
        if not self.p.settings_applied:
            self._save_config()
            self.p._append_log("ℹ Автозбереження налаштувань перед стартом")
            self.p.settings_applied = True

        # 4) конфіг з UI
        cfg = self._cfg_from_ui()

        # 5) очистка станів
        self.p.cleanup_temp()
        self.p._clear_host_logs()

        # 6) старт бекенду
        start_video_jobs(cfg, self.p.status_q, self.p.cancel_event)

        # 7) повідомляємо UI
        if self.p._host and hasattr(self.p._host, "set_running"):
            try:
                self.p._host.set_running(self.p, True)
                if hasattr(self.p._host, "set_progress"):
                    self.p._host.set_progress(self.p, 0, "Старт")
            except Exception:
                pass

    def stop(self):
        try:
            stop_all_jobs(self.p.cancel_event)
        except Exception:
            pass

        if self.p._host and hasattr(self.p._host, "set_running"):
            try:
                self.p._host.set_running(self.p, False)
            except Exception:
                pass

        self.p.settings_applied = False
        self.p._set_start_enabled(False)
        self.p.cleanup_temp()
        self.p._append_log("■ Зупинено")

    # --- Приватні ---
    def _save_config(self):
        # Якщо у вашому UI є сторедж — додай тут
        pass

    def _cfg_from_ui(self) -> Dict[str, Any]:
        """
        Збирає конфіг із хоста (UI). Якщо якихось полів нема — ставимо безпечні дефолти.
        Повертаємо рівно ті ключі, які читає бекенд.
        """
        h = self.p._host

        def gv(name: str, default=None):
            # пробуємо різні способи доступу для сумісності з різними UI
            if h is None:
                return default
            if hasattr(h, "get"):
                try:
                    return h.get(name, default)
                except Exception:
                    pass
            if hasattr(h, name):
                try:
                    return getattr(h, name)
                except Exception:
                    pass
            meth = getattr(h, f"get_{name}", None)
            if callable(meth):
                try:
                    return meth()
                except Exception:
                    pass
            return default

        # Директорії
        music_dir = gv("music_dir", os.path.join(os.getcwd(), "music"))
        media_dir = gv("media_dir", os.path.join(os.getcwd(), "media"))
        out_dir   = gv("out_dir",   os.path.join(os.getcwd(), "out"))

        # Основні налаштування
        cfg: Dict[str, Any] = {
            "music_dir": music_dir,
            "media_dir": media_dir,
            "out_dir": out_dir,
            "use_video": bool(gv("use_video", True)),
            "songs": int(gv("songs", 1) or 1),
            "jobs": int(gv("jobs", 1) or 1),
            "until_material": bool(gv("until_material", False)),
            # Відео/Аудіо параметри
            "resolution": gv("resolution", "1920x1080"),
            "fps": int(gv("fps", 30) or 30),
            "threads": int(gv("threads", 2) or 2),
            "speed": float(gv("speed", 1.0) or 1.0),
            "vcodec": gv("vcodec", "libx264"),
            "acodec": gv("acodec", "aac"),
            "crf": int(gv("crf", 20) or 20),
            "pix_fmt": gv("pix_fmt", "yuv420p"),
        }

        # Опційні «форси»
        forced_audio_paths = gv("force_audio_paths", None)
        if forced_audio_paths:
            cfg["force_audio_paths"] = list(forced_audio_paths)
        forced_bg_path = gv("force_bg_path", None)
        if forced_bg_path:
            cfg["force_bg_path"] = forced_bg_path

        basename = gv("basename", None)
        if basename:
            cfg["basename"] = basename

        return cfg
