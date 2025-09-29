# -*- coding: utf-8 -*-
from __future__ import annotations
"""
video_logic.py — тонкий адаптер для інтеграції UI (host) із бекендом.
Публічні методи: start(), stop(), drain(status_q).
"""

import threading
import queue
from typing import Optional, Any, Dict

try:
    from video_backend import start_video_jobs, stop_all_jobs
except Exception:
    # альтернативний шлях імпорту, якщо структура інша
    from logic.video_backend import start_video_jobs, stop_all_jobs

class VideoLogic:
    def __init__(self, host: Optional[Any] = None):
        self.host = host
        self.status_q: "queue.Queue[dict]" = queue.Queue()
        self.cancel_event: threading.Event = threading.Event()

    def set_host(self, host: Any) -> None:
        self.host = host

    def start(self):
        if not self.host:
            return
        cfg: Dict = self.host.get_current_config()
        # Зупиняємо попередні і створюємо новий event
        self.stop()
        self.cancel_event = threading.Event()
        start_video_jobs(cfg, self.status_q, self.cancel_event)

    def stop(self):
        try:
            self.cancel_event.set()
        except Exception:
            pass
        try:
            stop_all_jobs()
        except Exception:
            pass

    def drain(self):
        """Повертає список повідомлень із черги (не блокує)."""
        out = []
        try:
            while True:
                out.append(self.status_q.get_nowait())
        except queue.Empty:
            pass
        return out
