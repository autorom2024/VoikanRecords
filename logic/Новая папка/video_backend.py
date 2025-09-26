# -*- coding: utf-8 -*-
from __future__ import annotations

"""
Video Backend (FFmpeg + optional CUDA), tidy and debug-friendly
- Deterministic order of songs (no random).
- Album mode: 1 background per album, N tracks in order; repeat/trim to album_sec.
- GPU path uses overlay_cuda; auto-detects available CUDA filters (scale_cuda vs scale_npp),
  otherwise falls back to CPU overlay or hwdownload safely.
- Minimal, clear logging (no sidebar deps).
- Includes lightweight self-tests that do not invoke ffmpeg.
"""

import os, time, signal, queue, threading, subprocess, json
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from pydub import AudioSegment

# ============================ CONSTANTS ============================
AUDIO_EXT = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}

CACHE_DIR = Path("_cache") / "video_ui"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# process registry
_PROCS: List[subprocess.Popen] = []
_PROCS_LOCK = threading.Lock()
_RUNNING = False
_STOP_ALL = False
_MANAGER_THREAD: Optional[threading.Thread] = None

_PROCESS_STATE_FILE = CACHE_DIR / "processing_state.json"
_REMAINING = 0
_REMAINING_LOCK = threading.Lock()

# ============================ UTILS ============================

def _ffmpeg() -> str:
    return "ffmpeg"


def _safe_int(v, d=0) -> int:
    try:
        return int(v)
    except Exception:
        return d


def _parse_res(txt: str) -> Tuple[int,int,int]:
    try:
        parts = txt.split()
        wh = next(p for p in parts if "x" in p)
        w, h = map(int, wh.split("x"))
        fps = int(next(p for p in parts if "fps" in p).replace("fps",""))
        return w, h, fps
    except Exception:
        return 1920, 1080, 30


def _list_files(root: str, exts: set[str]) -> List[Path]:
    if not root:
        return []
    p = Path(root)
    if not p.exists():
        return []
    out: List[Path] = []
    for r,_,files in os.walk(p):
        for f in files:
            if Path(f).suffix.lower() in exts:
                out.append(Path(r)/f)
    out.sort()
    return out


def _reg(p: subprocess.Popen):
    with _PROCS_LOCK:
        _PROCS.append(p)


def _unreg(p: subprocess.Popen):
    with _PROCS_LOCK:
        if p in _PROCS:
            _PROCS.remove(p)

# ============================ FFmpeg filter probing ============================
_FFMPEG_FILTERS: Optional[set] = None


def _probe_ffmpeg_filters(status_q=None) -> set:
    global _FFMPEG_FILTERS
    if _FFMPEG_FILTERS is not None:
        return _FFMPEG_FILTERS
    try:
        out = subprocess.run([_ffmpeg(), "-hide_banner", "-filters"], capture_output=True, text=True)
        txt = (out.stdout or "") + "\n" + (out.stderr or "")
        filters = set()
        for line in txt.splitlines():
            parts = (line.strip() or "").split()
            if len(parts) >= 2:
                filters.add(parts[1])
        _FFMPEG_FILTERS = filters
        if status_q is not None:
            try:
                status_q.put({"type": "log", "msg": f"[FF] CUDA avail: overlay_cuda={'overlay_cuda' in filters}, scale_cuda={'scale_cuda' in filters}, scale_npp={'scale_npp' in filters}, hwupload_cuda={'hwupload_cuda' in filters}"})
            except Exception:
                pass
        return filters
    except Exception:
        _FFMPEG_FILTERS = set()
        return _FFMPEG_FILTERS


def _choose_gpu_filters(status_q=None) -> Tuple[bool, Optional[str]]:
    """Return (overlay_ok, scale_filter_name or None)."""
    fs = _probe_ffmpeg_filters(status_q)
    overlay_ok = ("overlay_cuda" in fs) and ("hwupload_cuda" in fs)
    # prefer scale_cuda, then scale_npp; None if neither
    scale_f = "scale_cuda" if "scale_cuda" in fs else ("scale_npp" if "scale_npp" in fs else None)
    return overlay_ok, scale_f

# ============================ STATE MANAGEMENT ============================

def _load_processing_state() -> Dict:
    try:
        if _PROCESS_STATE_FILE.exists():
            with open(_PROCESS_STATE_FILE, 'r', encoding='utf-8') as f:
                obj = json.load(f)
                if isinstance(obj, dict):
                    obj.setdefault("processed_songs", [])
                    obj.setdefault("last_position", 0)
                    return obj
    except Exception:
        pass
    return {"processed_songs": [], "last_position": 0}


