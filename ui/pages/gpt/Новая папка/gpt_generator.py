# -*- coding: utf-8 -*-
# ui/pages/gpt/gpt_generator.py
#
# Генератор метаданих для YouTube (канал-агностичний):
# - структура опису: HOOK + MUSIC DETAILS + STORY + SOFT SEO + CTA (Subscribe + Like + 🔔)
# - емодзі в абзацах; можна вимкнути директивою в промті: `emoji: off` або задати список: `emoji: 🎧⚡🔥`
# - унікальність заголовків по "namespace" (промт/канал), ретраї + автодиверсифікація
# - антикліше (не падає, а переписує штампи)
# - рівно N хештегів (без спаму в описі)
# - повертає: (title, description, tags_ignored, hashtags_list, keywords_string)

from __future__ import annotations
import os, re, json, difflib, random, hashlib
from typing import List, Tuple, Dict, Any
import requests
from helpers_youtube import parse_duration  # Додано імпорт

STYLE_CYCLE = ["IMAGERY", "EMOTION", "CONTEXT", "POETIC"]
CACHE_FILE = os.path.join(os.path.dirname(__file__), "gpt_cache.json")

# ===== Анти-кліше =====
BANNED_WORDS = {"unlock", "secrets", "magic"}
BANNED_PHRASES = {
    "surrender to the soothing whispers",
    "surrender to the gentle embrace",
    "dive into tranquility",
    "let yourself drift away",
    "immerse yourself",
    "let the night cradle your soul",
    "embrace the soothing vibes",
    "perfect for relaxation, study, or meditation",
    "perfect for studying, relaxing, and dreaming",
}
BANNED_REGEX = [
    r"\bimmer(se|s)e\s+yourself\b",
    r"\blet\s+the\s+night\s+cradle\s+your\s+soul\b",
    r"\b(surrender|give\s+in)\s+to\s+the\s+(soothing|gentle)\s+(whispers|embrace)\b",
    r"\b(dive|slip)\s+into\s+(calm|tranquility|serenity)\b",
    r"\b(embrace|ride)\s+the\s+soothing\s+vibes\b",
]

# ===== Унікальність =====
SIMILARITY_THRESHOLD = 0.58
RECENT_LIMIT = 15
MAX_RETRIES = 3

# ===== Емодзі =====
DEFAULT_EMOJIS = list("🎧🎵✨🔥🌙⭐⚡🎹🎸🎷🎻🥁🌀🌌")
GENRE_EMOJIS: Dict[str, List[str]] = {
    "lofi": list("🌙☕📚🧸✨"), "phonk": list("🔥💀🛞🏁⚡"), "trap": list("🔥⚡🧨🎛️"),
    "dnb": list("⚙️🚧🔊🌀"), "techno": list("🖤⚙️🔩🚧"), "synthwave": list("🌆🌌🟣💾"),
    "ambient": list("🌫️🌌🕊️✨"), "piano": list("🎹🌙🤍"), "jazz": list("🎷🍷🕯️"),
    "classical": list("🎻🏛️🌟"), "metal": list("🤘🔥⚡"), "rock": list("🎸🔥⚡"),
    "house": list("🎚️🎛️✨"), "chill": list("🌙✨🧊"), "sleep": list("😴🌙🛌"),
    "study": list("📚💡☕"), "gaming": list("🎮⚡🟩"), "rain": list("🌧️☔🏙️"),
    "workout": list("💪🔥⏱️"), "meditation": list("🧘‍♂️🌿✨"),
}

