# logic/pixabay_api.py

import os, requests, time

PIXABAY_URL = "https://pixabay.com/api/"

def pixabay_search(prompt, api_key, outdir, count, orientation, quality, media_type, cancel_event, status_q):
    os.makedirs(outdir, exist_ok=True)
    params = {
        "key": api_key,
        "q": prompt,
        "per_page": count
    }

    if orientation != "Будь-яка":
        params["orientation"] = orientation.lower()

    if media_type == "Фото":
        url = PIXABAY_URL
    else:
        url = "https://pixabay.com/api/videos/"

    status_q.put({"msg": f"🔵 Pixabay: пошук за промтом '{prompt}'…"})

    resp = requests.get(url, params=params)
    if resp.status_code != 200:
        status_q.put({"msg": f"❌ Pixabay error {resp.status_code}"})
        return

    data = resp.json()
    items = data.get("hits", [])

    for i, item in enumerate(items):
        if cancel_event.is_set():
            status_q.put({"msg": "🟡 Pixabay: зупинено"})
            return

        if media_type == "Фото":
            file_url = item["largeImageURL"]
            fname = f"pixabay_{i+1}.jpg"
        else:
            file_url = item["videos"]["medium"]["url"]
            fname = f"pixabay_{i+1}.mp4"

        path = os.path.join(outdir, fname)
        r = requests.get(file_url)
        with open(path, "wb") as f: f.write(r.content)

        status_q.put({"msg": f"✅ Pixabay: збережено {path}"})
        time.sleep(0.2)

    status_q.put({"msg": "🟢 Pixabay: пошук завершено"})
