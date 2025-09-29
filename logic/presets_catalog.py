# -*- coding: utf-8 -*-
"""
Каталог пресетів і превʼю для UI:
- 5 категорій × 20 пресетів: кодер, еквалайзер, сцена, перехід, ефект
- get_*_presets() -> list[dict]
- render_preset_preview(category, preset_id, W, H, out_path, cancel_cb=None) -> out_path
"""

from __future__ import annotations
import os, math, random, json, subprocess, tempfile
from typing import Dict, List, Tuple, Callable, Optional
import numpy as np
from PIL import Image, ImageFilter, ImageOps, ImageDraw

# ---------------------------
# КОДЕРИ (GPU/CPU) — 20
# ---------------------------
CODEC_PRESETS: List[Dict] = [
    # NVENC H.264 — 10 варіантів
    {"id":"nv_p1_hq",   "name":"NV p1 HQ",   "desc":"NVENC якість (CQ18, AQ, LA=32)", "encoder":"h264_nvenc",
     "params":{"preset":"p1","rc":"vbr","cq":18,"b":"18M","maxrate":"36M","bufsize":"72M","la":32,"aq":1,"aq_strength":12,"bf":3,"multipass":"fullres"}},
    {"id":"nv_p2",      "name":"NV p2",      "desc":"NVENC збалансовано (LA=24, AQ)", "encoder":"h264_nvenc",
     "params":{"preset":"p2","rc":"vbr","cq":19,"b":"16M","maxrate":"32M","bufsize":"64M","la":24,"aq":1,"aq_strength":10,"bf":2}},
    {"id":"nv_p3",      "name":"NV p3",      "desc":"NVENC швидше, LA=16",           "encoder":"h264_nvenc",
     "params":{"preset":"p3","rc":"vbr","cq":20,"b":"14M","maxrate":"28M","bufsize":"56M","la":16,"aq":1,"aq_strength":9,"bf":2}},
    {"id":"nv_p4_bal",  "name":"NV p4 Bal",  "desc":"NVENC баланс, LA=16, AQ",       "encoder":"h264_nvenc",
     "params":{"preset":"p4","rc":"vbr","cq":20,"b":"14M","maxrate":"28M","bufsize":"56M","la":16,"aq":1,"aq_strength":9,"bf":2}},
    {"id":"nv_p5",      "name":"NV p5",      "desc":"NVENC швидко (LA=8)",           "encoder":"h264_nvenc",
     "params":{"preset":"p5","rc":"vbr","cq":21,"b":"12M","maxrate":"24M","bufsize":"48M","la":8,"aq":1,"aq_strength":8,"bf":2}},
    {"id":"nv_p6",      "name":"NV p6",      "desc":"NVENC дуже швидко",             "encoder":"h264_nvenc",
     "params":{"preset":"p6","rc":"vbr","cq":22,"b":"10M","maxrate":"20M","bufsize":"40M","la":4,"aq":0,"bf":1}},
    {"id":"nv_p7_fast", "name":"NV p7 Fast", "desc":"NVENC макс. швидкість",         "encoder":"h264_nvenc",
     "params":{"preset":"p7","rc":"vbr","cq":23,"b":"10M","maxrate":"20M","bufsize":"40M","la":0,"aq":0,"bf":0}},
    {"id":"nv_qp0",     "name":"NV Lossless","desc":"NVENC без втрат (QP=0)",        "encoder":"h264_nvenc",
     "params":{"preset":"p2","rc":"constqp","qp":0,"bf":0}},
    {"id":"nv_hevc_p5", "name":"HEVC p5",    "desc":"NVENC HEVC баланс",             "encoder":"hevc_nvenc",
     "params":{"preset":"p5","rc":"vbr","cq":21,"b":"10M","maxrate":"20M","bufsize":"40M","bf":2}},
    {"id":"nv_hevc_p7", "name":"HEVC p7",    "desc":"NVENC HEVC швидкість",          "encoder":"hevc_nvenc",
     "params":{"preset":"p7","rc":"vbr","cq":23,"b":"8M","maxrate":"16M","bufsize":"32M","bf":1}},

    # Intel QSV — 4
    {"id":"qsv_bal",    "name":"QSV Bal",    "desc":"Intel QSV balanced + LA",       "encoder":"h264_qsv",
     "params":{"preset":"balanced","global_quality":20,"b":"16M","maxrate":"32M","bufsize":"64M","look_ahead":1,"la_depth":20,"bf":2}},
    {"id":"qsv_fast",   "name":"QSV Fast",   "desc":"Intel QSV швидко",              "encoder":"h264_qsv",
     "params":{"preset":"fast","global_quality":22,"b":"12M","maxrate":"24M","bufsize":"48M","bf":1}},
    {"id":"qsv_slow",   "name":"QSV Slow",   "desc":"Intel QSV якість",              "encoder":"h264_qsv",
     "params":{"preset":"slow","global_quality":18,"b":"18M","maxrate":"36M","bufsize":"72M","look_ahead":1,"la_depth":32,"bf":3}},
    {"id":"qsv_hevc",   "name":"QSV HEVC",   "desc":"Intel HEVC",                    "encoder":"hevc_qsv",
     "params":{"preset":"balanced","global_quality":22,"b":"10M","maxrate":"20M","bufsize":"40M","bf":2}},

    # AMD AMF — 3
    {"id":"amf_bal",    "name":"AMF Bal",    "desc":"AMD AMF баланс",                "encoder":"h264_amf",
     "params":{"quality":"balanced","rc":"cqp","qp_i":18,"qp_p":18,"b":"16M","maxrate":"32M","bufsize":"64M","bf":2}},
    {"id":"amf_fast",   "name":"AMF Fast",   "desc":"AMD AMF швидко",                 "encoder":"h264_amf",
     "params":{"quality":"speed","rc":"cqp","qp_i":20,"qp_p":20,"b":"12M","maxrate":"24M","bufsize":"48M","bf":1}},
    {"id":"amf_hq",     "name":"AMF HQ",     "desc":"AMD AMF якість",                 "encoder":"h264_amf",
     "params":{"quality":"quality","rc":"cqp","qp_i":18,"qp_p":18,"b":"18M","maxrate":"36M","bufsize":"72M","bf":3}},

    # CPU x264 — 3
    {"id":"x264_fast",  "name":"x264 Fast",  "desc":"CPU швидко (preset=fast)",      "encoder":"libx264",
     "params":{"preset":"fast","crf":20}},
    {"id":"x264_med",   "name":"x264 Med",   "desc":"CPU баланс (preset=medium)",    "encoder":"libx264",
     "params":{"preset":"medium","crf":19}},
    {"id":"x264_slow",  "name":"x264 Slow",  "desc":"CPU якість (preset=slow)",      "encoder":"libx264",
     "params":{"preset":"slow","crf":18}},
]