# ===== Багатомовні CTA =====
MULTILINGUAL_CTA = {
    "en": "👍 If this mix vibes with you, **subscribe**, drop a like and tap the 🔔 to never miss a new session.",
    "uk": "👍 Якщо цей мікс тобі зайшов — **підпишись**, постав лайк і натисни 🔔, щоб не пропустити нові сети.",
    "es": "👍 Si te gusta este mix, **suscríbete**, deja un like y activa la 🔔 para no perderte nuevas sesiones.",
    "fr": "👍 Si ce mix vous plaît, **abonnez-vous**, likez et activez la 🔔 pour ne manquer aucune nouvelle session.",
    "de": "👍 Wenn dir dieser Mix gefällt, **abonniere**, like und aktiviere die 🔔, um keine neuen Sessions zu verpassen.",
    "pt": "👍 Se você curtiu este mix, **inscreva-se**, deixe um like e ative o 🔔 para não perder novas sessões.",
    "it": "👍 Se ti piace questo mix, **iscriviti**, metti mi piace e attiva la 🔔 per non perdere nuove sessioni.",
    "pl": "👍 Jeśli podoba Ci się ten miks, **subskrybuj**, zostaw like i naciśnij 🔔, aby nie przegapić nowych sesji.",
    "nl": "👍 Als je van deze mix geniet, **abonneer je**, like en activeer de 🔔 om geen nieuwe sessies te missen.",
    "tr": "👍 Bu mix hoşuna gittiyse, **abone ol**, beğen ve yeni seansları kaçırmamak için 🔔'a tıkla.",
    "ja": "👍 このミックスが気に入ったら、**チャンネル登録**、いいね、そして🔔をタップして新しいセッションを見逃さないでください。",
    "ko": "👍 이 믹스가 마음에 든다면 **구독**, 좋아요를 누르고 🔔을 탭하여 새로운 세션을 놓치지 마세요.",
    "zh": "👍 如果你喜欢这个混音，请**订阅**、点赞并点击🔔，不错过任何新会话。",
    "ar": "👍 إذا أعجبك هذا المزيج، **اشترك**، أضف إعجابًا واضغط على 🔔 حتى لا تفوت الجلسات الجديدة.",
    "hi": "👍 अगर आपको यह मिक्स पसंद आया, तो **सब्सक्राइब** करें, लाइक करें और 🔔 को टैप करें ताकि आप कोई नया सत्र न चूकें।"
}

# ===== Cache =====
def _load_cache() -> dict:
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            obj = json.load(f)
            if not isinstance(obj, dict): raise ValueError
            obj.setdefault("style_index", 0)
            if not isinstance(obj.get("last_titles"), dict):
                obj["last_titles"] = {"global": list(obj.get("last_titles") or [])}
            return obj
    except Exception:
        return {"style_index": 0, "last_titles": {"global": []}}

def _save_cache(obj: dict) -> None:
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def _rotate_style() -> str:
    c = _load_cache()
    idx = c.get("style_index", 0) % len(STYLE_CYCLE)
    c["style_index"] = idx + 1
    _save_cache(c)
    return STYLE_CYCLE[idx]

def _ns_key(text: str) -> str:
    base = re.sub(r"\s+", " ", (text or "").strip().lower())
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:12] or "global"

def _remember_title(ns: str, title: str) -> None:
    c = _load_cache(); lt: Dict[str, List[str]] = c.get("last_titles", {})
    arr = ([title] + lt.get(ns, []))[:80]; lt[ns] = arr
    c["last_titles"] = lt; _save_cache(c)

def _recent_titles(ns: str) -> List[str]:
    return (_load_cache().get("last_titles") or {}).get(ns, [])

# ===== Нормалізація =====
_rx_emoji = re.compile("[" "\U0001F300-\U0001F6FF" "\U0001F900-\U0001F9FF" "\u2600-\u26FF\u2700-\u27BF" "]", re.UNICODE)

def _normalize(s: str) -> str:
    s = s.lower(); s = _rx_emoji.sub(" ", s); s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def _too_similar(a: str, b: str, t: float = SIMILARITY_THRESHOLD) -> bool:
    return bool(a and b and difflib.SequenceMatcher(None, _normalize(a), _normalize(b)).ratio() >= t)

# ===== Конфіг із промта =====
def _detect_config(theme: str) -> Dict[str, Any]:
    text = theme or ""; low = text.lower()
    # emoji directive
    require_emoji, custom = True, None
    m = re.search(r"emoji\s*:\s*([^\n\r]+)", low)
    if m:
        raw = m.group(1).strip()
        if raw.startswith("off"): require_emoji = False
        else: custom = [ch for ch in raw if ch.strip()]
    # genre
    genre = next((g for g in GENRE_EMOJIS if g in low), None)
    emoji_set = custom or (GENRE_EMOJIS.get(genre) if genre else DEFAULT_EMOJIS)
    # seed keywords
    words = re.findall(r"[a-z]{4,}", low)
    stop = {"channel","music","video","mix","playlist","style","theme","prompt","title","description","hashtags","emoji","clickbait"}
    seed = sorted(set(w for w in words if w not in stop))[:40]
    return {"require_emoji": require_emoji, "emoji_set": emoji_set, "seed": seed, "ns": _ns_key(low), "genre": genre or "generic"}

