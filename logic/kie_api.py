# logic/kie_api.py
import requests

CANDIDATE_URLS = [
    "https://api.kie.ai/api/v1/chat/credit",
    "https://api.kie.ai/api/v1/credit",
    "https://api.kie.ai/api/v1/user/credit",
    "https://api.kie.ai/api/v1/billing/credit",
]

def _dig(js, *paths):
    for path in paths:
        cur = js; ok = True
        for k in path:
            if isinstance(cur, dict) and k in cur:
                cur = cur[k]
            else:
                ok = False; break
        if ok and isinstance(cur, (int, float, str)):
            try: return float(cur)
            except Exception: pass
    return None

def kie_fetch_credits(kie_api_key: str):
    if not kie_api_key: return None
    headers = {"Authorization": f"Bearer {kie_api_key}"}
    for url in CANDIDATE_URLS:
        try:
            r = requests.get(url, headers=headers, timeout=15)
            if r.status_code != 200: continue
            js = r.json()
            val = _dig(js, ("data","balance"), ("data","credits"), ("balance",), ("credits",))
            if val is not None: return val
        except Exception:
            continue
    return None
