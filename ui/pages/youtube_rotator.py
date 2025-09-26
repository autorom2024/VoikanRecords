# youtube_rotator.py
# v1.0 — клієнт YouTube Data API із авто-ротацією ключів
from __future__ import annotations
from typing import Dict, Any
from google_key_pool import KeyPool

YTV3 = "https://www.googleapis.com/youtube/v3"

class YTRotatingClient:
    """GET/POST до YouTube Data API без OAuth (де можливо). Ротація ключів на quotaExceeded / rateLimitExceeded."""
    def __init__(self, pool: KeyPool):
        self.pool = pool

    def videos_list(self, **params) -> Dict[str, Any]:
        r = self.pool.send_with_rotation(f"{YTV3}/videos", params)
        return r.json()

    def search_list(self, **params) -> Dict[str, Any]:
        r = self.pool.send_with_rotation(f"{YTV3}/search", params)
        return r.json()

    def playlistItems_insert(self, body: Dict[str, Any], **params) -> Dict[str, Any]:
        r = self.pool.send_with_rotation(f"{YTV3}/playlistItems", params, method="POST", json_body=body)
        return r.json()