def get_codec_presets() -> List[Dict]:
    return CODEC_PRESETS[:]

# ---------------------------
# ЕКВАЛАЙЗЕРИ — 20
# ---------------------------
EQ_PRESETS: List[Dict] = [
    {"id":"bars_classic","name":"Bars Classic","desc":"класичні вертикальні смуги",
     "params":{"n_bars":96,"height":300,"attack":0.6,"decay":0.02,"gamma":1.0,"mirror":True,"color":(255,255,255)}},
    {"id":"bars_smooth","name":"Bars Smooth","desc":"плавний рух, мʼякий спад",
     "params":{"n_bars":96,"height":280,"attack":0.55,"decay":0.015,"gamma":0.95,"mirror":True,"color":(220,220,255)}},
    {"id":"neon","name":"Neon","desc":"яскраві неонові бари",
     "params":{"n_bars":96,"height":320,"attack":0.65,"decay":0.02,"gamma":1.05,"mirror":True,"color":(120,200,255)}},
    {"id":"mirror","name":"Mirror","desc":"дзеркально вгору/вниз",
     "params":{"n_bars":120,"height":300,"attack":0.6,"decay":0.02,"gamma":1.0,"mirror":True,"color":(240,240,240)}},
    {"id":"dense","name":"Dense","desc":"щільні, багато смуг",
     "params":{"n_bars":160,"height":260,"attack":0.55,"decay":0.02,"gamma":1.0,"mirror":True,"color":(230,230,230)}},
    {"id":"sharp","name":"Sharp","desc":"швидкий відгук",
     "params":{"n_bars":96,"height":300,"attack":0.7,"decay":0.018,"gamma":1.0,"mirror":True,"color":(255,255,255)}},
    {"id":"softglow","name":"SoftGlow","desc":"теплий відтінок",
     "params":{"n_bars":96,"height":300,"attack":0.6,"decay":0.02,"gamma":0.95,"mirror":True,"color":(255,190,140)}},
    {"id":"lowend","name":"LowEnd","desc":"акцент на бас",
     "params":{"n_bars":96,"height":300,"attack":0.6,"decay":0.02,"gamma":0.9,"mirror":True,"color":(255,230,180)}},
    {"id":"hiend","name":"HiEnd","desc":"акцент на верх",
     "params":{"n_bars":96,"height":280,"attack":0.6,"decay":0.02,"gamma":1.1,"mirror":True,"color":(200,220,255)}},
    {"id":"dots","name":"Dots","desc":"точки замість смуг",
     "params":{"n_bars":180,"height":220,"attack":0.6,"decay":0.02,"gamma":1.0,"mirror":True,"color":(255,255,255)}},
    {"id":"waveform","name":"Wave","desc":"хвильова форма",
     "params":{"n_bars":96,"height":260,"attack":0.6,"decay":0.02,"gamma":1.0,"mirror":False,"color":(255,255,255)}},
    {"id":"thick","name":"Thick","desc":"товсті смуги",
     "params":{"n_bars":64,"height":340,"attack":0.6,"decay":0.02,"gamma":1.0,"mirror":True,"color":(255,255,255)}},
    {"id":"thin","name":"Thin","desc":"тонкі смуги",
     "params":{"n_bars":192,"height":240,"attack":0.55,"decay":0.02,"gamma":1.0,"mirror":True,"color":(255,255,255)}},
    {"id":"pulse","name":"Pulse","desc":"пульс під біт",
     "params":{"n_bars":96,"height":320,"attack":0.75,"decay":0.03,"gamma":1.0,"mirror":True,"color":(255,255,255)}},
    {"id":"rainbow","name":"Rainbow","desc":"веселковий",
     "params":{"n_bars":128,"height":280,"attack":0.6,"decay":0.02,"gamma":1.0,"mirror":True,"color":(255,255,255)}},
    {"id":"ice","name":"Ice","desc":"холодні кольори",
     "params":{"n_bars":96,"height":300,"attack":0.6,"decay":0.02,"gamma":1.0,"mirror":True,"color":(180,220,255)}},
    {"id":"fire","name":"Fire","desc":"теплі кольори",
     "params":{"n_bars":96,"height":300,"attack":0.6,"decay":0.02,"gamma":1.0,"mirror":True,"color":(255,160,100)}},
    {"id":"soft_decay","name":"SoftDecay","desc":"повільне згасання",
     "params":{"n_bars":96,"height":280,"attack":0.55,"decay":0.012,"gamma":1.0,"mirror":True,"color":(255,255,255)}},
    {"id":"fast_react","name":"FastReact","desc":"дуже швидкий відгук",
     "params":{"n_bars":96,"height":280,"attack":0.8,"decay":0.04,"gamma":1.0,"mirror":True,"color":(255,255,255)}},
    {"id":"mirror_glow","name":"MirrorGlow","desc":"дзеркало + легке світло",
     "params":{"n_bars":120,"height":300,"attack":0.6,"decay":0.02,"gamma":1.0,"mirror":True,"color":(255,245,230)}},
]

