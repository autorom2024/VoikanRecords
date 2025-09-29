# -*- coding: utf-8 -*-
# ui/pages/gpt/gpt_translate_utils.py
#
# Чистий переклад існуючих метаданих (title, description, hashtags) без зміни структури
# Працює разом із gpt_generator_core.gpt_autofill_metadata

from __future__ import annotations
import re
from typing import List, Tuple

# Імпортуємо з core модулю, не змінюючи його
from gpt_generator_core import _openai_chat as _core_chat, _json_loose as _core_json

__all__ = [
    "gpt_translate_only",
    "gpt_translate_bundle",
]


def _translate_text(api_key: str, text: str, target_lang: str) -> str:
    """Переклад одного блоку тексту з вимогою повернути строгий JSON."""
    system = (
        f"You are a precise translator. Translate the user's text into {target_lang}. "
        "Do NOT add, remove, or rephrase ideas. Preserve line breaks, punctuation, emojis, markdown and spacing. "
        "Keep inline hashtags (#tag) and URLs unchanged. Return strict JSON: {\"text\": \"...\"}."
    )
    data = _core_json(_core_chat(
        api_key,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": text or ""},
        ],
        model="gpt-4o-mini",
        temperature=0.0,
        max_tokens=1800,
    ))
    return str(data.get("text", "")).strip()


def _normalize_hashtags(inp) -> List[str]:
    """Приводимо hashtags до уніфікованого списку без решітки (YouTube приймає unicode)."""
    if isinstance(inp, str):
        tokens = re.findall(r"#?([\w\d_]+)", inp, flags=re.UNICODE)
        return [t.strip("_").lower() for t in tokens if t]
    arr = []
    for h in (inp or []):
        h = str(h)
        m = re.findall(r"#?([\w\d_]+)", h, flags=re.UNICODE)
        if m:
            arr.append(m[0].strip("_").lower())
    # унікальні, в початковому порядку
    seen = set(); out = []
    for x in arr:
        if x and x not in seen:
            seen.add(x); out.append(x)
    return out


def gpt_translate_only(
    api_key: str,
    title: str,
    description: str,
    hashtags: List[str] | str,
    target_lang: str,
    *,
    keep_hashtags: bool = True,
    translate_hashtags: bool = False,
) -> Tuple[str, str, List[str]]:
    """
    Перекладає лише title та description у target_lang. Хештеги — залишає як є (за замовчуванням)
    або, якщо translate_hashtags=True, намагається перекласти кожен тег окремо (ретельно не змінюючи форму).
    Повертає: (translated_title, translated_description, hashtags_list)
    """
    translated_title = _translate_text(api_key, title or "", target_lang)
    translated_desc  = _translate_text(api_key, description or "", target_lang)

    tags_list = _normalize_hashtags(hashtags)

    if keep_hashtags:
        return translated_title, translated_desc, tags_list

    if translate_hashtags and tags_list:
        # Перекладаємо кожен тег окремо; зберігаємо як один токен без пробілів
        joined = "\n".join(f"#{t}" for t in tags_list)
        prompt = (
            f"Translate each hashtag into {target_lang}. Keep it one token without spaces; "
            "replace spaces with underscores if needed. Do not invent new tags. Return JSON: {\"tags\":[\"tag1\",...]}"
        )
        data = _core_json(_core_chat(
            api_key,
            messages=[{"role": "system", "content": prompt}, {"role": "user", "content": joined}],
            model="gpt-4o-mini", temperature=0.0, max_tokens=400,
        ))
        out = data.get("tags")
        if isinstance(out, list) and out:
            clean = []
            seen = set()
            for t in out:
                core = re.sub(r"[^\w\d_]+", "", str(t).lower())
                if core and core not in seen:
                    seen.add(core); clean.append(core)
            if clean:
                tags_list = clean

    return translated_title, translated_desc, tags_list


def gpt_translate_bundle(
    api_key: str,
    autofilled_tuple: Tuple[str, str, List[str], List[str], str],
    target_lang: str,
    *,
    keep_hashtags: bool = True,
    keep_keywords: bool = True,
) -> Tuple[str, str, List[str], List[str], str]:
    """
    Утиліта для результату gpt_autofill_metadata.
    Вхід: (title, description, tags_ignored, hashtags_list, keywords_string)
    Вихід: така сама п'ятірка, де title/description перекладені, а hashtags/keywords — скопійовані (за замовчуванням).
    """
    title, description, tags_ignored, hashtags_list, keywords_string = autofilled_tuple
    new_title, new_desc, new_hashtags = gpt_translate_only(
        api_key,
        title,
        description,
        hashtags_list,
        target_lang,
        keep_hashtags=keep_hashtags,
        translate_hashtags=False,
    )
    new_keywords = keywords_string if keep_keywords else keywords_string
    return new_title, new_desc, tags_ignored, new_hashtags, new_keywords
