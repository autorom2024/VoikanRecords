# -*- coding: utf-8 -*-
"""
Imagen 4 (Vertex) — генерація + ідейний двигун (Gemini / OpenAI / локальний).
- Поле OpenAI API Key з UI або змінна середовища OPENAI_API_KEY.
- Якщо обрано OpenAI, але бібліотеки нема/ключа нема — автоматично фолбек на локальний генератор ідей (лог попередить).
- Усе інше (2K, backoff, prompts_used.txt, ідеї тільки) — як у попередній версії.
"""

from __future__ import annotations
import os
import io
import re
import json
import time
import random
import difflib
from typing import List, Optional, Callable, Dict, Any, Tuple

from google import genai
from google.genai import types
from PIL import Image

# ---- Моделі/можливості ----
MODEL_CAPS: Dict[str, Dict[str, object]] = {
    "imagen-4.0-generate-001": {
        "display": "Imagen 4",
        "aspects": ["1:1", "3:4", "4:3", "9:16", "16:9"],
        "qualities": ["1K", "2K"],
        "per_call_max": 4,
    },
    "imagen-4.0-ultra-generate-001": {
        "display": "Imagen 4 Ultra",
        "aspects": ["1:1", "3:4", "4:3", "9:16", "16:9"],
        "qualities": ["1K", "2K"],
        "per_call_max": 4,
    },
}

PIXELS_1K = {
    "1:1": (1024, 1024),  "3:4": (896, 1280),  "4:3": (1280, 896),
    "9:16": (768, 1408),  "16:9": (1408, 768)
}
PIXELS_2K = {
    "1:1": (2048, 2048),  "3:4": (1792, 2560), "4:3": (2560, 1792),
    "9:16": (1536, 2816), "16:9": (2816, 1536)
}

def _target_dims(quality: str, aspect: str) -> Tuple[int, int]:
    if quality == "2K":
        return PIXELS_2K.get(aspect, (2048, 2048))
    return PIXELS_1K.get(aspect, (1024, 1024))

# -------------------- Службові --------------------

def _read_johnson(path: Optional[str]) -> dict:
    if not path:
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _ensure_adc_env(key_file: Optional[str], project: Optional[str], location: Optional[str]) -> None:
    if key_file and os.path.exists(key_file):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = key_file
    if project:
        os.environ["GOOGLE_CLOUD_PROJECT"] = project
    if location:
        os.environ["GOOGLE_CLOUD_LOCATION"] = location
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "true"

def _make_client(key_file: Optional[str], location: Optional[str] = None) -> genai.Client:
    j = _read_johnson(key_file)
    project = j.get("project") or j.get("project_id") or j.get("gcp_project") or os.getenv("GOOGLE_CLOUD_PROJECT")
    loc = j.get("location") or j.get("region") or location or os.getenv("GOOGLE_CLOUD_LOCATION") or "us-central1"
    if not project:
        raise RuntimeError("Johnson.json не містить 'project', і змінна середовища GOOGLE_CLOUD_PROJECT не задана.")
    _ensure_adc_env(key_file, project, loc)
    http_options = types.HttpOptions(api_version="v1")
    return genai.Client(vertexai=True, project=project, location=loc, http_options=http_options)

def list_models_and_caps(key_file: Optional[str], location: Optional[str] = None) -> dict:
    client = _make_client(key_file, location)
    available = set()
    try:
        for m in client.models.list():
            mid = getattr(m, "name", None) or getattr(m, "id", None) or str(m)
            if not mid:
                continue
            if "/" in mid:
                mid = mid.split("/")[-1]
            if mid in MODEL_CAPS:
                available.add(mid)
    except Exception:
        available = set(MODEL_CAPS.keys())

    models = [{"id": mid, "display": MODEL_CAPS[mid]["display"]} for mid in MODEL_CAPS if mid in available] \
             or [{"id": mid, "display": MODEL_CAPS[mid]["display"]} for mid in MODEL_CAPS]

    caps = {
        mid: {
            "aspects": MODEL_CAPS[mid]["aspects"],
            "qualities": MODEL_CAPS[mid]["qualities"],
            "per_call_max": MODEL_CAPS[mid]["per_call_max"],
        } for mid in MODEL_CAPS
    }
    return {"models": models, "caps": caps}

# -------------------- Байти → PIL --------------------