def get_eq_presets() -> List[Dict]:
    return EQ_PRESETS[:]

# ---------------------------
# СЦЕНИ — 20
# ---------------------------
SCENE_PRESETS: List[Dict] = [
    {"id":"kenburns","name":"KenBurns","desc":"повільне панорамування фото","params":{"type":"kenburns"}},
    {"id":"starfield","name":"Starfield","desc":"зоряне поле","params":{"type":"starfield"}},
    {"id":"soft_blur","name":"SoftBlur","desc":"мʼяке світіння","params":{"type":"soft_blur"}},
    {"id":"sunset","name":"Sunset","desc":"теплий градієнт","params":{"type":"gradient","colors":[(255,120,80),(50,10,30)]}},
    {"id":"night","name":"Night","desc":"холодний градієнт","params":{"type":"gradient","colors":[(20,40,70),(5,5,15)]}},
    {"id":"neon_grid","name":"NeonGrid","desc":"неонова сітка","params":{"type":"grid"}},
    {"id":"grain","name":"Grain","desc":"кінозерно","params":{"type":"grain"}},
    {"id":"bokeh","name":"Bokeh","desc":"боке вогні","params":{"type":"bokeh"}},
    {"id":"rays","name":"Rays","desc":"світлові промені","params":{"type":"rays"}},
    {"id":"aurora","name":"Aurora","desc":"північне сяйво","params":{"type":"aurora"}},
    {"id":"vhs","name":"VHS","desc":"сканлайни ретро","params":{"type":"vhs"}},
    {"id":"glitch","name":"Glitch","desc":"легкий глітч","params":{"type":"glitch"}},
    {"id":"fog","name":"Fog","desc":"туман","params":{"type":"fog"}},
    {"id":"noise","name":"Noise","desc":"шум текстура","params":{"type":"noise"}},
    {"id":"geo","name":"Geometry","desc":"геометричні фігури","params":{"type":"geo"}},
    {"id":"bars","name":"Bars","desc":"кіно-рамки (letterbox)","params":{"type":"letterbox"}},
    {"id":"mirror","name":"Mirror","desc":"дзеркальна симетрія","params":{"type":"mirror"}},
    {"id":"particles","name":"Particles","desc":"частинки","params":{"type":"particles"}},
    {"id":"wave","name":"Wave","desc":"хвильовий фон","params":{"type":"wave"}},
    {"id":"ripple","name":"Ripple","desc":"водяні кола","params":{"type":"ripple"}},
]