def _save_processing_state(state: Dict):
    try:
        with open(_PROCESS_STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _reset_processing_state():
    try:
        if _PROCESS_STATE_FILE.exists():
            _PROCESS_STATE_FILE.unlink()
    except Exception:
        pass

# ============================ STOP / KILL ============================

def stop_all_jobs():
    global _STOP_ALL, _RUNNING
    _STOP_ALL = True
    with _PROCS_LOCK:
        for p in list(_PROCS):
            try:
                if os.name == "nt":
                    subprocess.call(["taskkill","/F","/T","/PID",str(p.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    os.killpg(os.getpgid(p.pid), signal.SIGKILL)
            except Exception:
                pass
        _PROCS.clear()
    _RUNNING = False

# ============================ OPTIONAL Qt (PNG frames) ============================
_make_png = False
try:
    from PySide6.QtGui import QImage, QPainter, QColor, QBrush, QRadialGradient, QPen
    from PySide6.QtCore import Qt, QPoint
    _make_png = True
except Exception:
    _make_png = False


def _qcolor(hex_color: str) -> "QColor":
    try:
        return QColor(hex_color or "#FFFFFF")
    except Exception:
        from types import SimpleNamespace
        return SimpleNamespace(name=lambda: "#FFFFFF")  # minimal stub for non-Qt env


def _save_png(img: "QImage", path: Path) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        return img.save(str(path), "PNG")
    except Exception:
        return False

# ============================ EFFECTS ============================
class EffSeq:
    def __init__(self, nick: str, dir_frames: Path, fps: int):
        self.nick = nick
        self.dir  = dir_frames
        self.fps  = fps

# ---- stars / smoke / rain generators (unchanged logic, compact logging) ----

def _stars_sig(stars_ui: Dict, W:int,H:int,fps:int) -> str:
    cnt  = int(stars_ui.get("count",700))
    s0   = int(stars_ui.get("size",2))
    pulse= int(stars_ui.get("pulse",40))
    col  = _qcolor(stars_ui.get("color","#FFFFFF")).name().replace("#","")
    op   = int(max(0,min(100,int(stars_ui.get("opacity",85)))))
    return f"starsV3_{W}x{H}_f{fps}_n{cnt}_s{s0}_c{col}_o{op}_p{pulse}_L6"


def _build_stars_frames(stars_ui: Dict, W: int, H: int, fps: int, status_q) -> Optional[Path]:
    if not _make_png or not stars_ui.get("enabled", False): return None
    loop_sec = 6
    frames = fps*loop_sec
    cnt   = max(30, int(stars_ui.get("count", 700)))
    s0    = max(1,  int(stars_ui.get("size", 2)))
    pulse = max(0,  int(stars_ui.get("pulse", 40)))
    col   = _qcolor(stars_ui.get("color", "#FFFFFF"))
    opf   = max(0.05, min(1.0, int(stars_ui.get("opacity", 85))/100.0))
    ramp_in = float(stars_ui.get("intro_sec", 0.7))

    sig = _stars_sig(stars_ui,W,H,fps)
    frames_dir = (CACHE_DIR / f"seq_{sig}" / "frames")
    if (frames_dir/"f_0000.png").exists():
        try: status_q.put({"type":"log","msg":f"[BE] Stars cached: {frames_dir}"})
        except Exception: pass
        return frames_dir

    import random, math
    rnd = random.Random(0x51A2A5 ^ (W<<1) ^ (H<<2) ^ cnt)
    births = []
    for _ in range(cnt):
        x = rnd.randint(0,W-1); y = rnd.randint(0,H-1)
        size = s0 + rnd.randint(0, max(0, s0))
        life = rnd.uniform(0.8, 2.0)
        t0   = rnd.uniform(0.2, max(0.2, loop_sec - life))
        ph   = rnd.random()*2*math.pi
        births.append((x,y,size,t0,life,ph))

    frames_dir.mkdir(parents=True, exist_ok=True)
    for f in range(frames):
        t = f/fps
        img = QImage(W,H,QImage.Format_ARGB32_Premultiplied); img.fill(0)
        p = QPainter(img)
        try:
            p.setRenderHint(QPainter.Antialiasing, False)
            for (x,y,size,t0,life,ph) in births:
                if not (t0 <= t <= t0+life): continue
                import math
                lt = (t - t0) / life
                fade = math.sin(math.pi*lt)
                a_p = 0.5 + 0.5*math.sin(2*math.pi*(1.0/loop_sec)*t + ph)
                a_p = (1.0 - pulse/100.0) + (pulse/100.0)*a_p
                ramp = 1.0 if ramp_in<=0 else max(0.0, min(1.0, t / ramp_in))
                a = max(0.0, min(1.0, fade*a_p)) * opf * ramp
                if a <= 0.001:
                    continue
                qcol = QColor(col); qcol.setAlphaF(a)
                p.setPen(Qt.NoPen); p.setBrush(QBrush(qcol))
                s_pix = max(1, int(round(size * (0.6 + 0.4*ramp))))
                p.drawRect(x - s_pix//2, y - s_pix//2, s_pix, s_pix)
        finally:
            p.end()
        _save_png(img, frames_dir/f"f_{f:04d}.png")
    try: status_q.put({"type":"log","msg":f"[BE] Stars built: {frames_dir} ({frames}f)"})
    except Exception: pass
    return frames_dir


def _build_smoke_frames(sm_ui: Dict, W: int, H: int, fps: int, status_q) -> Optional[Path]:
    if not _make_png or not sm_ui.get("enabled", False): return None
    loop_sec=6; frames=fps*loop_sec
    density = max(30, int(sm_ui.get("density", 90)))
    col     = _qcolor(sm_ui.get("color", "#A0A0A0"))
    opf     = max(0.05, min(1.0, int(sm_ui.get("opacity", 40))/100.0))
    speed   = float(sm_ui.get("speed", 18.0))

    col_hex = col.name().replace("#","")
    frames_dir = (CACHE_DIR / f"seq_smokeV2_{W}x{H}_f{fps}_d{density}_c{col_hex}_o{int(opf*100)}_s{int(speed)}" / "frames")
    if (frames_dir/"f_0000.png").exists():
        try: status_q.put({"type":"log","msg":f"[BE] Smoke cached: {frames_dir}"})
        except Exception: pass
        return frames_dir

    import random, math
    rnd = random.Random(0xC0FFEE ^ (W<<1) ^ (H<<2) ^ density)
    puffs=[]
    for _ in range(density):
        x=rnd.randint(-W//4, W+W//4); y=rnd.randint(-H//4, H+H//4)
        r=rnd.randint(28,110); ang=rnd.random()*2*math.pi
        vx=math.cos(ang)*speed; vy=math.sin(ang)*(speed*0.5)
        ph=rnd.random()*2*math.pi
        puffs.append((x,y,r,vx,vy,ph))

    frames_dir.mkdir(parents=True, exist_ok=True)
    for f in range(frames):
        t=f/fps
        img = QImage(W,H,QImage.Format_ARGB32_Premultiplied); img.fill(0)
        p=QPainter(img)
        try:
            for (x0,y0,r,vx,vy,ph) in puffs:
                import math
                x = ((x0 + vx*t + 2*W) % (W+W//2)) - W//4
                y = ((y0 + vy*t + 2*H) % (H+H//2)) - H//4
                a = 0.55*(0.5+0.5*math.sin(2*math.pi*(1.0/loop_sec)*t+ph)) + 0.45
                a = min(1.0,max(0.0,a))*opf
                g = QRadialGradient(int(x),int(y),r)
                c1=QColor(col); c1.setAlphaF(a*0.35)
                c2=QColor(col); c2.setAlphaF(0.0)
                g.setColorAt(0.0,c1); g.setColorAt(1.0,c2)
                p.setBrush(QBrush(g)); p.setPen(Qt.NoPen)
                p.drawEllipse(QPoint(int(x),int(y)), r, r)
        finally:
            p.end()
        _save_png(img, frames_dir/f"f_{f:04d}.png")
    try: status_q.put({"type":"log","msg":f"[BE] Smoke built: {frames_dir} ({frames}f)"})
    except Exception: pass
    return frames_dir


def _build_rain_frames(rain_ui: Dict, W: int, H: int, fps: int, status_q) -> Optional[Path]:
    if not _make_png or not rain_ui.get("enabled", False): return None
    loop_sec=4; frames=fps*loop_sec
    cnt=max(200,int(rain_ui.get("count",1200)))
    L=max(5,int(rain_ui.get("length",40)))
    thick=max(1,int(rain_ui.get("thickness",2)))
    ang=float(rain_ui.get("angle_deg",15.0))
    speed=float(rain_ui.get("speed",160.0))
    col=_qcolor(rain_ui.get("color","#9BE2FF"))
    opf=max(0.05,min(1.0,int(rain_ui.get("opacity",55))/100.0))

    col_hex = col.name().replace("#","")
    frames_dir=(CACHE_DIR/f"seq_rainV2_{W}x{H}_f{fps}_n{cnt}_L{L}_th{thick}_a{int(ang)}_s{int(speed)}_c{col_hex}_o{int(opf*100)}"/"frames")
    if (frames_dir/"f_0000.png").exists():
        try: status_q.put({"type":"log","msg":f"[BE] Rain cached: {frames_dir}"})
        except Exception: pass
        return frames_dir

    import random, math
    rnd=random.Random(0x5151DEAD^(W<<1)^(H<<2))
    dx=int(L*math.cos(math.radians(ang))); dy=int(L*math.sin(math.radians(ang)))+1
    drops=[]
    for _ in range(cnt):
        x=rnd.randint(-W//2, W+W//2); y=rnd.randint(-H//2, H+H//2)
        v=speed*(0.7+0.6*rnd.random())
        drops.append((x,y,v))

    frames_dir.mkdir(parents=True, exist_ok=True)
    for f in range(frames):
        t=f/fps
        img = QImage(W,H,QImage.Format_ARGB32_Premultiplied); img.fill(0)
        p=QPainter(img)
        try:
            p.setRenderHint(QPainter.Antialiasing, True)
            c=QColor(col); c.setAlphaF(opf)
            pen=QPen(c, thick, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            p.setPen(pen)
            import math
            for (x0,y0,v) in drops:
                x=int(x0 + (v*math.cos(math.radians(ang)))*t)%(W+W//2)-W//4
                y=int(y0 + (v*math.sin(math.radians(ang)))*t)%(H+H//2)-H//4
                p.drawLine(x,y, x+dx, y+dy)
        finally:
            p.end()
        _save_png(img, frames_dir/f"f_{f:04d}.png")
    try: status_q.put({"type":"log","msg":f"[BE] Rain built: {frames_dir} ({frames}f)"})
    except Exception: pass
    return frames_dir


def _prepare_effect_sequences(cfg: Dict, W:int, H:int, fps:int, status_q) -> List[EffSeq]:
    out: List[EffSeq] = []
    st = cfg.get("stars_ui") or {}
    rn = cfg.get("rain_ui")  or {}
    sm = cfg.get("smoke_ui") or {}
    if st.get("enabled"):
        d=_build_stars_frames(st,W,H,fps,status_q); 
        if d: out.append(EffSeq("stars",d,fps))
    if rn.get("enabled"):
        d=_build_rain_frames(rn,W,H,fps,status_q);
        if d: out.append(EffSeq("rain",d,fps))
    if sm.get("enabled"):
        d=_build_smoke_frames(sm,W,H,fps,status_q);
        if d: out.append(EffSeq("smoke",d,fps))
    try: status_q.put({"type":"log","msg": "[BE] Effects: " + (", ".join(e.nick for e in out) if out else "none")})
    except Exception: pass
    return out

# ============================ FILTER CHAINS ============================

def _bg_chain(W:int,H:int,fps:int,has_bg:bool) -> Tuple[str,str]:
    if has_bg:
        return (f"[1:v]scale={W}:{H}:force_original_aspect_ratio=increase,"
                f"crop={W}:{H},fps={fps},format=rgba[bg_raw];"
                f"[bg_raw]setpts=PTS-STARTPTS[bg]", "[bg]")
    else:
        return (f"color=color=black:size={W}x{H}:rate={fps},format=rgba[bg]", "[bg]")


def _motion_chain(mv: Dict, W:int,H:int,fps:int) -> Tuple[str,str]:
    if not mv or not mv.get("enabled", False): return "", "[bg]"
    direction = str(mv.get("direction","lr"))
    amount    = float(mv.get("amount",20.0))
    speed     = float(mv.get("speed",40.0))
    rot_deg   = float(mv.get("rot_deg",8.0))
    rot_hz    = float(mv.get("rot_hz",0.1))
    shake_px  = float(mv.get("shake_px",6.0))
    shake_hz  = float(mv.get("shake_hz",1.2))

    parts=[f"[bg]scale=round({W}*{1.0 + min(0.50, amount/200.0)}):round({H}*{1.0 + min(0.50, amount/200.0)}):flags=bicubic[bg_s]"]
    out_tag="[bgm]"; hz=max(0.02, speed/200.0)

    if direction in ("lr","rl"):
        parts.append(f"[bg_s]crop={W}:{H}:x='(iw-{W})/2 + min((iw-{W})/2,{int(W*0.15+amount*1.5)})*{('-' if direction=='rl' else '')}sin(2*PI*{hz}*t)':y='(ih-{H})/2',format=rgba{out_tag}")
    elif direction in ("up","down"):
        parts.append(f"[bg_s]crop={W}:{H}:x='(iw-{W})/2':y='(ih-{H})/2 + min((ih-{H})/2,{int(H*0.15+amount*1.5)})*{('' if direction=='down' else '-') }sin(2*PI*{hz}*t)',format=rgba{out_tag}")
    elif direction in ("zin","zout"):
        amp=min(0.40, amount/100.0)*(1 if direction=="zin" else -1)
        parts.append(f"[bg_s]zoompan=z='1+{amp}*sin(2*PI*{max(0.02, speed/400.0)}*t)':x='(iw-iw/zoom)/2':y='(ih-ih/zoom)/2':d=1:fps={fps}:s={W}x{H},format=rgba{out_tag}")
    elif direction=="rotate":
        a= max(0.0, rot_deg)*3.14159265/180.0; hz_r=max(0.01,rot_hz)
        parts.append(f"[bg_s]rotate=a='{a}*sin(2*PI*{hz_r}*t)':fillcolor=black@1[bg_r];[bg_r]crop={W}:{H}:x='(iw-{W})/2':y='(ih-{H})/2',format=rgba{out_tag}")
    elif direction=="shake":
        px=max(1.0,shake_px); hz_s=max(0.05,shake_hz)
        parts.append(f"[bg_s]crop={W}:{H}:x='(iw-{W})/2 + {px}*sin(2*PI*{hz_s}*t)':y='(ih-{H})/2 + {px}*cos(2*PI*{hz_s}*t)',format=rgba{out_tag}")
    else:
        return "", "[bg]"
    return ";".join(parts), out_tag


def _eq_chain(eq: Dict, W:int, H:int) -> Tuple[str,int,int,bool,str,str]:
    import math
    mode_ui = str(eq.get("mode","bar")).lower()
    mirror  = bool(eq.get("mirror", True))
    fullscreen = bool(eq.get("fullscreen", False))
    yofs    = _safe_int(eq.get("y_offset",0),0)
    height  = _safe_int(eq.get("height", H//2), H//2)
    bars    = max(8, min(256, _safe_int(eq.get("bars",96),96)))

    hexc = (eq.get("color","#FFFFFF") or "#FFFFFF").upper().strip()
    def _rgb01(h:str)->Tuple[float,float,float]:
        s = h.lstrip("#")
        if len(s)==3: s="".join(c*2 for c in s)
        try:
            return int(s[0:2],16)/255.0, int(s[2:4],16)/255.0, int(s[4:6],16)/255.0
        except Exception:
            return 1.0,1.0,1.0
    r,g,b = _rgb01(hexc)
    opacity = max(0,min(100,_safe_int(eq.get("opacity",90),90)))/100.0

    ws = max(256, min(16384, 2 ** int(round(math.log2(bars*32)))))

    if mirror:
        eq_h = H//2 if fullscreen else max(40, min(H//2, height))
        baseline = int(H*(0.5 + yofs/200.0))
        baseline = max(eq_h, min(H-eq_h, baseline))
        y_top = baseline - eq_h
    else:
        eq_h = H if fullscreen else max(40, min(H, height))
        y_top = int((H - eq_h) * (yofs + 100) / 200.0)
        y_top = max(0, min(H - eq_h, y_top))

    mode = "line" if mode_ui=="line" else "bar"
    gen = (f"[0:a]aresample=async=1:first_pts=0,asetpts=PTS-STARTPTS[audsrc];"
           f"[audsrc]showfreqs=size={W}x{eq_h}:mode={mode}:fscale=log:win_size={ws}:colors=white,"
           f"format=rgba,colorchannelmixer=rr={r:.3f}:gg={g:.3f}:bb={b:.3f}:aa={opacity:.3f}[eq_wave]")
    gen += ";[eq_wave]format=rgba[eq_up]"

    if mirror:
        gen += ";[eq_up]split=2[eq_u1][eq_u2];[eq_u2]vflip,format=rgba[eq_dn]"
        return gen, eq_h, y_top, True, "[eq_u1]", "[eq_dn]"
    else:
        return gen, eq_h, y_top, False, "[eq_up]", ""

# ============================ FFMPEG COMMAND ============================

def _ffmpeg_cmd_single(cfg: Dict, song: Path, bg_img: Optional[Path], out_path: Path,
                       status_q: "queue.Queue[dict]") -> Tuple[List[str], str]:
    W,H,fps = _parse_res(cfg.get("resolution","1920x1080 30fps"))
    gpu = (cfg.get("gpu","auto") or "auto").lower()
    preset = cfg.get("gpu_preset","auto/balanced")
    threads=_safe_int(cfg.get("threads",16),16)
    verbose = bool(cfg.get("verbose", False))

    # tentatively decide CUDA path availability (final decision after we know overlays)
    use_cuda_fx = (gpu in ("nvidia","auto")) and bool(cfg.get("gpu_effects", True))
    overlay_ok, scale_f = _choose_gpu_filters(status_q) if use_cuda_fx else (False, None)
    if use_cuda_fx and not overlay_ok:
        use_cuda_fx = False  # no overlay_cuda/hwupload_cuda → CPU path

    # base args
    args=[_ffmpeg(),"-y","-hide_banner","-stats","-loglevel","error" if not verbose else "info"]

    # inputs
    album_enabled = bool(cfg.get("album_enabled", False))
    album_sec = _safe_int(cfg.get("album_sec", 0), 0)
    album_combined = bool(cfg.get("album_combined", False))

    if album_enabled and album_sec>0 and not album_combined:
        args += ["-stream_loop","-1","-i",str(song)]
    else:
        args += ["-i",str(song)]

    has_bg = bool(bg_img and bg_img.exists())
    if has_bg:
        args += ["-loop","1","-framerate",str(fps),"-i",str(bg_img)]

    # effects frames
    effs = _prepare_effect_sequences(cfg, W,H,fps,status_q)

    # Decision: alpha overlays (EQ/PNG) are more stable on CPU. overlay_cuda often lacks alpha support.
    needs_alpha = True  # EQ always generates RGBA with alpha; PNG effects too
    if needs_alpha and use_cuda_fx:
        use_cuda_fx = False
        try:
            status_q.put({"type":"log","msg":"[CFG] CUDA overlay disabled (alpha composition on CPU for stability)"})
        except Exception:
            pass

    # Late init CUDA device only if we really use CUDA filters
    if use_cuda_fx:
        args += ["-init_hw_device","cuda=cuda:0","-filter_hw_device","cuda","-hwaccel","cuda","-hwaccel_output_format","cuda"]

    for e in effs:
        args += ["-stream_loop","-1","-framerate",str(e.fps),"-f","image2","-i", str(e.dir/"f_%04d.png")]

    try:
        status_q.put({"type":"log","msg":f"[CFG] GPU={gpu}, preset={preset}, threads={threads}, cuda_fx={use_cuda_fx} (scale={scale_f or '—'})"})
    except Exception:
        pass

    # build filter_complex
    fparts: List[str] = []

    # background (CPU)
    bg_decl,bg_tag = _bg_chain(W,H,fps,has_bg); fparts.append(bg_decl)
    mv_txt, bg_after = _motion_chain(cfg.get("motion_ui") or {}, W,H,fps)
    if mv_txt:
        fparts.append(mv_txt); bg_after = "[bgm]"
    else:
        bg_after = bg_tag

    # EQ chain (produces [eq_up] and optionally [eq_dn])
    eq_txt, eq_h, y_top, mirror, tag_up, tag_dn = _eq_chain(cfg.get("eq_ui") or {}, W,H)
    fparts.append(eq_txt)

    if use_cuda_fx:
        # upload to GPU
        fparts.append(f"{bg_after}format=rgba,hwupload_cuda[bg_gpu]")
        fparts.append(f"{tag_up}format=rgba,hwupload_cuda[eq_up_gpu]")
        up_tag = "[eq_up_gpu]"; dn_tag = ""
        if mirror and tag_dn:
            fparts.append(f"{tag_dn}format=rgba,hwupload_cuda[eq_dn_gpu]")
            dn_tag = "[eq_dn_gpu]"

        # overlay top (GPU)
        fparts.append(f"[bg_gpu]{up_tag}overlay_cuda=x=0:y={y_top}[v1g]")
        last = "[v1g]"
        if mirror and dn_tag:
            fparts.append(f"{last}{dn_tag}overlay_cuda=x=0:y={y_top+eq_h}[v2g]")
            last = "[v2g]"

        # effects on GPU
        base_idx = 2 if has_bg else 1
        for i,_e in enumerate(effs):
            idx = base_idx + i
            fparts.append(f"[{idx}:v]format=rgba,hwupload_cuda[fx{idx}]")
            fparts.append(f"{last}[fx{idx}]overlay_cuda=x=0:y=0[v{idx}g]")
            last = f"[v{idx}g]"

        # finalize: prefer GPU scale if present, else hwdownload to CPU
        if scale_f:
            fparts.append(f"{last}{scale_f}=w={W}:h={H}:format=nv12[vout]")
        else:
            fparts.append(f"{last}hwdownload,format=yuv420p[vout]")
    else:
        # CPU overlays (support alpha properly)
        fparts.append(f"{bg_after}{tag_up}overlay=x=0:y={y_top}:shortest=1,format=rgba[v1]")
        last="[v1]"
        if mirror and tag_dn:
            fparts.append(f"{last}{tag_dn}overlay=x=0:y={y_top+eq_h}:shortest=1,format=rgba[v2]")
            last="[v2]"
        base_idx = 2 if has_bg else 1
        for i,e in enumerate(effs):
            idx = base_idx + i
            fparts.append(f"{last}[{idx}:v]overlay=x=0:y=0:shortest=1,format=rgba[v_{e.nick}]")
            last = f"[v_{e.nick}]"
        fparts.append(f"{last}scale={W}:{H},fps={fps},format=yuv420p[vout]")

    filter_complex = ";".join(fparts)

    # video codec
    def _choose_vcodec(gpu: str, preset: str, target_bps: int = 10_000_000) -> Tuple[str, List[str]]:
        pmap = {"p1":"p1","p2":"p2","p3":"p3","p4":"p4","p5":"p5","p6":"p6","p7(quality)":"p7","auto/balanced":"p5"}
        nv_preset = pmap.get(preset, "p5")
        vb = str(target_bps); mr = str(int(target_bps*1.3)); bs = str(target_bps*2)
        if gpu in ("nvidia","auto"):
            return "h264_nvenc", ["-preset", nv_preset, "-rc", "vbr_hq", "-b:v", vb, "-maxrate", mr, "-bufsize", bs]
        if gpu == "amd":
            return "h264_amf", ["-quality","quality","-b:v",vb]
        if gpu == "intel":
            return "h264_qsv", ["-global_quality","20","-b:v",vb]
        return "libx264", ["-preset","medium","-crf","19"]

    vcodec, vopts = _choose_vcodec(gpu,preset)
    try:
        status_q.put({"type":"log","msg":f"[CODEC] vcodec={vcodec} ({'GPU' if 'nvenc' in vcodec or 'qsv' in vcodec or 'amf' in vcodec else 'CPU'})"})
    except Exception:
        pass

    cmd = list(args) + [
        "-filter_complex", filter_complex,
        "-map", "[vout]", "-map", "0:a",
        "-shortest",  # ensure stop when audio ends (overlay_cuda lacks shortest)
        "-c:v", vcodec, *vopts,
        "-c:a", "aac", "-b:a", "192k",
        "-movflags","+faststart",
    ]

    # CPU paths (or hwdownload) require explicit pix_fmt
    if not use_cuda_fx or not scale_f:
        cmd += ["-pix_fmt","yuv420p"]

    if album_enabled and album_sec>0 and not album_combined:
        cmd += ["-t", str(album_sec)]
    if threads>0:
        cmd += ["-threads", str(threads)]

    cmd += [str(out_path)]
    return cmd, filter_complex

# ============================ WORKERS ============================
class RenderJob:
    def __init__(self, cfg: Dict, song: Path, bg: Optional[Path], out_dir: Path, album_index: int = 0):
        self.cfg = cfg
        self.song = song
        self.bg = bg
        self.out_dir = out_dir
        self.album_index = album_index


def _run_ffmpeg(cmd: List[str], status_q: "queue.Queue[dict]", cancel_event: threading.Event, worker_name:str, worker_num:int) -> int:
    worker_tag = f"W{worker_num}"

    if os.name == "nt":
        popen_kw = dict(creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    else:
        popen_kw = dict(preexec_fn=os.setsid)

    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, **popen_kw)
    _reg(p)

    try:
        for line in p.stdout:
            if cancel_event.is_set():
                try:
                    if os.name=="nt":
                        subprocess.call(["taskkill","/F","/T","/PID",str(p.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    else:
                        os.killpg(os.getpgid(p.pid), signal.SIGKILL)
                except Exception: pass
                break
            line=(line or "").strip()
            if not line: continue
            lo=line.lower()
            if lo.startswith("frame=") or lo.startswith("fps=") or "time=" in lo or "speed=" in lo or "bitrate=" in lo:
                status_q.put({"type":"log","msg":f"[{worker_tag}] {line}"})
            if "error" in lo or "invalid argument" in lo or "not implemented" in lo:
                status_q.put({"type":"log","msg":f"[{worker_tag}] {line}"})
        return p.wait()
    finally:
        _unreg(p)


def _worker_loop(name:str, worker_num:int, qin:"queue.Queue[RenderJob]", status_q:"queue.Queue[dict]", cancel_event:threading.Event, jobs_count:int):
    worker_tag = f"W{worker_num}"
    while not _STOP_ALL:
        try:
            job = qin.get(timeout=0.2)
        except queue.Empty:
            if cancel_event.is_set(): break
            continue
        except Exception as e:
            status_q.put({"type":"log","msg":f"[{worker_tag}] queue error: {e}"})
            continue

        try:
            if job is None or cancel_event.is_set():
                qin.task_done(); break

            out_dir=job.out_dir; out_dir.mkdir(parents=True, exist_ok=True)
            ts=time.strftime("%Y%m%d_%H%M%S")
            W,H,_=_parse_res(job.cfg.get("resolution","1920x1080 30fps"))
            out_path = (out_dir/f"album_{job.album_index}_{W}x{H}_{ts}.mp4" if job.album_index>0 else out_dir/f"render_{W}x{H}_{ts}_{worker_tag}.mp4")

            cmd, _ = _ffmpeg_cmd_single(job.cfg, job.song, job.bg, out_path, status_q)
            if job.album_index > 0:
                status_q.put({"type":"log","msg":f"▶ {worker_tag} Альбом {job.album_index}: старт рендера"})
            else:
                status_q.put({"type":"log","msg":f"▶ {worker_tag}/{jobs_count} Рендер: {job.song.name}"})

            code=_run_ffmpeg(cmd, status_q, cancel_event, worker_tag, worker_num)
            if code==0:
                if job.album_index > 0:
                    status_q.put({"type":"log","msg":f"✅ {worker_tag} Альбом {job.album_index} готово: {out_path.name}"})
                    status_q.put({"type":"done","output":f"Альбом {job.album_index}: {out_path.name}"})
                    # cleanup temporary album wav if created by backend
                    try:
                        if str(job.song.name).startswith("album_audio_") and job.song.exists():
                            job.song.unlink(missing_ok=True)
                            status_q.put({"type":"log","msg":f"[CLEAN] Видалено тимчасовий аудіо-файл альбому: {job.song.name}"})
                    except Exception:
                        pass
                else:
                    status_q.put({"type":"log","msg":f"✅ {worker_tag}/{jobs_count} Готово: {out_path.name}"})
                    status_q.put({"type":"done","output":f"Кліп: {out_path.name}"})
            else:
                if job.album_index > 0:
                    status_q.put({"type":"error","msg":f"Альбом {job.album_index} помилка: FFmpeg exit {code}"})
                else:
                    status_q.put({"type":"error","msg":f"Кліп помилка: FFmpeg exit {code}"})
        finally:
            qin.task_done()

# ============================ PUBLIC API ============================
class _BgPool:
    def __init__(self, items: List[Path]):
        self.items = list(items)
        self.idx = 0
    def next(self) -> Optional[Path]:
        if not self.items:
            return None
        p = self.items[self.idx]
        self.idx = (self.idx + 1) % len(self.items)
        return p


def _select_batch(songs_all: List[Path], last_position: int, want: int, until_material: bool) -> Tuple[List[Path], int]:
    """Повертає рівно *want* треків (або менше, якщо залишок менший).
    *until_material* не впливає на розмір батчу — лише на те, чи повторюємо циклом.
    """
    total = len(songs_all)
    if total == 0 or last_position >= total:
        return [], last_position
    chunk = max(1, int(want or 1))
    end = min(total, last_position + chunk)
    batch = songs_all[last_position:end]
    new_pos = end
    return batch, new_pos


def _build_album_audio(tracks: List[Path], album_sec: int, status_q: "queue.Queue[dict]") -> Tuple[Path, float]:
    assert tracks, "tracks must be non-empty"
    ms_limit = max(0, int(album_sec * 1000))
    combined = AudioSegment.silent(duration=0)
    order_log: List[str] = []

    if ms_limit == 0:
        for t in tracks:
            try:
                seg = AudioSegment.from_file(t)
                combined += seg
                order_log.append(t.name)
            except Exception as e:
                status_q.put({"type":"log","msg":f"⚠ Пропуск {t.name}: {e}"})
    else:
        total = 0
        while total < ms_limit:
            for t in tracks:
                try:
                    seg = AudioSegment.from_file(t)
                except Exception as e:
                    status_q.put({"type":"log","msg":f"⚠ Пропуск {t.name}: {e}"}); continue
                if total + len(seg) > ms_limit:
                    need = ms_limit - total
                    if need > 0:
                        combined += seg[:need]
                        order_log.append(f"{t.name}[:{need}ms]")
                        total += need
                    break
                else:
                    combined += seg
                    order_log.append(t.name)
                    total += len(seg)
            else:
                continue
            break

    out_wav = CACHE_DIR / f"album_audio_{int(time.time())}.wav"
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    combined.export(out_wav, format="wav")
    dur_sec = len(combined) / 1000.0
    status_q.put({"type":"log","msg":f"[ALBUM] Комбіновано {len(order_log)} сегм.: {', '.join(order_log)}"})
    status_q.put({"type":"log","msg":f"[ALBUM] Тривалість: {dur_sec:.2f}s (ціль {album_sec or '—'}s)"})
    return out_wav, dur_sec


def start_video_jobs(cfg: Dict, status_q: "queue.Queue[dict]", cancel_event: threading.Event):
    global _RUNNING, _STOP_ALL, _MANAGER_THREAD
    if _RUNNING:
        status_q.put({"type":"log","msg":"⚠ Уже виконується."}); return

    music_dir = (cfg.get("music_dir"," ") or "").strip()
    media_dir = (cfg.get("media_dir"," ") or "").strip()
    out_dir   = (cfg.get("out_dir"," ") or "").strip()

    songs_all = _list_files(music_dir, AUDIO_EXT)
    if not songs_all:
        status_q.put({"type":"error","msg":"⛔ Немає аудіо у папці Музика."}); return
    imgs_all  = _list_files(media_dir, IMAGE_EXT)

    out_path = Path(out_dir) if out_dir else Path(".")
    jobs=max(1,min(10,_safe_int(cfg.get("jobs",1),1)))
    want=max(1,min(100,_safe_int(cfg.get("songs",1),1)))
    until_material = bool(cfg.get("until_material", False))
    album_enabled = bool(cfg.get("album_enabled", True))
    album_sec = _safe_int(cfg.get("album_sec",0),0)

    # Log effective batching plan
    try:
        status_q.put({"type":"log","msg":f"[CFG] until_material={until_material}, songs_per_album={want}, jobs={jobs}"})
    except Exception:
        pass

    state = _load_processing_state()
    last_position = state.get("last_position", 0)
    if last_position >= len(songs_all):
        last_position = 0

    status_q.put({"type":"log","msg":f"[RESUME] Позиція {last_position}/{len(songs_all)}"})

    qin:"queue.Queue[RenderJob]" = queue.Queue(maxsize=max(1, jobs*2))

    def _manager():
        global _RUNNING, _STOP_ALL
        _RUNNING=True; _STOP_ALL=False
        try:
            workers=[]
            for i in range(jobs):
                t=threading.Thread(target=_worker_loop, args=(f"W{i+1}", i+1, qin, status_q, cancel_event, jobs), daemon=True)
                t.start(); workers.append(t)

            bg_pool = _BgPool(imgs_all)
            new_position = last_position
            albums_enqueued = 0

            if album_enabled:
                idx = 1
                while True:
                    batch, new_position = _select_batch(songs_all, new_position, want, until_material)
                    if not batch:
                        break
                    status_q.put({"type":"log","msg":f"[PLAN] Альбом {idx}: {len(batch)} трек(ів), ціль {album_sec or '—'}s"})
                    album_wav, _ = _build_album_audio(batch, album_sec, status_q)
                    cfg_local = dict(cfg); cfg_local["album_combined"] = True
                    qin.put(RenderJob(cfg_local, album_wav, bg_pool.next(), out_path, idx))
                    albums_enqueued += 1; idx += 1
                    if not until_material:
                        break
                with _REMAINING_LOCK:
                    globals()["_REMAINING"] = albums_enqueued
            else:
                batch, new_position = _select_batch(songs_all, last_position, want, until_material)
                for s in batch:
                    qin.put(RenderJob(cfg, s, bg_pool.next(), out_path, 0))
                with _REMAINING_LOCK:
                    globals()["_REMAINING"] = len(batch)

            qin.join()

            _save_processing_state({
                "last_position": new_position,
                "processed_songs": [str(p) for p in songs_all[:new_position]]
            })
            status_q.put({"type":"log","msg":f"[SAVE] Позиція збережена: {new_position}/{len(songs_all)}"})

            for _ in workers: qin.put(None)
            for t in workers: t.join(timeout=0.3)

            status_q.put({"type":"log","msg":"[DONE] Усі задачі завершено."})
            status_q.put({"type":"all_done"})
        finally:
            _RUNNING=False

    _MANAGER_THREAD = threading.Thread(target=_manager, name="FFMPEG_MANAGER", daemon=True)
    _MANAGER_THREAD.start()


def reset_processing_state():
    _reset_processing_state()


# ============================ SELF-TESTS ============================
if __name__ == "__main__":
    # These do NOT call real ffmpeg. They validate chain building logic only.
    class _DummyQ:
        def __init__(self): self.logs=[]
        def put(self, obj):
            if isinstance(obj, dict) and obj.get("type") == "log":
                self.logs.append(obj.get("msg",""))

    q=_DummyQ()
    cfg_cpu = {"resolution":"640x360 25fps","gpu":"auto","gpu_effects":False,"album_enabled":False}
    cmd_cpu, fc_cpu = _ffmpeg_cmd_single(cfg_cpu, Path("a.wav"), None, Path("o.mp4"), q)
    assert "overlay=" in fc_cpu and "[vout]" in fc_cpu

    # Simulate that only overlay_cuda exists but no scale_npp/scale_cuda → expect hwdownload fallback
    _FFMPEG_FILTERS = {"overlay_cuda","hwupload_cuda"}
    cfg_gpu = {"resolution":"640x360 25fps","gpu":"auto","gpu_effects":True,"album_enabled":False}
    cmd_gpu, fc_gpu = _ffmpeg_cmd_single(cfg_gpu, Path("a.wav"), None, Path("o.mp4"), q)
    assert ("overlay_cuda" in fc_gpu) and ("hwdownload" in fc_gpu)

    # Simulate scale_cuda present → no hwdownload, keep GPU frames
    _FFMPEG_FILTERS = {"overlay_cuda","hwupload_cuda","scale_cuda"}
    cmd_gpu2, fc_gpu2 = _ffmpeg_cmd_single(cfg_gpu, Path("a.wav"), None, Path("o.mp4"), q)
    assert ("overlay_cuda" in fc_gpu2) and ("scale_cuda" in fc_gpu2) and ("hwdownload" not in fc_gpu2)

    print("Self-tests passed.")
