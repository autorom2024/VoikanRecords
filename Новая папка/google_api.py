# !!! УВАГА: ФАЙЛ ПОВНИЙ, БЕЗ СКОРОЧЕНЬ. НІЧОГО НЕ ВИДАЛЯТИ !!!

import os
import json
import pickle
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow

# ------------------------------
# Налаштування OAuth
# ------------------------------
SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/youtubepartner"
]

TOKEN_DIR = "tokens"
os.makedirs(TOKEN_DIR, exist_ok=True)


def authorize_google(client_secret_file: str, account_name: str = "default"):
    """Авторизація Google API"""
    creds = None
    token_file = os.path.join(TOKEN_DIR, f"token_{account_name}.pkl")

    if os.path.exists(token_file):
        with open(token_file, "rb") as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(client_secret_file, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(token_file, "wb") as token:
            pickle.dump(creds, token)

    service = build("youtube", "v3", credentials=creds)
    email = creds.id_token.get("email") if creds.id_token else None
    return service, email, creds


def revoke_token(account_name: str = "default") -> bool:
    """Видалити локальний токен"""
    token_file = os.path.join(TOKEN_DIR, f"token_{account_name}.pkl")
    if os.path.exists(token_file):
        os.remove(token_file)
        return True
    return False


# ------------------------------
# Допоміжні функції
# ------------------------------

def parse_duration(duration: str) -> int:
    """Парсинг ISO8601 PT#H#M#S → секунди"""
    if not duration:
        return 0
    pattern = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")
    m = pattern.match(duration)
    if not m:
        return 0
    h, m_, s = m.groups()
    return int(h or 0) * 3600 + int(m_ or 0) * 60 + int(s or 0)


def format_duration(seconds: int) -> str:
    """Форматування секунд у H:MM:SS або M:SS"""
    if seconds < 0:
        return "0:00"
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02}:{s:02}"
    else:
        return f"{m}:{s:02}"


# ------------------------------
# Відео
# ------------------------------

def list_my_videos(service, max_results=50) -> List[Dict[str, Any]]:
    """
    Отримати список відео з Uploads Playlist (канал користувача).
    """
    # Отримати playlistId для Uploads
    ch_resp = service.channels().list(part="contentDetails", mine=True).execute()
    uploads_playlist_id = ch_resp["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

    items = []
    page_token = None
    while True and len(items) < max_results:
        req = service.playlistItems().list(
            part="contentDetails",
            playlistId=uploads_playlist_id,
            maxResults=min(50, max_results - len(items)),
            pageToken=page_token,
        )
        resp = req.execute()
        video_ids = [it["contentDetails"]["videoId"] for it in resp["items"]]
        if not video_ids:
            break

        vids = (
            service.videos()
            .list(part="snippet,contentDetails,status,statistics", id=",".join(video_ids))
            .execute()
        )

        for v in vids["items"]:
            duration_s = parse_duration(v["contentDetails"].get("duration"))
            duration_str = format_duration(duration_s)
            items.append({
                "id": v["id"],
                "title": v["snippet"].get("title"),
                "description": v["snippet"].get("description"),
                "duration": v["contentDetails"].get("duration"),
                "duration_s": duration_s,
                "duration_str": duration_str,
                "privacyStatus": v["status"].get("privacyStatus"),
                "publishedAt": v["snippet"].get("publishedAt"),
                "viewCount": v.get("statistics", {}).get("viewCount", 0),
                "thumbnail": v["snippet"]["thumbnails"].get("default", {}).get("url"),
            })

        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    return items


def get_videos_split(service, max_results=200, unpublished_only=False):
    """
    Отримати окремо videos / shorts / all.
    Shorts = <=60 сек або назва/теги містять '#shorts'
    """
    all_items = list_my_videos(service, max_results=max_results)
    videos, shorts = [], []

    for v in all_items:
        if v.get("duration_s", 0) <= 60 or "#shorts" in (v.get("title") or "").lower():
            shorts.append(v)
        else:
            videos.append(v)

    if unpublished_only:
        videos = [x for x in videos if x.get("privacyStatus") != "public"]
        shorts = [x for x in shorts if x.get("privacyStatus") != "public"]

    return {"videos": videos, "shorts": shorts, "all": all_items}


# ------------------------------
# Планування
# ------------------------------

def set_video_schedule(service, video_id: str, publish_time: str, privacy_status: str = "private"):
    """Запланувати відео на publishAt (ISO 8601, UTC)"""
    body = {"id": video_id, "status": {"privacyStatus": "private", "publishAt": publish_time}}
    return service.videos().update(part="status", body=body).execute()


# ------------------------------
# Оновлення метаданих
# ------------------------------

def update_video_metadata(service, video_id: str, title=None, description=None, tags=None, category_id=None):
    """Оновити метадані відео"""
    body = {"id": video_id, "snippet": {}}
    if title: body["snippet"]["title"] = title
    if description: body["snippet"]["description"] = description
    if tags: body["snippet"]["tags"] = tags
    if category_id: body["snippet"]["categoryId"] = category_id
    return service.videos().update(part="snippet", body=body).execute()


def set_localizations(service, video_id: str, localizations: Dict[str, Dict[str, str]]):
    """Додати локалізації до відео"""
    body = {"id": video_id, "localizations": localizations}
    return service.videos().update(part="localizations", body=body).execute()


# ------------------------------
# Завантаження відео
# ------------------------------

def upload_video(service, file_path: str, title: str, description: str, tags: List[str], category_id="22", privacy_status="private"):
    """Завантажити відео на YouTube"""
    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": category_id,
        },
        "status": {"privacyStatus": privacy_status},
    }
    media = MediaFileUpload(file_path, chunksize=-1, resumable=True)
    return service.videos().insert(part="snippet,status", body=body, media_body=media).execute()


# ------------------------------
# Утиліти для часу
# ------------------------------

def to_utc_iso(dt: datetime) -> str:
    """Datetime → ISO 8601 UTC string"""
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def from_utc_iso(s: str) -> datetime:
    """ISO 8601 UTC string → datetime"""
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")