def get_scene_presets() -> List[Dict]:
    return SCENE_PRESETS[:]

# ---------------------------
# ПЕРЕХОДИ — 20
# ---------------------------
TRANSITION_PRESETS: List[Dict] = [
    {"id":"cross_smooth","name":"Crossfade","desc":"плавне змішування","params":{"type":"cross","dur":0.6}},
    {"id":"fade_black","name":"FadeBlack","desc":"в затемнення","params":{"type":"fade","to":"black","dur":0.5}},
    {"id":"fade_white","name":"FadeWhite","desc":"в біле","params":{"type":"fade","to":"white","dur":0.5}},
    {"id":"zoom_cut","name":"ZoomCut","desc":"збільшення + зріз","params":{"type":"zoom","dur":0.5}},
    {"id":"pan_cut","name":"PanCut","desc":"панорамний зріз","params":{"type":"pan","dur":0.5}},
    {"id":"slide_left","name":"SlideL","desc":"зсув ліворуч","params":{"type":"slide","dir":"left","dur":0.5}},
    {"id":"slide_right","name":"SlideR","desc":"зсув праворуч","params":{"type":"slide","dir":"right","dur":0.5}},
    {"id":"slide_up","name":"SlideUp","desc":"зсув вгору","params":{"type":"slide","dir":"up","dur":0.5}},
    {"id":"slide_down","name":"SlideDn","desc":"зсув вниз","params":{"type":"slide","dir":"down","dur":0.5}},
    {"id":"whip","name":"Whip","desc":"швидкий пан з розмиттям","params":{"type":"whip","dur":0.4}},
    {"id":"flash","name":"Flash","desc":"спалах","params":{"type":"flash","dur":0.2}},
    {"id":"wipe_h","name":"WipeH","desc":"шторка по X","params":{"type":"wipe","axis":"x","dur":0.5}},
    {"id":"wipe_v","name":"WipeV","desc":"шторка по Y","params":{"type":"wipe","axis":"y","dur":0.5}},
    {"id":"push","name":"Push","desc":"новий кадр тисне старий","params":{"type":"push","dur":0.5}},
    {"id":"page","name":"Page","desc":"перегортання сторінки","params":{"type":"page","dur":0.6}},
    {"id":"zoom_blur","name":"ZoomBlur","desc":"зум з розмиттям","params":{"type":"zoom_blur","dur":0.6}},
    {"id":"light_leak","name":"LightLeak","desc":"спалах світла","params":{"type":"leak","dur":0.4}},
    {"id":"ripple_t","name":"RippleTr","desc":"хвильовий перехід","params":{"type":"ripple","dur":0.6}},
    {"id":"cube","name":"Cube","desc":"3D куб","params":{"type":"cube","dur":0.7}},
    {"id":"split","name":"Split","desc":"розріз екрана","params":{"type":"split","dur":0.5}},
]

def get_transition_presets() -> List[Dict]:
    return TRANSITION_PRESETS[:]

