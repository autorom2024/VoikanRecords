# -*- coding: utf-8 -*-
# google_api_autofill.py — OAuth + отримання списку відео через uploads → videos.list
# Важливо: потрібен файл client_secret.json у корені або шлях у CREDENTIALS_FILE.

import os
from typing import Dict, List, Tuple
from datetime import datetime

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/youtube"]
CREDENTIALS_FILE = os.getenv("GOOGLE_CLIENT_SECRETS", "client_secret.json")
TOKEN_FILE = os.getenv("GOOGLE_TOKEN_FILE_AUTOFILL", "token_autofill.json")

def authorize_google_autofill():
    """Повертає (youtube, creds, channel_id)"""
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                raise FileNotFoundError(f"Не знайдено {CREDENTIALS_FILE}. Покладіть client_secret.json поруч із програмою.")
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w", encoding="utf-8") as f:
            f.write(creds.to_json())

    youtube = build("youtube", "v3", credentials=creds)

    # Отримаємо channel_id для mine
    ch = youtube.channels().list(part="id", mine=True).execute()
    items = ch.get("items") or []
    channel_id = items[0]["id"] if items else None
    return youtube, creds, channel_id

def _parse_duration_iso8601(iso: str) -> int:
    # Простий парсер: PT#H#M#S
    if not iso or not iso.startswith("PT"):
        return 0
    import re
    h = m = s = 0
    mobj = re.findall(r"(\d+H)|(\d+M)|(\d+S)", iso)
    for part in mobj:
        if part[0]: h = int(part[0][:-1])
        if part[1]: m = int(part[1][:-1])
        if part[2]: s = int(part[2][:-1])
    return h*3600 + m*60 + s

def _collect_uploads_video_ids(youtube, max_results=500) -> List[str]:
    # 1) uploads playlist
    ch = youtube.channels().list(part="contentDetails", mine=True).execute()
    items = ch.get("items") or []
    if not items:
        return []
    uploads = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]

    ids = []
    page_token = None
    while True:
        res = youtube.playlistItems().list(
            part="contentDetails", playlistId=uploads, maxResults=50, pageToken=page_token
        ).execute()
        for it in res.get("items", []):
            vid = (it.get("contentDetails") or {}).get("videoId")
            if vid:
                ids.append(vid)
        page_token = res.get("nextPageToken")
        if not page_token or len(ids) >= max_results:
            break
    return ids[:max_results]

def _fetch_videos(youtube, ids: List[str]) -> List[dict]:
    out = []
    for i in range(0, len(ids), 50):
        chunk = ids[i:i+50]
        res = youtube.videos().list(
            part="id,snippet,contentDetails,statistics,status,localizations",
            id=",".join(chunk)
        ).execute()
        for it in res.get("items", []):
            sn = it.get("snippet", {}) or {}
            st = it.get("status", {}) or {}
            cd = it.get("contentDetails", {}) or {}
            stats = it.get("statistics", {}) or {}
            locs = it.get("localizations", {}) or {}
            out.append({
                "id": it.get("id"),
                "title": sn.get("title",""),
                "description": sn.get("description",""),
                "tags": sn.get("tags", []),
                "duration": cd.get("duration",""),
                "viewCount": int(stats.get("viewCount", 0)) if stats.get("viewCount") else 0,
                "privacyStatus": st.get("privacyStatus",""),
                "publishAt": st.get("publishAt") or sn.get("publishedAt"),
                "localizations": locs,
                "categoryId": sn.get("categoryId"),
            })
    return out

def get_videos_split(youtube, max_results=500, unpublished_only=False) -> Dict[str, List[dict]]:
    """
    Повертає {"videos": [...], "shorts": [...]}
    Shorts — тривалість <= 60 секунд.
    unpublished_only — якщо True, повертає тільки те, що не public без явного schedule.
    """
    ids = _collect_uploads_video_ids(youtube, max_results=max_results)
    if not ids:
        return {"videos": [], "shorts": []}
    data = _fetch_videos(youtube, ids)

    videos, shorts = [], []
    for v in data:
        secs = _parse_duration_iso8601(v.get("duration", ""))
        is_short = secs and secs <= 60
        if unpublished_only:
            if v.get("privacyStatus","").lower() == "public" and not v.get("publishAt"):
                # опубліковані — пропускаємо
                continue
        (shorts if is_short else videos).append(v)

    return {"videos": videos, "shorts": shorts}