# ===== Антикліше/CTA =====
def _contains_banned(d: str) -> bool:
    t = (d or "").lower()
    return any(p in t for p in BANNED_PHRASES) or any(re.search(rx, t) for rx in BANNED_REGEX)

def _rewrite_cliches(desc: str, seed_terms: List[str]) -> str:
    text = desc
    repl = {
        r"\bimmerse yourself\b": "drift with every layer of the arrangement",
        r"\bimmerse\s+yourself\b": "sink deeper into the texture of the sound",
        r"\blet the night cradle your soul\b": "as night settles over the city skyline",
        r"\bsurrender to the soothing whispers\b": "follow the hush of distant chords",
        r"\bsurrender to the gentle embrace\b": "lean into the warm pulse of the mix",
        r"\bdive into tranquility\b": "step into a quiet pocket of calm",
        r"\bperfect for relaxation, study, or meditation\b": "built for focus, late work hours and slow evenings",
        r"\bembrace the soothing vibes\b": "ride the soft tide of rhythms",
    }
    for pat, rpl in repl.items():
        text = re.sub(pat, rpl, text, flags=re.I)
    seeds = [s for s in seed_terms if re.match(r"[a-z]{3,}", s or "", flags=re.I)]
    seeds = list(dict.fromkeys(seeds))[:6]
    if seeds:
        tail = " ".join(f"#{re.sub(r'[^a-z0-9_]', '', s.lower())}" for s in seeds[:3])
        if tail:
            text = (text + (" " if re.search(r"[.!?…]\s*$", text) else ". ") + tail).strip()
    return re.sub(r"[ \t]{2,}", " ", re.sub(r"#{2,}", "#", text)).strip()

def _sprinkle_paragraph_emojis(pars: List[str], emoji_set: List[str]) -> List[str]:
    if not pars: return pars
    ems = list(emoji_set or DEFAULT_EMOJIS); random.shuffle(ems)
    out = []
    for i, p in enumerate(pars):
        emo = ems[i % len(ems)] if ems else ""
        out.append((emo + " " if emo and not p.strip().startswith(("**", emo)) else "") + p.strip())
    return out

def _detect_language(text: str) -> str:
    """Визначає мову тексту для CTA"""
    text_lower = text.lower()
    
    # Перевірка на різні мови
    if any(word in text_lower for word in ["subscribe", "like", "bell", "session"]):
        return "en"
    elif any(word in text_lower for word in ["підпис", "лайк", "дзвіночок", "сети"]):
        return "uk"
    elif any(word in text_lower for word in ["подпиш", "лайк", "колокольчик", "сеты"]):
        return "ru"
    elif any(word in text_lower for word in ["suscríbete", "like", "campana", "sesión"]):
        return "es"
    elif any(word in text_lower for word in ["abonnez", "like", "cloche", "session"]):
        return "fr"
    elif any(word in text_lower for word in ["abonniere", "like", "glocke", "session"]):
        return "de"
    elif any(word in text_lower for word in ["inscreva", "like", "sino", "sessão"]):
        return "pt"
    elif any(word in text_lower for word in ["iscriviti", "like", "campanella", "sessione"]):
        return "it"
    elif any(word in text_lower for word in ["subskrybuj", "like", "dzwonek", "sesja"]):
        return "pl"
    elif any(word in text_lower for word in ["abonneer", "like", "bel", "sessie"]):
        return "nl"
    elif any(word in text_lower for word in ["abone", "beğen", "zil", "oturum"]):
        return "tr"
    elif any(word in text_lower for word in ["登録", "いいね", "ベル", "セッション"]):
        return "ja"
    elif any(word in text_lower for word in ["구독", "좋아요", "벨", "세션"]):
        return "ko"
    elif any(word in text_lower for word in ["订阅", "点赞", "铃铛", "会话"]):
        return "zh"
    elif any(word in text_lower for word in ["اشترك", "إعجاب", "جرس", "جلسة"]):
        return "ar"
    elif any(word in text_lower for word in ["सब्सक्राइब", "लाइक", "घंटी", "सत्र"]):
        return "hi"
    
    return "en"  # default

