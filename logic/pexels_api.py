# logic/pexels_api.py

import os, requests, time

PEXELS_URL = "https://api.pexels.com/v1/search"

def pexels_search(prompt, api_key, outdir, count, orientation, quality, media_type, cancel_event, status_q):
    """
    prompt       - пошуковий запит
    api_key      - Pexels API ключ
    outdir       - куди зберігати результати
    count        - кількість результатів
    orientation  - "Будь-яка" | "Горизонталь" | "Вертикаль" | "Квадрат"
    quality      - "HD"|"FullHD"|"2K"|"4K"
    media_type   - "Фото"|"Відео"
    cancel_event - threading.Event
    status_q     - черга для логів
    """
    os.makedirs(outdir, exist_ok=True)
    headers = {"Authorization": api_key}
    params = {"query": prompt, "per_page": count}

    if orientation != "Будь-яка":
        params["orientation"] = orientation.lower()

    if media_type == "Фото":
        url = PEXELS_URL
    else:
        url = "https://api.pexels.com/videos/search"

    status_q.put({"msg": f"🔵 Pexels: пошук за промтом '{prompt}'…"})

    resp = requests.get(url, headers=headers, params=params)
    if resp.status_code != 200:
        status_q.put({"msg": f"❌ Pexels error {resp.status_code}"})
        return

    data = resp.json()
    items = data.get("photos" if media_type=="Фото" else "videos", [])

    for i, item in enumerate(items):
        if cancel_event.is_set():
            status_q.put({"msg": "🟡 Pexels: зупинено"})
            return

        if media_type == "Фото":
            file_url = item["src"]["original"]
            fname = f"pexels_{i+1}.jpg"
        else:
            file_url = item["video_files"][0]["link"]
            fname = f"pexels_{i+1}.mp4"

        path = os.path.join(outdir, fname)
        r = requests.get(file_url)
        with open(path, "wb") as f: f.write(r.content)

        status_q.put({"msg": f"✅ Pexels: збережено {path}"})
        time.sleep(0.2)

    status_q.put({"msg": "🟢 Pexels: пошук завершено"})