def _gen_image_to_pil(g) -> Optional[Image.Image]:
    img_obj = getattr(g, "image", None)
    if img_obj is not None and hasattr(img_obj, "image_bytes") and img_obj.image_bytes:
        return Image.open(io.BytesIO(img_obj.image_bytes))
    if img_obj is not None and hasattr(img_obj, "bytes") and img_obj.bytes:
        return Image.open(io.BytesIO(img_obj.bytes))
    by = getattr(g, "bytes", None)
    if by:
        return Image.open(io.BytesIO(by))
    if isinstance(img_obj, Image.Image):
        return img_obj
    return None

# -------------------- Детекції полів --------------------

def _gifields() -> set:
    fields = getattr(types.GenerateImagesConfig, "model_fields", None)
    if isinstance(fields, dict) and fields:
        return set(fields.keys())
    fields_v1 = getattr(types.GenerateImagesConfig, "__fields__", None)
    if isinstance(fields_v1, dict) and fields_v1:
        return set(fields_v1.keys())
    return set()

def _gcfields() -> set:
    fields = getattr(types.GenerateContentConfig, "model_fields", None)
    if isinstance(fields, dict) and fields:
        return set(fields.keys())
    fields_v1 = getattr(types.GenerateContentConfig, "__fields__", None)
    if isinstance(fields_v1, dict) and fields_v1:
        return set(fields_v1.keys())
    return set()

def _cfg_allowed(base: dict, allowed: set, **kwargs) -> dict:
    cfg = dict(base)
    for k, v in kwargs.items():
        if k in allowed:
            cfg[k] = v
    return cfg

# -------------------- Backoff utils --------------------

def _sleep_backoff(attempt: int):
    base = min(5 * (2 ** (attempt - 1)), 60)  # до 60 сек
    jitter = random.uniform(0.2, 1.5)
    time.sleep(base + jitter)

def _with_backoff(call, status_q, what: str, max_retries: int = 5):
    for attempt in range(1, max_retries + 1):
        try:
            return call()
        except Exception as e:
            msg = str(e)
            if "RESOURCE_EXHAUSTED" in msg or "429" in msg:
                status_q.put({"msg": f"[Фото] ⏳ {what}: квота/ліміт (спроба {attempt}/{max_retries}). Чекаю backoff…"})
                _sleep_backoff(attempt)
                continue
            raise
    raise RuntimeError(f"{what}: вичерпано спроби (квоти не відновились)")

# -------------------- Upscale --------------------

def _try_vertex_upscale_x2(client: genai.Client, model_id: str, image_obj, mime: str, status_q):
    def _call1():
        cfg_cls = getattr(types, "UpscaleImageConfig", None)
        cfg = cfg_cls(include_rai_reason=True, output_mime_type=mime) if cfg_cls else None
        return client.models.upscale_image(model=model_id, image=image_obj, upscale_factor="x2", config=cfg)

    fn = getattr(client.models, "upscale_image", None)
    if callable(fn):
        try:
            resp = _with_backoff(_call1, status_q, "Upscale x2 (Vertex)")
            gens = getattr(resp, "generated_images", None) or []
            return gens[0] if gens else None
        except Exception as e:
            status_q.put({"msg": f"[Фото] ⚠ Vertex upscale_image x2 не вдався остаточно: {e}"})

    fn2 = getattr(client.models, "transform_image", None)
    if callable(fn2):
        try:
            resp = client.models.transform_image(model=model_id, image=image_obj, upscale_factor="x2")
            gens = getattr(resp, "generated_images", None) or []
            return gens[0] if gens else None
        except Exception as e:
            status_q.put({"msg": f"[Фото] ⚠ Vertex transform_image x2 не вдався: {e}"})
    return None