def _ensure_cta_block(pars: List[str], lang_hint: str = "en") -> List[str]:
    txt = "\n".join(pars).lower()
    
    # Перевірка наявності CTA на різних мовах
    cta_keywords = [
        "subscribe", "підпис", "подпиш", "suscríbete", "abonnier", 
        "subscribirse", "inscreva", "iscriviti", "abonner", "abonnieren",
        "subskrybuj", "abonneer", "abone", "登録", "구독", "订阅", "اشترك", "सब्सक्राइब"
    ]
    if any(k in txt for k in cta_keywords):
        return pars
    
    # Визначення мови для CTA
    detected_lang = _detect_language(txt)
    cta = MULTILINGUAL_CTA.get(detected_lang, MULTILINGUAL_CTA["en"])
    
    return pars + [cta]

def _strip_inline_hashtags(text: str) -> str:
    return "\n".join([ln for ln in text.splitlines() if not re.match(r"\s*(#\w+\s*){3,}$", ln.strip())]).strip()

# ===== Заголовок =====
def _ensure_one_emoji(title: str, *, need: bool, emoji_set: List[str]) -> str:
    found = _rx_emoji.findall(title)
    if not need:
        return re.sub(r"\s+", " ", _rx_emoji.sub(" ", title)).strip() if found else title
    if not found:
        emo = random.choice(emoji_set or DEFAULT_EMOJIS)
        return title.replace(" – ", f" {emo} – ", 1) if " – " in title else f"{title} {emo}"
    first = found[0]
    stripped = re.sub(r"\s+", " ", _rx_emoji.sub(" ", title)).strip()
    return stripped.replace(" – ", f" {first} – ", 1) if " – " in stripped else f"{stripped} {first}"

def _enforce_title_rules(title: str, *, need_emoji: bool, emoji_set: List[str], max_len: int=98) -> str:
    t = title.strip()
    t = re.sub(r"\(?20(2[4-5])\)?", "", t).strip(" -•|.,")
    for w in BANNED_WORDS:
        if w in t.lower():
            t = re.sub(re.escape(w), "", t, flags=re.I).strip()
    t = _ensure_one_emoji(t, need=need_emoji, emoji_set=emoji_set)
    if len(t) > max_len:
        cut = t[:max_len]
        for ch in (" — ", " – ", " - "):
            if ch in cut: cut = cut[:cut.rfind(ch)].strip(); break
        t = cut if len(cut) >= 20 else t[:max_len].strip()
    return t

def _validate_description(desc: str, seeds: List[str], emoji_set: List[str], lang_hint: str) -> str:
    d = _strip_inline_hashtags((desc or "").strip())
    parts = [x.strip() for x in re.split(r"\n{2,}", d) if x.strip()]
    uniq, seen = [], set()
    for p in parts:
        k = re.sub(r"\s+", " ", p.lower())[:160]
        if k not in seen: uniq.append(p); seen.add(k)
    parts = uniq
    joined = "\n\n".join(parts)
    if _contains_banned(joined):
        joined = _rewrite_cliches(joined, seeds)
        parts = [p.strip() for p in re.split(r"\n{2,}", joined) if p.strip()]
    while len(parts) < 4:
        filler = [
            "A warm blend of textures, subtle rhythm and atmosphere crafted for long focus and calm late hours.",
            "Expect gentle transitions, evolving pads and small details that reward listening on good headphones.",
            "Mixed with care to keep the energy smooth and steady from start to finish.",
        ]
        parts.append(filler[min(len(parts), len(filler)-1)])
    parts = _sprinkle_paragraph_emojis(parts[:5], emoji_set)
    parts = _ensure_cta_block(parts, lang_hint=lang_hint)
    return re.sub(r"[ \t]{2,}", " ", "\n\n".join(parts).strip())

# ===== Локальна диверсифікація =====
_ENRICH_TOKENS = ["Edition","Escape","Journey","Memoir","Reflections","Diaries","Chronicles"]

