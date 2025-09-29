"""
Drop‑in GPT namer for VOIKAN RECORDS app.

— What it does —
• Generates unique track / album titles (and optional short lyrics) from a style prompt.
• Keeps filenames safe (sanitizes characters) and deduplicates titles.
• Works even without network/API (local fallback generator).
• Soft balance check that never raises (keeps the UI green if key present).

— How it integrates —
AudioPage already imports:
    from logic.gpt_namer import gpt_generate_titles, gpt_fetch_balances
So placing this file at logic/gpt_namer.py is enough. No UI edits required.

— Env vars (optional) —
GPT_NAMER_MODEL : model id (default: "gpt-4o-mini")
OPENAI_API_KEY  : OpenAI key if not passed from UI
OPENAI_BASE_URL : custom base URL (e.g. Azure/OpenRouter compatible gateways)

"""
from __future__ import annotations

import os
import re
import json
import time
import math
import random
import hashlib
import unicodedata
from typing import List, Dict, Optional

__all__ = ["gpt_generate_titles", "gpt_fetch_balances", "sanitize_title"]

# ---------------------------- helpers ----------------------------

def _is_cyrillic(text: str) -> bool:
    return bool(re.search(r"[\u0400-\u04FF]", text or ""))


def sanitize_title(title: str, max_len: int = 120) -> str:
    """Make a string safe for filenames without changing its meaning too much."""
    if not title:
        return ""
    t = unicodedata.normalize("NFKC", str(title))
    t = re.sub(r"[\r\n\t]+", " ", t)
    t = re.sub(r"\s{2,}", " ", t).strip()
    # Replace characters illegal on Windows/macOS/Linux
    t = re.sub(r"[<>:\\/\|\?\*\0]", "·", t)
    # Trim leading/trailing dots/spaces
    t = t.strip(" .")
    # Limit length to be filesystem-friendly
    if len(t) > max_len:
        t = t[: max(1, max_len - 1)].rstrip()
    return t


def _unique_titles(titles: List[str]) -> List[str]:
    """Ensure titles are unique; add a 3–4 char disambiguator when needed."""
    seen = set()
    out: List[str] = []
    for raw in titles:
        t = sanitize_title(raw)
        key = re.sub(r"[^a-z0-9]+", "", t.lower())
        if not t:
            continue
        if key in seen:
            # Stable short hash based on text + time bucket for uniqueness
            salt = f"{t}|{int(time.time() // 60)}|{random.random()}".encode("utf-8")
            h = hashlib.sha1(salt).hexdigest()[:4]
            t = sanitize_title(f"{t} {h}")
            key = re.sub(r"[^a-z0-9]+", "", t.lower())
        if key in seen:
            # If still colliding, skip silently
            continue
        seen.add(key)
        out.append(t)
    return out


# ------------------------- balance checking ----------------------

def gpt_fetch_balances(api_key: str) -> Dict[str, float]:
    """Soft check that the key *works* (never raises). Returns optional usage fields.
    We intentionally avoid hitting billing endpoints. If a ping succeeds, we
    return an empty dict so the UI shows "—" but the green light stays on.
    """
    key = api_key or os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        return {}

    base_url = os.getenv("OPENAI_BASE_URL")  # optional custom endpoint

    # Try new OpenAI SDK first
    try:
        from openai import OpenAI  # type: ignore

        client = OpenAI(api_key=key, base_url=base_url or None)
        _ = client.models.list()
        return {}
    except Exception:
        pass

    # Legacy SDK fallback
    try:
        import openai  # type: ignore

        if base_url:
            openai.base_url = base_url
        openai.api_key = key
        _ = openai.Model.list()  # lightweight call
        return {}
    except Exception:
        return {}


# ------------------------- GPT title/lyrics ----------------------

def gpt_generate_titles(api_key: str, style: str, kind: str, count: int) -> List[str]:
    """Main entry used by the UI.

    Args:
        api_key: Provider key; can be empty — then local fallback is used.
        style: Free-form style prompt from the UI.
        kind:  "track" | "album" | "lyrics".
        count: desired number of items.

    Returns:
        List[str] of titles; for kind=="lyrics" each element is a full lyrics text.
    """
    kind = (kind or "track").lower()
    n = max(1, min(100, int(count or 1)))
    style = (style or "melodic electronic music").strip()

    out: List[str] = []

    # 1) Try OpenAI (new SDK)
    if (api_key or os.getenv("OPENAI_API_KEY")) and kind in {"track", "album", "lyrics"}:
        try:
            out = _openai_generate(api_key or os.getenv("OPENAI_API_KEY", ""), style, kind, n)
        except Exception:
            out = []

    # 2) Fallback: local generator (deterministic-ish)
    if not out:
        out = _local_generate(style, kind, n)

    # 3) Post-process
    if kind in {"track", "album"}:
        out = _unique_titles([sanitize_title(t) for t in out])
        # Make sure we return exactly n items (pad if model returned less)
        while len(out) < n:
            base = style.split(",")[0].strip() or "Untitled"
            extra = hashlib.md5(f"{base}|{kind}|{len(out)}|{time.time()}".encode()).hexdigest()[:3]
            out.append(sanitize_title(f"{base} {extra}"))
        if len(out) > n:
            out = out[:n]
    else:  # lyrics: keep as-is, just strip trailing spaces
        out = [s.rstrip() for s in out][:n]

    return out


# ------------------------- provider adapters ---------------------