def _local_upscale_to(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    try:
        resample = Image.Resampling.LANCZOS
    except Exception:
        resample = Image.LANCZOS
    return img.resize((target_w, target_h), resample)

# -------------------- Ідейний двигун: утиліти --------------------

def _clean_one_line(s: str) -> str:
    import re as _re
    s = s.replace("\n", " ").replace("\r", " ")
    s = _re.sub(r"\s{2,}", " ", s).strip()
    return s.strip("«»\"'` ")

def _similar(a: str, b: str, thresh: float = 0.92) -> bool:
    try:
        return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio() >= thresh
    except Exception:
        return a == b

def _gencfg(temperature: float, top_p: float, top_k: int, seed: int):
    try:
        allowed = _gcfields()
        kwargs = {}
        if "temperature" in allowed: kwargs["temperature"] = float(temperature)
        if "top_p" in allowed:       kwargs["top_p"] = float(top_p)
        if "top_k" in allowed:       kwargs["top_k"] = int(top_k)
        if "random_seed" in allowed: kwargs["random_seed"] = int(seed)
        if "candidate_count" in allowed: kwargs["candidate_count"] = 1
        if "max_output_tokens" in allowed: kwargs["max_output_tokens"] = 256
        return types.GenerateContentConfig(**kwargs) if kwargs else None
    except Exception:
        return None

# ---- Gemini-варіанти ----
def _prompt_variant_gemini(base_prompt: str, theme: str, idx: int, client: genai.Client) -> str:
    base_prompt = _clean_one_line(base_prompt)
    theme = (theme or "").strip()
    try:
        cfg = _gencfg(temperature=1.35, top_p=0.95, top_k=40, seed=idx * 7777)
        instr = (
            "Переформулюй промт для генерації зображення, НЕ змінюючи суть і ключові обʼєкти. "
            "Додай малі стилістичні варіації (синоніми, перестановка частин), 1 РЯДОК без пояснень."
        )
        if theme:
            instr += f" У темі/настрої: «{theme}»."
        text = f"{instr}\n\nБазовий промт:\n{base_prompt}\n\nВаріація №{idx}:"
        if cfg is not None:
            resp = client.models.generate_content(model="gemini-1.5-flash", contents=text, config=cfg)
        else:
            resp = client.models.generate_content(model="gemini-1.5-flash", contents=text)
        out = _clean_one_line(getattr(resp, "text", "") or "")
        if not out or _similar(out, base_prompt):
            raise RuntimeError("Недостатня варіативність")
        return out
    except Exception:
        return _heuristic_variant(base_prompt, theme, idx)

# ---- OpenAI-варіанти ----
def _prompt_variant_openai(base_prompt: str, theme: str, idx: int, api_key: Optional[str], status_q) -> str:
    base_prompt = _clean_one_line(base_prompt)
    theme = (theme or "").strip()
    key = api_key or os.getenv("OPENAI_API_KEY")

    if not key:
        status_q.put({"msg": "[Фото] ⚠ OpenAI ключ не вказано (ні в полі, ні в ENV). Перехід на локальний генератор ідей."})
        return _heuristic_variant(base_prompt, theme, idx)

    # 1) Новий клієнт (openai>=1.0)
    try:
        from openai import OpenAI
        client = OpenAI(api_key=key)
        prompt = (
            "Rephrase the following image generation prompt WITHOUT changing its meaning or key objects. "
            "Use small stylistic variations (synonyms, clause reordering). "
            "Return EXACTLY one line, no explanations."
        )
        if theme:
            prompt += f" Blend in this theme/mood: '{theme}'."
        text = f"{prompt}\n\nBase prompt:\n{base_prompt}\n\nVariation #{idx}:"

        # seed підтримується в деяких версіях; якщо ні — просто ігнорується
        kwargs = {"temperature": 1.2}
        try:
            kwargs["seed"] = idx * 8881
        except Exception:
            pass

        resp = client.responses.create(
            model="gpt-4o-mini",
            input=text,
            **kwargs
        )
        out = _clean_one_line(getattr(resp, "output_text", "") or "")
        if not out or _similar(out, base_prompt):
            raise RuntimeError("Low variance (responses)")
        return out
    except ImportError:
        pass
    except Exception as e:
        status_q.put({"msg": f"[Фото] ⚠ OpenAI responses API: {e}. Спробую legacy ChatCompletion…"})
        # fallthrough → legacy

    # 2) Legacy (openai<=0.28)
    try:
        import openai  # type: ignore
        openai.api_key = key
        messages = [
            {"role": "system", "content": "You rephrase prompts without changing meaning."},
            {"role": "user", "content":
                f"Base: {base_prompt}\nTheme: {theme}\n"
                f"Rephrase as a single line, same meaning, slight stylistic variation. Variation #{idx}."}
        ]
        resp = openai.ChatCompletion.create(model="gpt-4o-mini", messages=messages, temperature=1.2)
        out = _clean_one_line(resp["choices"][0]["message"]["content"])
        if not out or _similar(out, base_prompt):
            raise RuntimeError("Low variance (chat.completions)")
        return out
    except Exception as e:
        status_q.put({"msg": f"[Фото] ⚠ OpenAI ChatCompletion: {e}. Перехід на локальний генератор ідей."})
        return _heuristic_variant(base_prompt, theme, idx)

# ---- Локальний перефраз ----
def _heuristic_variant(base_prompt: str, theme: str, idx: int) -> str:
    parts = [p.strip() for p in re.split(r"[;,.]|(\s-\s)", base_prompt) if p and p.strip() and p != " - "]
    random.seed(10_000 + idx)
    if len(parts) > 1:
        random.shuffle(parts)
    core = ", ".join(parts) if parts else base_prompt
    theme = (theme or "").strip()
    bag = [
        "кінематографічна композиція",
        "мʼяке освітлення",
        "виразна перспектива",
        "гармонійна палітра",
        "насичені текстури",
        "виразний контраст",
    ]
    extra = ", ".join(random.sample(bag, k=min(2, len(bag))))
    variant = f"{core}. {('Стиль/настрій: ' + theme + '. ') if theme else ''}{extra}"
    return _clean_one_line(variant)

def _make_ideas(client: genai.Client, base_prompt: str, theme: str, count: int,
                provider: str, status_q, openai_api_key: Optional[str]) -> List[str]:
    ideas = []
    seen = []
    for i in range(1, count + 1):
        if provider == "gemini":
            p = _prompt_variant_gemini(base_prompt, theme, i, client)
        elif provider == "openai":
            p = _prompt_variant_openai(base_prompt, theme, i, openai_api_key, status_q)
        else:
            p = _heuristic_variant(base_prompt, theme, i)

        # дедуплікація
        if any(_similar(p, s) for s in seen):
            p = _heuristic_variant(base_prompt, theme, i + 777_000)
        ideas.append(p)
        seen.append(p)
        status_q.put({"msg": f"[Фото] ✎ Варіація #{i}: {p[:180] + ('…' if len(p) > 180 else '')}"})
    return ideas

# -------------------- Основна генерація --------------------

def vertex_generate_images(
    prompts: List[str],
    key_file: str,
    outdir: str,
    batches: int,
    per_gen: int,
    quality: str,
    model: Optional[str],
    file_format: str,
    aspect: str,
    enhance: bool,
    cancel_event,
    status_q,
    preview_cb: Optional[Callable[[str], None]] = None,
    location: Optional[str] = None,
    *,
    autoprompt_enable: bool = False,
    autoprompt_theme: str = "",
    auto_count: int = 1,
    ideas_only: bool = False,
    ideas_provider: str = "gemini",  # "gemini" | "openai" | "local"
    openai_api_key: Optional[str] = None,
) -> int:
    os.makedirs(outdir, exist_ok=True)
    client = _make_client(key_file, location)

    model_id = model or "imagen-4.0-generate-001"
    if model_id not in MODEL_CAPS:
        model_id = "imagen-4.0-generate-001"

    caps = MODEL_CAPS[model_id]
    if aspect not in caps["aspects"]:
        raise ValueError(f"Непідтримуваний аспект '{aspect}' для {model_id}")
    if quality not in caps["qualities"]:
        status_q.put({"msg": f"[Фото] ⚠ Якість '{quality}' недоступна для {model_id}. Ставлю '1K'."})
        quality = "1K"

    per_gen = max(1, min(int(per_gen or 1), int(caps["per_call_max"])))
    auto_count = max(1, min(int(auto_count or 1), 500))

    fmt = (file_format or "png").lower()
    if fmt == "jpg":
        fmt = "jpeg"
    if fmt not in ("png", "jpeg", "webp"):
        fmt = "png"
    mime = f"image/{fmt}"

    supported = _gifields()
    supports_sample = "sample_image_size" in supported

    base_cfg = dict(
        number_of_images=per_gen,
        include_rai_reason=True,
        output_mime_type=mime,
        enhance_prompt=bool(enhance),
    )
    cfgs = []
    cfg1 = _cfg_allowed(base_cfg, supported, sample_image_size=quality, aspect_ratio=aspect)
    if cfg1 != base_cfg:
        cfgs.append(cfg1)
    cfg2 = _cfg_allowed(base_cfg, supported, aspect_ratio=aspect)
    if cfg2 != base_cfg:
        cfgs.append(cfg2)
    cfgs.append(base_cfg)

    total_saved = 0
    batches = max(1, int(batches or 1))

    for b in range(batches):
        for src_prompt in prompts:
            base_prompt = (src_prompt or "").strip()
            if not base_prompt:
                continue

            # --- зібрати ідеї --- #
            if autoprompt_enable or ideas_only:
                provider = ideas_provider if ideas_provider in ("gemini", "openai", "local") else "gemini"
                ideas = _make_ideas(client, base_prompt, (autoprompt_theme or "").strip(),
                                    auto_count, provider, status_q, openai_api_key)
            else:
                ideas = [base_prompt] * auto_count

            # --- тільки ідеї --- #
            if ideas_only:
                fpath = os.path.join(outdir, "prompts_used.txt")
                with open(fpath, "w", encoding="utf-8") as f:
                    for i, p in enumerate(ideas, 1):
                        f.write(f"{i:03d}: {p}\n")
                status_q.put({"msg": f"[Фото] 📝 Записано ідей: {len(ideas)} → {fpath}"})
                status_q.put({"msg": "[Фото] 🟢 Завершено"})
                return 0

            # --- рендер кожної варіації --- #
            for run, p in enumerate(ideas, start=1):
                if cancel_event and cancel_event.is_set():
                    status_q.put({"msg": "[Фото] ⏹ Зупинено користувачем."})
                    break

                status_q.put({"msg": f"[Фото] ▶ Генерація: {MODEL_CAPS[model_id]['display']} | {quality} | {aspect} | x{per_gen} | варіація #{run}"})

                resp, last_err = None, None
                for idx, cfg in enumerate(cfgs, start=1):
                    def _call():
                        return client.models.generate_images(model=model_id, prompt=p, config=types.GenerateImagesConfig(**cfg))
                    try:
                        resp = _with_backoff(_call, status_q, "Генерація зображень")
                        break
                    except Exception as e:
                        last_err = e
                        status_q.put({"msg": f"[Фото] ⚠ Конфіг {idx} не пройшов: {e}"})
                if resp is None:
                    status_q.put({"msg": f"[Фото] ❌ Vertex помилка (вичерпано всі варіанти): {last_err}"})
                    continue

                gens = getattr(resp, "generated_images", None) or []
                if not gens:
                    status_q.put({"msg": "[Фото] ⚠ Порожня відповідь: зображень немає."})
                    continue

                want_2k = (quality == "2K")
                target_w, target_h = _target_dims(quality, aspect)
                did_upscale_vertex = False

                if want_2k and not supports_sample:
                    status_q.put({"msg": "[Фото] ↑ Нам потрібен 2K, але SDK не знає sample_image_size → пробую Vertex Upscale x2..."})
                    upscaled = []
                    for g in gens:
                        def _call_up():
                            return _try_vertex_upscale_x2(client, model_id, g.image, mime, status_q)
                        ug = _with_backoff(_call_up, status_q, "Upscale x2 (Vertex)", max_retries=3)
                        upscaled.append(ug or g)
                        did_upscale_vertex = did_upscale_vertex or (ug is not None)
                    gens = upscaled

                ts = time.strftime("%Y%m%d_%H%M%S")
                saved_here = 0

                for i, g in enumerate(gens, start=1):
                    try:
                        pil_img = _gen_image_to_pil(g)
                        if pil_img is None:
                            status_q.put({"msg": f"[Фото] ⚠ Немає даних зображення #{i} (image_bytes)."})
                            continue

                        w, h = pil_img.size
                        if want_2k and (w, h) != (target_w, target_h):
                            if not did_upscale_vertex:
                                status_q.put({"msg": f"[Фото] ↑ Локальний Upscale x2 → {target_w}x{target_h} (LANCZOS)."})
                            pil_img = _local_upscale_to(pil_img, target_w, target_h)
                            w, h = pil_img.size

                        fname = f"img_b{b+1:02d}_r{run:03d}_{i}_{quality}_{aspect.replace(':','-')}_{w}x{h}_{ts}.png"
                        fpath = os.path.join(outdir, fname)
                        pil_img.save(fpath)
                        saved_here += 1
                        total_saved += 1

                        if saved_here == 1 and callable(preview_cb):
                            try:
                                preview_cb(fpath)
                            except Exception:
                                pass
                    except Exception as ie:
                        status_q.put({"msg": f"[Фото] ⚠ Помилка збереження #{i}: {ie}"})

                if saved_here:
                    status_q.put({"msg": f"[Фото] ✅ Збережено: {saved_here} ({quality}, {aspect})"})

    status_q.put({"msg": "[Фото] 🟢 Завершено"})
    return total_saved