def _diversify_title(title: str, *, need_emoji: bool, emoji_set: List[str]) -> str:
    base = re.sub(r"\s+[" "\U0001F300-\U0001F6FF" "\U0001F900-\U0001F9FF" "\u2600-\u26FF\u2700-\u27BF" "]$", "", title).strip()
    tok = random.choice(_ENRICH_TOKENS)
    cand = f"{base} — {tok}" if " – " not in base else base.split(" – ",1)[0] + f" – {base.split(' – ',1)[1]} | {tok}"
    return _enforce_title_rules(cand, need_emoji=need_emoji, emoji_set=emoji_set)

# ===== OpenAI =====
def _openai_chat(api_key: str, messages: list, model="gpt-4o-mini", temperature: float=0.25, max_tokens: int = 900) -> str:
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens,
               "response_format": {"type": "json_object"}}
    r = requests.post(url, headers=headers, json=payload, timeout=60)
    if r.status_code == 401: raise RuntimeError("OpenAI 401 Unauthorized")
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]

def _json_loose(text: str) -> dict:
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", (text or "").strip(), flags=re.I)
    i, j = s.find("{"), s.rfind("}")
    if i >= 0 and j > i: s = s[i:j+1]
    s = re.sub(r",\s*(\]|})", r"\1", s)
    s = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", " ", s)
    try: return json.loads(s)
    except Exception: return json.loads(s.replace("'", '"'))

