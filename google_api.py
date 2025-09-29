import os
import pickle
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from datetime import datetime
from helpers_youtube import parse_duration_to_seconds

SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]
TOKEN_FILE = "token_youtube.pkl"


def authorize_google(client_secret_file="client_secret.json"):
    creds = None
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "rb") as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(client_secret_file, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "wb") as token:
            pickle.dump(creds, token)

    youtube = build("youtube", "v3", credentials=creds)
    # залишаю email як було — None, щоб нічого не ламалось
    return youtube, None, creds


def revoke_token():
    if os.path.exists(TOKEN_FILE):
        os.remove(TOKEN_FILE)
        return True
    return False


def get_videos_split(youtube, max_results=50, unpublished_only=True):
    """
    Повертає словник {"videos": [...], "shorts": [...]}
    """
    videos = []
    shorts = []

    try:
        request = youtube.search().list(
            part="id",
            forMine=True,
            type="video",
            order="date",
            maxResults=max_results
        )
        response = request.execute()

        ids = [item["id"]["videoId"] for item in response.get("items", [])]
        if not ids:
            return {"videos": [], "shorts": []}

        details = youtube.videos().list(
            part="snippet,contentDetails,status,statistics",
            id=",".join(ids)
        ).execute()

        for v in details.get("items", []):
            status = v.get("status", {})
            snippet = v.get("snippet", {})
            content = v.get("contentDetails", {})
            stats = v.get("statistics", {})

            # Пропускаємо опубліковані, якщо треба лише неопубліковані
            if unpublished_only and status.get("privacyStatus") == "public" and not status.get("publishAt"):
                continue

            vid = {
                "id": v["id"],
                "title": snippet.get("title"),
                "description": snippet.get("description"),
                "duration": content.get("duration"),
                "privacyStatus": status.get("privacyStatus"),
                "publishAt": status.get("publishAt"),
                "viewCount": stats.get("viewCount", 0),
            }

            # Визначення Shorts
            dur_sec = parse_duration_to_seconds(content.get("duration"))
            if dur_sec <= 60:
                shorts.append(vid)
            else:
                videos.append(vid)

        return {"videos": videos, "shorts": shorts}

    except HttpError as e:
        raise Exception(f"ПОМИЛКА YouTube API: {e}")


def set_video_schedule(youtube, video_id, publish_time_iso):
    """
    Встановлює розклад публікації для відео
    """
    try:
        request = youtube.videos().update(
            part="status",
            body={
                "id": video_id,
                "status": {
                    "privacyStatus": "private",
                    "publishAt": publish_time_iso,
                    "selfDeclaredMadeForKids": False
                }
            }
        )
        return request.execute()
    except HttpError as e:
        raise Exception(f"ПОМИЛКА планування: {e}")
