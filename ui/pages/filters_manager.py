# -*- coding: utf-8 -*-
# pages/filters_manager.py
#
# Акуратно визначає статус відео та застосовує фільтр рядків таблиці.
# Працює як для Videos, так і для Shorts (враховує заплановані/приватні/публічні).
from __future__ import annotations
from datetime import datetime, timezone
import re
from PySide6.QtWidgets import QTableWidget, QCheckBox

def _parse_iso_ts(v) -> datetime|None:
    try:
        if not v: return None
        if isinstance(v,(int,float)): return datetime.fromtimestamp(v, tz=timezone.utc)
        s = str(v).replace("Z","+00:00")
        return datetime.fromisoformat(s)
    except Exception:
        return None

def compute_status(item: dict) -> str:
    """Return one of: Public, Scheduled, Private, Unlisted, Draft/Other."""
    privacy = (item.get("privacyStatus") or item.get("privacy") or "").lower().strip()
    ts = item.get("publishAt") or item.get("scheduledPublishTime") or item.get("scheduled") or (item.get("status") or {}).get("publishAt")
    dt = _parse_iso_ts(ts)

    # YouTube logic: public + publishedAt in the past => Public; if future => Scheduled
    snippet = item.get("snippet") or {}
    published_snippet = _parse_iso_ts(snippet.get("publishedAt"))

    if privacy == "public":
        if dt and dt > datetime.now(timezone.utc):
            return "Scheduled"
        if published_snippet and published_snippet <= datetime.now(timezone.utc):
            return "Public"
        # інколи Shorts мають public без publishedAt — вважаємо Public
        if not dt and not published_snippet:
            return "Public"
        return "Public"
    if privacy == "private":
        if dt and dt > datetime.now(timezone.utc):
            return "Scheduled"
        return "Private"
    if privacy == "unlisted":
        if dt and dt > datetime.now(timezone.utc):
            return "Scheduled"
        return "Unlisted"
    # немає чіткого маркера — вважаємо Draft/Other
    if dt and dt > datetime.now(timezone.utc):
        return "Scheduled"
    return "Draft/Other"

def is_published(item: dict) -> bool:
    return compute_status(item) == "Public"

def apply_fast_filter(table: QTableWidget, mode: str) -> None:
    """
    mode: "Всі" | "Неопубліковані" | "Опубліковані"
    'Неопубліковані' включає: Scheduled, Private, Unlisted, Draft/Other.
    """
    COL_CHECK=0; COL_STATUS=10
    items = getattr(table, "_items", [])
    for row in range(table.rowCount()):
        v = items[row] if row < len(items) else {}
        status = compute_status(v)
        hide = False
        if mode == "Опубліковані":
            hide = (status != "Public")
        elif mode == "Неопубліковані":
            hide = (status == "Public")
        else:
            hide = False
        table.setRowHidden(row, hide)
    # поновити підрахунок виділених (совісно з головним кодом)
    selected = 0
    for row in range(table.rowCount()):
        if table.isRowHidden(row): continue
        w = table.cellWidget(row, COL_CHECK)
        if w and isinstance(w, QCheckBox) and w.isChecked(): selected += 1
    # нічого не повертаємо — головний файл сам перераховує лічильники