# ===== Публічне API =====
def gpt_autofill_metadata(
    api_key: str,
    base_prompt: str,
    extra_prompt: str,
    channel_theme: str,
    orig_title: str,
    orig_desc: str,
    tags_count: int,
    hashtags_count: int,
    desc_chars: int,
    remove_years: bool,
    source_tags=None
):
    """
    return: (title, description, tags_ignored, hashtags_list, keywords_string)
    """
    source_tags = [(" ".join(str(t).split())).strip(",;# ") for t in (source_tags or []) if (" ".join(str(t).split())).strip(",;# ")]
    seed_preview = ", ".join(source_tags[:30]) if source_tags else "—"

    cfg = _detect_config(channel_theme); style = _rotate_style()
    ns, recent = cfg["ns"], _recent_titles(cfg["ns"])[:RECENT_LIMIT]

    system = (base_prompt or "").strip() or "You are a professional YouTube metadata writer for music channels. Return strict JSON."
    system += (
        "\n\nHARD VALIDATION:\n"
        "- Title: <=98 chars; unique vs recent (per channel); optionally ONE emoji (configurable).\n"
        "- No years 2024/2025. No words: unlock, secrets, magic.\n"
        "- Description (4–5 short paragraphs):\n"
        "  1) **Hook** with one emoji; vivid image; no clichés.\n"
        "  2) Musical details (instruments, arrangement, energy curve).\n"
        "  3) Story/scene (place, time, textures — concrete nouns).\n"
        "  4) Soft SEO line with 2–3 keywords.\n"
        "  5) CTA: ask to SUBSCRIBE + like + 🔔.\n"
        "- No hashtags inside description (return them separately).\n"
        "- Output JSON only with keys: title, description, hashtags."
    )

    def _user(avoid: List[str]) -> str:
        avoid_block = "\n".join(f"- {t}" for t in avoid) if avoid else "—"
        emoji_line = "Emoji: OFF" if not cfg["require_emoji"] else f"Emoji set: {''.join(cfg['emoji_set'])[:10]}" 
        return f"""
CHANNEL THEME / PROMPT (use this; do NOT inject your own genre):
{(channel_theme or '').strip()}

STYLE FOR TITLE (rotates): {style}
{emoji_line}

AVOID SIMILARITY WITH THESE RECENT TITLES (same channel/profile):
{avoid_block}

ORIGINAL TITLE:
{(orig_title or '').strip()}

ORIGINAL DESCRIPTION (trimmed):
{(orig_desc or '').strip()[:4000]}

CONSTRAINTS:
- Target description length: {desc_chars} chars (±15%).
- Hashtags: exactly {hashtags_count}, all start with #; no duplicates; derive from theme & tags; no generic spam.
- Tags come from table; DO NOT invent tags. Seed tags for context: {seed_preview}

{(extra_prompt or '').strip()}

OUTPUT (strict JSON):
{{ "title": "...", "description": "...", "hashtags": "..." }}
""".strip()

    avoid, title, description, hashtags_raw = list(recent), "", "", ""
    for attempt in range(1, MAX_RETRIES + 1):
        data = _json_loose(_openai_chat(api_key,[{"role":"system","content":system},{"role":"user","content":_user(avoid)}],
                                        model="gpt-4o-mini", temperature=0.25, max_tokens=900))
        title = str(data.get("title","")).strip()
        description = str(data.get("description","")).strip()
        hashtags_raw = data.get("hashtags","")

        if not title: continue
        if any(w in title.lower() for w in BANNED_WORDS): continue
        if remove_years: title = re.sub(r"\(?20(2[4-5])\)?","",title).strip(" -•|.,")
        title = _enforce_title_rules(title, need_emoji=cfg["require_emoji"], emoji_set=cfg["emoji_set"])
        if any(_too_similar(o, title) for o in recent):
            avoid = (recent + [title])[-RECENT_LIMIT:]
            if attempt == MAX_RETRIES:
                title = _diversify_title(title, need_emoji=cfg["require_emoji"], emoji_set=cfg["emoji_set"]); break
            continue
        break

    _remember_title(ns, title)

    lang_hint = "en"  # default
    low_theme = (channel_theme or "").lower()
    if re.search(r"\b(ukrainian|українськ|укр)\b", low_theme):
        lang_hint = "uk"
    elif re.search(r"\b(russian|русский|російськ)\b", low_theme):
        lang_hint = "ru"
    elif re.search(r"\b(spanish|español|espanol)\b", low_theme):
        lang_hint = "es"
    elif re.search(r"\b(french|français|francais)\b", low_theme):
        lang_hint = "fr"
    elif re.search(r"\b(german|deutsch)\b", low_theme):
        lang_hint = "de"
    elif re.search(r"\b(portuguese|português|portugues)\b", low_theme):
        lang_hint = "pt"
    elif re.search(r"\b(italian|italiano)\b", low_theme):
        lang_hint = "it"
    elif re.search(r"\b(polish|polski)\b", low_theme):
        lang_hint = "pl"
    elif re.search(r"\b(dutch|nederlands)\b", low_theme):
        lang_hint = "nl"
    elif re.search(r"\b(turkish|türkçe)\b", low_theme):
        lang_hint = "tr"
    elif re.search(r"\b(japanese|日本語)\b", low_theme):
        lang_hint = "ja"
    elif re.search(r"\b(korean|한국어)\b", low_theme):
        lang_hint = "ko"
    elif re.search(r"\b(chinese|中文)\b", low_theme):
        lang_hint = "zh"
    elif re.search(r"\b(arabic|عربي)\b", low_theme):
        lang_hint = "ar"
    elif re.search(r"\b(hindi|हिन्दी)\b", low_theme):
        lang_hint = "hi"

    seeds = (cfg["seed"] or []) + (source_tags or [])
    description = _validate_description(description, seeds=seeds, emoji_set=cfg["emoji_set"], lang_hint=lang_hint)

    def _parse_hashtags(raw, want: int, seeds: List[str]) -> List[str]:
        parts = re.findall(r"#?[A-Za-z0-9_]+", raw) if isinstance(raw,str) else sum([re.findall(r"#?[A-Za-z0-9_]+", str(x)) for x in (raw or []) if x is not None], [])
        seen, out = set(), []
        for h in parts:
            core = h.lstrip("#").replace("-", "_").lower().strip("_")
            if core and core not in seen:
                seen.add(core); out.append(core)
                if len(out) >= want: break
        i = 0
        while len(out) < want and i < len(seeds)*2:
            c = re.sub(r"[^a-z0-9_]", "", (seeds[i % max(1,len(seeds))] or "").lower())
            if c and c not in seen: seen.add(c); out.append(c)
            i += 1
        fallback = ["music","mix","playlist","session","live","set","vibes","sound","beats","atmosphere"]
        for f in fallback:
            if len(out) >= want: break
            if f not in seen: seen.add(f); out.append(f)
        return out[:want]

    hashtags = _parse_hashtags(hashtags_raw, hashtags_count, seeds=seeds)

    kw = ", ".join(source_tags)
    if len(kw) > 500:
        cut = kw[:500]; kw = cut[:cut.rfind(",")].strip() if "," in cut else cut.strip()

    return title, description, [], hashtags, kw
