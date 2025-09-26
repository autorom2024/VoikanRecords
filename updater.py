# updater.py
from __future__ import annotations
import json, os, time, webbrowser
from pathlib import Path
from typing import Optional
import requests
from packaging.version import Version
from PySide6.QtWidgets import QMessageBox

CHECK_INTERVAL = 60 * 60 * 24  # 1 доба
TIMEOUT = 2  # сек

def _cache_file(app_name: str) -> Path:
    app = app_name.lower().replace(" ", "_")
    if os.name == "nt":
        base = Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / app / "update.json"
    elif sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / app / "update.json"
    else:
        return Path(os.getenv("XDG_CACHE_HOME", Path.home() / ".cache")) / app / "update.json"

def _should_check(cache_path: Path) -> bool:
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        return time.time() - data.get("ts", 0) > CHECK_INTERVAL
    except Exception:
        return True

def _write_cache(cache_path: Path, latest: str):
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps({"ts": int(time.time()), "latest": latest}), encoding="utf-8")

def check_update(manifest_url: str, current_version: str, app_name: str) -> Optional[dict]:
    # вимикач через змінну оточення, напр. MYAPP_NO_UPDATE_CHECK=1
    if os.getenv(f"{app_name.upper().replace(' ', '_')}_NO_UPDATE_CHECK"):
        return None

    cache = _cache_file(app_name)
    if not _should_check(cache):
        return None

    try:
        r = requests.get(manifest_url, timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()
        latest = str(data["version"])
        _write_cache(cache, latest)
        if Version(latest) > Version(current_version):
            return data  # очікуємо поля version, page_url або download_url
    except Exception:
        pass
    return None

def notify_if_update(update: dict, app_name: str, parent=None):
    latest = update.get("version", "?")
    page_url = update.get("page_url") or update.get("url") or update.get("download_url")
    changelog = update.get("changelog", "")
    text = f"Доступна нова версія {latest}.\n{changelog}\n\nВідкрити сторінку оновлення?"
    box = QMessageBox(parent)
    box.setWindowTitle(f"{app_name} — Оновлення")
    box.setText(text.strip())
    yes = box.addButton("Відкрити", QMessageBox.AcceptRole)
    later = box.addButton("Пізніше", QMessageBox.RejectRole)
    box.setIcon(QMessageBox.Information)
    box.exec()
    if box.clickedButton() is yes and page_url:
        webbrowser.open(page_url)

def check_and_notify(*, version: str, manifest_url: str, app_name: str, parent=None):
    upd = check_update(manifest_url, version, app_name)
    if upd:
        notify_if_update(upd, app_name, parent)