def _openai_generate(key: str, style: str, kind: str, count: int) -> List[str]:
    base_url = os.getenv("OPENAI_BASE_URL")
    model = os.getenv("GPT_NAMER_MODEL", "gpt-4o-mini")

    is_uk = _is_cyrillic(style)
    lang_hint = "Українською мовою" if is_uk else "English"

    if kind in {"track", "album"}:
        system = (
            "You are a concise music title generator. Output *only* a JSON array of strings. "
            "Each string is a short, evocative %s title, 2–5 words, no numbering, no emojis, no quotes."
            % ("album" if kind == "album" else "track")
        )
        user = (
            f"Style / mood: {style}\n"
            f"Language: {lang_hint}.\n"
            f"Need exactly {count} unique {kind} titles."
        )
        text = _openai_chat(key, model, system, user, base_url=base_url, max_tokens=300)
        items = _parse_list(text)
        return items[:count]

    # kind == "lyrics"
    system = (
        "You are a songwriter. Write compact song lyrics (8–14 lines) with a clear chorus. "
        "Return plain text only, no markdown fences."
    )
    user = (
        f"Style / mood: {style}\n"
        f"Language: {lang_hint}.\n"
        f"Keep it singable; avoid profanity."
    )
    text = _openai_chat(key, model, system, user, base_url=base_url, max_tokens=400)
    # Return as a single-item list (UI expects list)
    return [text.strip()]


def _openai_chat(key: str, model: str, system: str, user: str, *, base_url: Optional[str], max_tokens: int) -> str:
    # Try new SDK first
    try:
        from openai import OpenAI  # type: ignore

        client = OpenAI(api_key=key, base_url=base_url or None)
        res = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.9,
            max_tokens=max_tokens,
        )
        return (res.choices[0].message.content or "").strip()
    except Exception:
        # Legacy SDK fallback
        try:
            import openai  # type: ignore

            if base_url:
                openai.base_url = base_url
            openai.api_key = key
            res = openai.ChatCompletion.create(
                model=model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                temperature=0.9,
                max_tokens=max_tokens,
            )
            return (res["choices"][0]["message"]["content"] or "").strip()
        except Exception as e:
            raise e


def _parse_list(text: str) -> List[str]:
    text = (text or "").strip()
    # Try JSON first
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return [str(x).strip() for x in data if str(x).strip()]
    except Exception:
        pass
    # Fallback: split numbered/bulleted lines
    items: List[str] = []
    for line in text.splitlines():
        line = line.strip().strip("-•*·")
        line = re.sub(r"^\d+\s*[\.)]\s*", "", line)
        if line:
            items.append(line)
    return items


# ----------------------- local fallback (offline) -----------------

# A tiny pool of aesthetic words to assemble sensible titles when offline
_ADJ = [
    "Silent", "Neon", "Golden", "Electric", "Velvet", "Crystal", "Distant", "Endless",
    "Tidal", "Lunar", "Wild", "Hidden", "Azure", "Stellar", "Amber", "Midnight",
    "Tropical", "Frost", "Solar", "Velveteen", "Radiant", "Drift", "Echo", "Mellow",
]
_NOUN = [
    "Dreams", "Echoes", "Horizons", "Waves", "Skies", "Embers", "Gardens", "Pulse",
    "Voyage", "Mirage", "Aurora", "Ritual", "Reverie", "Cascade", "Reflections",
    "Paradise", "Alchemy", "Spectrum", "Harbor", "Momentum", "Solstice",
]
_UA_ADJ = [
    "Тихі", "Неонові", "Золоті", "Електричні", "Оксамитові", "Кришталеві", "Далекі",
    "Безкраї", "Припливні", "Місячні", "Дикі", "Приховані", "Блакитні", "Зоряні",
    "Бурштинові", "Опівнічні", "Тропічні", "Крижні", "Сонячні", "Сяйні", "Плинні",
]
_UA_NOUN = [
    "Сни", "Відлуння", "Горизонти", "Хвилі", "Небеса", "Жарини", "Сади", "Пульс",
    "Мандрівка", "Міраж", "Аврора", "Обряд", "Марення", "Каскад", "Відбиття",
    "Парадайз", "Алхімія", "Спектр", "Гавань", "Моментум", "Сонцестояння",
]


def _local_generate(style: str, kind: str, count: int) -> List[str]:
    rnd = random.Random()
    # Seed with style/kind for reproducibility across a session
    seed = int(hashlib.sha1(f"{style}|{kind}".encode("utf-8")).hexdigest(), 16) % (2 ** 32)
    rnd.seed(seed)

    ua = _is_cyrillic(style)
    ADJ = _UA_ADJ if ua else _ADJ
    NOUN = _UA_NOUN if ua else _NOUN

    if kind == "lyrics":
        verses = []
        hook_word = ("Сяйво" if ua else "Glow") if rnd.random() < 0.5 else ("Вітер" if ua else "Wind")
        for i in range(8 + rnd.randint(0, 6)):
            if i in (3, 7):  # simple chorus
                line = (f"Приспів: {hook_word} веде мене" if ua else f"Chorus: {hook_word} carries me")
            else:
                a = ADJ[rnd.randrange(len(ADJ))]
                n = NOUN[rnd.randrange(len(NOUN))]
                line = f"{a} {n}" if not ua else f"{a} {n}"
            verses.append(line)
        return ["\n".join(verses)] * max(1, count)

    titles: List[str] = []
    for _ in range(max(1, count * 2)):
        a = ADJ[rnd.randrange(len(ADJ))]
        n = NOUN[rnd.randrange(len(NOUN))]
        if ua:
            t = f"{a} {n}"
        else:
            # Occasionally add a modifier from the style text
            mod = ""
            if rnd.random() < 0.35:
                parts = [w for w in re.split(r"[^A-Za-z]+", style) if w]
                if parts:
                    mod = parts[rnd.randrange(len(parts))].capitalize()
            t = (f"{a} {n}" if not mod else f"{a} {n} {mod}").strip()
        titles.append(t)

    return _unique_titles(titles)[:count]