# ---------------------------
# ЕФЕКТИ — 20
# ---------------------------
EFFECT_PRESETS: List[Dict] = [
    {"id":"grain","name":"Grain","desc":"кінозерно","params":{"type":"grain","amt":0.12}},
    {"id":"vignette","name":"Vignette","desc":"віньєтування","params":{"type":"vignette","strength":0.5}},
    {"id":"glow","name":"Glow","desc":"мʼяке світіння","params":{"type":"glow","radius":6}},
    {"id":"rays","name":"Rays","desc":"промені світла","params":{"type":"rays","strength":0.7}},
    {"id":"lens","name":"Lens","desc":"спотворення лінзи","params":{"type":"lens","strength":0.06}},
    {"id":"noise","name":"Noise","desc":"шум","params":{"type":"noise","amt":0.08}},
    {"id":"chroma","name":"ChromAb","desc":"хроматична аберація","params":{"type":"chroma","px":2}},
    {"id":"rgb_split","name":"RGB Split","desc":"зсув каналів","params":{"type":"rgb_split","px":2}},
    {"id":"scan","name":"Scanlines","desc":"VHS лінії","params":{"type":"scan","opacity":0.6}},
    {"id":"mblur","name":"MotionBlur","desc":"розмиття руху","params":{"type":"mblur","k":5}},
    {"id":"speed_ramp","name":"SpeedRamp","desc":"прискорення/сповільнення","params":{"type":"speed","x":1.2}},
    {"id":"fade_in","name":"FadeIn","desc":"плавна поява","params":{"type":"fade_in","sec":0.6}},
    {"id":"fade_out","name":"FadeOut","desc":"плавне зникання","params":{"type":"fade_out","sec":0.6}},
    {"id":"mirror","name":"Mirror","desc":"дзеркало","params":{"type":"mirror"}},
    {"id":"kaleido","name":"Kaleido","desc":"калейдоскоп","params":{"type":"kaleido","n":6}},
    {"id":"edges","name":"Edges","desc":"контури","params":{"type":"edges"}},
    {"id":"poster","name":"Posterize","desc":"постеризація","params":{"type":"poster","levels":5}},
    {"id":"sepia","name":"Sepia","desc":"сепія","params":{"type":"sepia"}},
    {"id":"bw","name":"B/W","desc":"ч/б контраст","params":{"type":"bw"}},
    {"id":"warm","name":"Warm","desc":"теплий тон","params":{"type":"warm"}},
]

def get_effect_presets() -> List[Dict]:
    return EFFECT_PRESETS[:]

# ------------------------------------------------------------
# ПРЕВʼЮ (реальний кадр) — швидке, без сторонніх файлів
# ------------------------------------------------------------

def _grad(W,H,c1,c2):
    img = Image.new("RGB",(W,H),c1)
    top = np.array(c1, np.float32); bot = np.array(c2, np.float32)
    arr = np.zeros((H,W,3), np.uint8)
    for y in range(H):
        t = y/(H-1)
        col = (top*(1-t)+bot*t).astype(np.uint8)
        arr[y,:] = col
    return Image.fromarray(arr)

def _draw_bars(W,H,params):
    n = params["n_bars"]; height = params["height"]; color = tuple(params["color"])
    img = Image.new("RGB",(W,H),(10,10,14))
    draw = ImageDraw.Draw(img)
    mid = H//2; step = max(1, W//n)
    rng = random.Random(123)
    for i in range(n):
        v = rng.random()
        h = int(v*height)
        x = int((i+0.5)*step)
        draw.rectangle([x-2, mid-h, x+2, mid], fill=color)
        if params.get("mirror",True):
            draw.rectangle([x-2, mid, x+2, min(H-1, mid+h)], fill=color)
    return img

def render_preset_preview(category: str, preset_id: str, W: int, H: int, out_path: str,
                          cancel_cb: Optional[Callable[[],bool]] = None) -> str:
    """
    Створює PNG превʼю під категорію/пресет. Жодних заглушок:
    сцену малюємо реально; еквалайзер — реальні бари; ефекти — реально накладаються.
    """
    category = category.lower()
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

    if category == "codec":
        # візуальне уявлення “навантаження/якість”
        pr = next(p for p in CODEC_PRESETS if p["id"]==preset_id)
        base = _grad(W,H,(30,30,32),(10,10,12))
        draw = ImageDraw.Draw(base)
        txt = f'{pr["name"]}\n{pr["desc"]}'
        draw.text((24,24), txt, fill=(230,230,230))
        base.save(out_path); return out_path

    if category == "eq":
        pr = next(p for p in EQ_PRESETS if p["id"]==preset_id)
        img = _draw_bars(W,H,pr["params"])
        img.save(out_path); return out_path

    if category == "scene":
        pr = next(p for p in SCENE_PRESETS if p["id"]==preset_id)
        t = pr["params"]["type"]
        if t == "gradient":
            c1, c2 = pr["params"]["colors"]
            img = _grad(W,H,c1,c2)
        elif t == "soft_blur":
            img = _grad(W,H,(60,40,80),(10,10,20)).filter(ImageFilter.GaussianBlur(8))
        elif t == "starfield":
            img = _grad(W,H,(5,5,10),(0,0,0))
            draw = ImageDraw.Draw(img)
            rng = random.Random(42)
            for _ in range(800):
                x = rng.randrange(W); y = rng.randrange(H); r = rng.choice([1,1,1,2])
                draw.ellipse([x-r,y-r,x+r,y+r], fill=(220,220,220))
        elif t == "grid":
            img = _grad(W,H,(8,12,20),(3,5,10))
            draw = ImageDraw.Draw(img)
            for x in range(0,W,40): draw.line([(x,0),(x,H)], fill=(0,180,255), width=1)
            for y in range(0,H,40): draw.line([(0,y),(W,y)], fill=(0,180,255), width=1)
        elif t == "grain":
            img = _grad(W,H,(20,20,20),(10,10,10))
            arr = np.array(img, np.uint8)
            noise = np.random.randint(0,30,(H,W,1),dtype=np.uint8)
            arr = np.clip(arr + noise, 0,255).astype(np.uint8)
            img = Image.fromarray(arr)
        else:
            img = _grad(W,H,(16,16,20),(6,6,10))
        img.save(out_path); return out_path

    if category == "transition":
        pr = next(p for p in TRANSITION_PRESETS if p["id"]==preset_id)
        img = _grad(W,H,(20,20,24),(6,6,10))
        draw = ImageDraw.Draw(img)
        # просте граф. пояснення напрямку/типу
        draw.rectangle([0,0,W//2,H], fill=(60,60,80))
        draw.rectangle([W//2,0,W,H], fill=(30,30,40))
        draw.text((24,24), pr["name"], fill=(230,230,230))
        draw.text((24,56), pr["desc"], fill=(200,200,200))
        img.save(out_path); return out_path

    if category == "effect":
        pr = next(p for p in EFFECT_PRESETS if p["id"]==preset_id)
        img = _grad(W,H,(40,40,48),(10,10,12))
        # застосуємо реальний ефект до градієнта
        t = pr["params"]["type"]
        if t == "vignette":
            m = Image.new("L",(W,H),0); d=ImageDraw.Draw(m)
            d.ellipse([-W*0.2,-H*0.2,W*1.2,H*1.2], fill=255)
            m = m.filter(ImageFilter.GaussianBlur(60))
            img = Image.composite(img, Image.new("RGB",(W,H),(0,0,0)), ImageOps.invert(m))
        elif t == "grain":
            arr = np.array(img, np.uint8)
            noise = np.random.randint(0,30,(H,W,1),dtype=np.uint8)
            arr = np.clip(arr + noise, 0,255).astype(np.uint8)
            img = Image.fromarray(arr)
        elif t == "glow":
            img = Image.blend(img, img.filter(ImageFilter.GaussianBlur(8)), 0.35)
        elif t == "rays":
            img = img.filter(ImageFilter.GaussianBlur(12))
        elif t == "sepia":
            arr = np.array(img, np.uint8).astype(np.float32)
            r,g,b = arr[:,:,0],arr[:,:,1],arr[:,:,2]
            tr = (0.393*r + 0.769*g + 0.189*b).clip(0,255)
            tg = (0.349*r + 0.686*g + 0.168*b).clip(0,255)
            tb = (0.272*r + 0.534*g + 0.131*b).clip(0,255)
            img = Image.fromarray(np.stack([tr,tg,tb],axis=2).astype(np.uint8))
        elif t == "bw":
            img = ImageOps.grayscale(img).convert("RGB")
        img.save(out_path); return out_path

    raise ValueError(f"Unknown category: {category}")
