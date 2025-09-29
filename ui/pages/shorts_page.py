# -*- coding: utf-8 -*-
"""
shorts_page.py — GPU/CPU multi-worker audio shorts cutter & 2-stage gender sorter

Фічі:
- Багатопотоковий різ (QThread), GUI не блокується.
- CUDA автодетект (torch+torchaudio CUDA).
- Вибір фрагментів: енергія + флюкс + onset, VAD-вага, вирівнювання до біта, антидублі.
- Покращення звуку: 10 пресетів (можна комбінувати) + м'який лімітер зі стелею (dBFS).
- Класифікація статі суперконсервативна: октавна корекція F0; якщо є torchcrepe — ще точніше.
- Кнопка «Очистити кеш».
- **Двостадійний режим**: спочатку все у `shorts_all/`, потім кнопка «Класифікувати» розкидає у `men/`, `women/`, `unknown/`.
"""

import os, sys, math, shutil
from queue import Queue
from dataclasses import dataclass
from typing import List, Tuple

import numpy as np

# ---------- Optional GPU stack ----------
TORCH_OK = False
try:
    import torch, torchaudio
    TORCH_OK = True
except Exception:
    TORCH_OK = False

# ---------- Optional CREPE (кращий F0) ----------
CREPE_OK = False
try:
    import torchcrepe  # optional; дає кращу стабільність F0
    CREPE_OK = True
except Exception:
    CREPE_OK = False

# ---------- Optional VAD ----------
VAD_OK = False
try:
    import webrtcvad
    VAD_OK = True
except Exception:
    VAD_OK = False

# ---------- CPU libs ----------
try:
    import librosa
except Exception:
    librosa = None
try:
    import soundfile as sf
except Exception:
    sf = None

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit,
    QSpinBox, QDoubleSpinBox, QPushButton, QFileDialog, QCheckBox,
    QLabel, QScrollArea, QFrame, QProgressBar, QSlider, QGridLayout
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QPalette, QColor

# ====================== helpers ======================

def _device_select(prefer_gpu=True) -> str:
    if prefer_gpu and TORCH_OK:
        try:
            if torch.cuda.is_available(): return "cuda"
        except Exception: pass
    return "cpu"

def _ensure_dir(path: str): os.makedirs(path, exist_ok=True)

def _save_wav(path: str, data: np.ndarray, sr: int):
    _ensure_dir(os.path.dirname(path))
    x = np.asarray(data, dtype=np.float32)
    if TORCH_OK:
        try:
            torchaudio.save(path, torch.from_numpy(x).unsqueeze(0), sr); return
        except Exception: pass
    if sf is not None:
        sf.write(path, x, sr); return
    import wave
    x16 = np.clip(x, -1, 1).astype(np.float32)
    x16 = (x16*32767.0).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(x16.tobytes())

# ---- biquad filters (RBJ) ----
def _biquad_coeffs(kind: str, fc: float, fs: float, q: float = 0.7071):
    w0=2*math.pi*(fc/fs); cosw0=math.cos(w0); sinw0=math.sin(w0); a=sinw0/(2*q)
    if kind=="lowpass":
        b0=(1-cosw0)/2; b1=1-cosw0; b2=(1-cosw0)/2; a0=1+a; a1=-2*cosw0; a2=1-a
    elif kind=="highpass":
        b0=(1+cosw0)/2; b1=-(1+cosw0); b2=(1+cosw0)/2; a0=1+a; a1=-2*cosw0; a2=1-a
    else: raise ValueError("kind")
    b0/=a0; b1/=a0; b2/=a0; a1/=a0; a2/=a0
    return b0,b1,b2,a1,a2

def _biquad_peq(fc: float, fs: float, gain_db: float, Q: float):
    A = 10**(gain_db/40.0); w0=2*math.pi*(fc/fs); alpha=math.sin(w0)/(2*Q); cosw0=math.cos(w0)
    b0 = 1 + alpha*A; b1 = -2*cosw0; b2 = 1 - alpha*A
    a0 = 1 + alpha/A; a1 = -2*cosw0; a2 = 1 - alpha/A
    b0/=a0; b1/=a0; b2/=a0; a1/=a0; a2/=a0; return b0,b1,b2,a1,a2

def _biquad_shelf(kind: str, fc: float, fs: float, gain_db: float, S: float = 1.0):
    A=10**(gain_db/40.0); w0=2*math.pi*(fc/fs); cosw0=math.cos(w0); sinw0=math.sin(w0)
    alpha = sinw0/2 * math.sqrt( (A + 1/A)*(1/S - 1) + 2 )
    if kind=="low":
        b0=A*((A+1)-(A-1)*cosw0+2*math.sqrt(A)*alpha); b1=2*A*((A-1)-(A+1)*cosw0); b2=A*((A+1)-(A-1)*cosw0-2*math.sqrt(A)*alpha)
        a0=(A+1)+(A-1)*cosw0+2*math.sqrt(A)*alpha; a1=-2*((A-1)+(A+1)*cosw0); a2=(A+1)+(A-1)*cosw0-2*math.sqrt(A)*alpha
    elif kind=="high":
        b0=A*((A+1)+(A-1)*cosw0+2*math.sqrt(A)*alpha); b1=-2*A*((A-1)+(A+1)*cosw0); b2=A*((A+1)+(A-1)*cosw0-2*math.sqrt(A)*alpha)
        a0=(A+1)-(A-1)*cosw0+2*math.sqrt(A)*alpha; a1=2*((A-1)-(A+1)*cosw0); a2=(A+1)-(A-1)*cosw0-2*math.sqrt(A)*alpha
    else: raise ValueError("kind must be 'low' or 'high'")
    b0/=a0; b1/=a0; b2/=a0; a1/=a0; a2/=a0; return b0,b1,b2,a1,a2

def _biquad_filter(x: np.ndarray, b0,b1,b2,a1,a2)->np.ndarray:
    y=np.zeros_like(x, dtype=np.float32); x1=x2=y1=y2=0.0
    for n in range(len(x)):
        xn=float(x[n]); yn=b0*xn + b1*x1 + b2*x2 - a1*y1 - a2*y2
        y[n]=yn; x2=x1; x1=xn; y2=y1; y1=yn
    return y

# ---- mastering / limiter ----
def _soft_limiter(x: np.ndarray, ceiling_db: float)->np.ndarray:
    c = 10**(ceiling_db/20.0)  # dBFS -> linear (0..1)
    if c >= 0.999:  # майже без ліміту
        return np.clip(x, -1, 1).astype(np.float32, copy=False)
    y = np.tanh(x / max(c,1e-6))
    y = y * c / np.tanh(1.0)
    return y.astype(np.float32, copy=False)

def _normalize_peak(x: np.ndarray, target=0.98)->np.ndarray:
    peak=float(np.max(np.abs(x)) or 1.0)
    return (x/peak*target).astype(np.float32, copy=False)

def _base_master(x: np.ndarray, sr: int)->np.ndarray:
    x=_normalize_peak(x, 0.98)
    b=_biquad_coeffs("highpass", 80.0, sr); x=_biquad_filter(x,*b)
    b=_biquad_coeffs("lowpass", 15000.0, sr); x=_biquad_filter(x,*b)
    return x

def _apply_eq_np(x: np.ndarray, sr: int, kind: str, **kw)->np.ndarray:
    if kind=="peq":  b=_biquad_peq(kw["fc"], sr, kw["gain_db"], kw.get("Q",1.0))
    elif kind=="ls": b=_biquad_shelf("low", kw["fc"], sr, kw["gain_db"], kw.get("S",1.0))
    elif kind=="hs": b=_biquad_shelf("high", kw["fc"], sr, kw["gain_db"], kw.get("S",1.0))
    else: raise ValueError("bad eq kind")
    return _biquad_filter(x,*b)

def _eq_torch(t: "torch.Tensor", sr: int, kind: str, **kw):
    if not TORCH_OK: raise RuntimeError
    if kind in ("peq","ls","hs"):
        return torchaudio.functional.equalizer_biquad(t, sr, center_freq=kw["fc"], Q=kw.get("Q",0.7), gain=kw["gain_db"])
    return t

PRESET_LIST = [
    "Pop Clean","R&B Smooth","Hip-Hop Bass","EDM Bright","Rock Grit",
    "Acoustic Natural","Jazz Warm","Trap 808","Podcast/Vocal","De-Harsh"
]

def enhance_audio(y: np.ndarray, sr: int, presets: List[str], ceiling_db: float) -> np.ndarray:
    x = _base_master(y.astype(np.float32, copy=False), sr)
    def peq(fc, g, Q=1.0):
        nonlocal x
        if TORCH_OK:
            try: x=_eq_torch(torch.from_numpy(x), sr, "peq", fc=fc, gain_db=g, Q=Q).numpy(); return
            except Exception: pass
        x=_apply_eq_np(x, sr, "peq", fc=fc, gain_db=g, Q=Q)
    def ls(fc, g, S=1.0):
        nonlocal x
        if TORCH_OK:
            try: x=_eq_torch(torch.from_numpy(x), sr, "ls", fc=fc, gain_db=g, S=S).numpy(); return
            except Exception: pass
        x=_apply_eq_np(x, sr, "ls", fc=fc, gain_db=g, S=S)
    def hs(fc, g, S=1.0):
        nonlocal x
        if TORCH_OK:
            try: x=_eq_torch(torch.from_numpy(x), sr, "hs", fc=fc, gain_db=g, S=S).numpy(); return
            except Exception: pass
        x=_apply_eq_np(x, sr, "hs", fc=fc, gain_db=g, S=S)

    for name in presets:
        if name=="Pop Clean":
            peq(5000,-2.0,2.0); peq(3000, +2.0,1.4); hs(12000, +2.0,0.8)
        elif name=="R&B Smooth":
            ls(150, +2.0,0.7);  peq(7000, -3.0,2.5); hs(12000,+1.5,0.7)
        elif name=="Hip-Hop Bass":
            ls(80, +3.0,0.8);   peq(2000, +1.5,1.2); peq(5000,-2.0,2.0)
        elif name=="EDM Bright":
            peq(3500,+3.0,1.0); hs(12000,+3.0,0.8); peq(6000,-2.0,3.0)
        elif name=="Rock Grit":
            peq(2500,+2.0,1.2); peq(4000,-3.0,2.0)
        elif name=="Acoustic Natural":
            peq(300,-1.5,1.0);  hs(12000,+1.5,0.8)
        elif name=="Jazz Warm":
            ls(120,+2.0,0.8);   peq(7000,-2.0,2.0)
        elif name=="Trap 808":
            ls(50,+4.0,0.7);    peq(2000,+1.0,1.2); peq(5000,-2.0,2.0)
        elif name=="Podcast/Vocal":
            peq(1600,+3.0,1.2); peq(8000,-3.0,3.0); b=_biquad_coeffs("highpass",80.0,sr); x=_biquad_filter(x,*b)
        elif name=="De-Harsh":
            peq(6000,-4.0,3.0)

    return _soft_limiter(x, ceiling_db)

# ===================== Pitch / Gender =====================

def _fold_octaves_vec(f: np.ndarray, lo=80.0, hi=340.0) -> np.ndarray:
    f = f.astype(np.float32, copy=False)
    for _ in range(3):
        m = f > hi
        if np.any(m): f[m] *= 0.5
        m = (f > 0) & (f < lo)
        if np.any(m): f[m] *= 2.0
    return f

def _pitch_profile_crepe(y: np.ndarray, sr: int, device: str) -> dict:
    if not CREPE_OK: return {"median":0.0,"p25":0.0,"p75":0.0,"voiced":0.0}
    # resample to 16k for speed
    if TORCH_OK:
        t=torch.from_numpy(y.astype(np.float32,copy=False)).to("cpu")
        if sr!=16000: t=torchaudio.functional.resample(t, sr, 16000)
        t=t.unsqueeze(0)  # (1,T)
        try:
            f0, per = torchcrepe.predict(
                t, 16000, hop_length=160, fmin=50.0, fmax=600.0,
                model='full', batch_size=1024, device=("cuda" if (device=="cuda" and torch.cuda.is_available()) else "cpu"),
                return_periodicity=True
            )
            # median filter
            f0  = torchcrepe.filter.median(f0, 3)
            per = torchcrepe.filter.median(per, 3)
            mask = per > 0.45
            f0 = f0[mask].detach().cpu().numpy().astype(np.float32, copy=False)
            vf = float(mask.float().mean().item())
            if f0.size==0: return {"median":0.0,"p25":0.0,"p75":0.0,"voiced":0.0}
            f0=_fold_octaves_vec(f0)
            return {
                "median": float(np.median(f0)),
                "p25":    float(np.percentile(f0,25)),
                "p75":    float(np.percentile(f0,75)),
                "voiced": vf
            }
        except Exception:
            return {"median":0.0,"p25":0.0,"p75":0.0,"voiced":0.0}
    return {"median":0.0,"p25":0.0,"p75":0.0,"voiced":0.0}

if TORCH_OK:
    def _pitch_profile_torch(y_t, sr:int)->dict:
        try:
            f = torchaudio.functional.detect_pitch_frequency(y_t.unsqueeze(0), sr)[0]
            total=int(f.numel()); 
            if total==0: return {"median":0.0,"p25":0.0,"p75":0.0,"voiced":0.0}
            mask=f>0; vf=float(mask.float().mean().item())
            arr=f[mask].detach().cpu().numpy().astype(np.float32,copy=False)
            if arr.size==0: return {"median":0.0,"p25":0.0,"p75":0.0,"voiced":0.0}
            arr=_fold_octaves_vec(arr)
            return {"median":float(np.median(arr)),
                    "p25":float(np.percentile(arr,25)),
                    "p75":float(np.percentile(arr,75)),
                    "voiced":vf}
        except Exception:
            return {"median":0.0,"p25":0.0,"p75":0.0,"voiced":0.0}
else:
    def _pitch_profile_torch(*a, **k)->dict:
        return {"median":0.0,"p25":0.0,"p75":0.0,"voiced":0.0}

def _pitch_profile_librosa(y: np.ndarray, sr:int)->dict:
    if librosa is None: return {"median":0.0,"p25":0.0,"p75":0.0,"voiced":0.0}
    try:
        f0,_,_=librosa.pyin(y, fmin=librosa.note_to_hz('C2'), fmax=librosa.note_to_hz('C7'))
        total=int(f0.size)
        if total==0: return {"median":0.0,"p25":0.0,"p75":0.0,"voiced":0.0}
        valid=f0[~np.isnan(f0)]
        vf=float(valid.size/total)
        if valid.size==0: return {"median":0.0,"p25":0.0,"p75":0.0,"voiced":0.0}
        arr=_fold_octaves_vec(valid.astype(np.float32,copy=False))
        return {"median":float(np.median(arr)),
                "p25":float(np.percentile(arr,25)),
                "p75":float(np.percentile(arr,75)),
                "voiced":vf}
    except Exception:
        return {"median":0.0,"p25":0.0,"p75":0.0,"voiced":0.0}

def _decide_gender(profs: List[dict]) -> str:
    P=[p for p in profs if p["median"]>0]
    if not P: return "UNK"
    vfrac=float(np.mean([p["voiced"] for p in P]))
    med=float(np.median([p["median"] for p in P]))
    p25=float(np.median([p["p25"] for p in P]))
    p75=float(np.median([p["p75"] for p in P]))
    # консервативно: WOM важко отримати, MAN теж зі страховкою
    if vfrac < 0.45: return "UNK"
    if med >= 205.0 and p25 >= 190.0: return "WOM"
    if med <= 165.0 and p75 <= 185.0: return "MAN"
    return "UNK"

# ---- VAD ----
def _resample_to_16k(y: np.ndarray, sr:int)->Tuple[np.ndarray,int]:
    if sr==16000: return y.astype(np.float32,copy=False), sr
    if TORCH_OK:
        try:
            t=torch.from_numpy(y.astype(np.float32,copy=False))
            t=torchaudio.functional.resample(t, sr, 16000)
            return t.numpy().astype(np.float32,copy=False), 16000
        except Exception: pass
    if librosa is not None:
        try: return librosa.resample(y, orig_sr=sr, target_sr=16000).astype(np.float32,copy=False), 16000
        except Exception: pass
    new_len=int(len(y)*16000/sr); idx=np.linspace(0,len(y)-1,new_len).astype(np.float32)
    return np.interp(idx, np.arange(len(y)), y).astype(np.float32,copy=False), 16000

def _vad_strength_frames(y: np.ndarray, sr:int, N:int, hop:int)->np.ndarray:
    if not VAD_OK: return np.zeros(N, dtype=np.float32)
    y16,sr16=_resample_to_16k(y,sr); vad=webrtcvad.Vad(2)
    win_ms=30; win_len=int(sr16*win_ms/1000)
    s=np.clip(y16,-1,1); s=(s*32767).astype(np.int16).tobytes()
    flags=[]
    for i in range(0,len(s),win_len*2):
        chunk=s[i:i+win_len*2]
        if len(chunk)<win_len*2: break
        try: flags.append(1 if vad.is_speech(chunk, sr16) else 0)
        except Exception: flags.append(0)
    if not flags: return np.zeros(N, dtype=np.float32)
    step_t=win_ms/1000.0; out=np.zeros(N, dtype=np.float32)
    for i in range(N):
        t=i*hop/float(sr); j=min(len(flags)-1, int(round(t/step_t)))
        jj=flags[max(0,j-1):min(len(flags),j+2)]; out[i]=float(sum(jj)/max(1,len(jj)))
    return out

# ---- beat align ----
def _align_to_beat(start_samp:int, win:int, y:np.ndarray, sr:int)->int:
    if not librosa: return start_samp
    try:
        _, beats = librosa.beat.beat_track(y=y, sr=sr, units='time')
        if beats is None or len(beats)==0: return start_samp
        t0=start_samp/sr
        diffs=[b for b in beats if b<=t0 and (t0-b)<=0.5]
        if not diffs: return start_samp
        s=int(max(diffs)*sr)
        return max(0, min(s, len(y)-win))
    except Exception: return start_samp

# ---- features for picker ----
if TORCH_OK:
    def _stft_feats_torch(y, sr:int, frame:int, hop:int):
        window=torch.hann_window(frame, device=y.device)
        spec=torch.stft(y, n_fft=frame, hop_length=hop, window=window, return_complex=True)
        mag=spec.abs()
        rms=torch.sqrt((mag.pow(2).mean(dim=0)).clamp_min(1e-12))
        flux=torch.relu(mag[:,1:]-mag[:,:-1]).mean(dim=0)
        flux=torch.cat([flux.new_zeros(1), flux], dim=0)
        return rms, flux
else:
    def _stft_feats_torch(*a, **k): raise RuntimeError("Torch not available")

def _stft_feats_librosa(y: np.ndarray, sr:int, frame:int, hop:int):
    if not librosa:
        rms=np.sqrt(np.maximum(np.convolve(y**2, np.ones(1024),'same'),1e-12))[::hop]
        return rms, np.zeros_like(rms)
    S=np.abs(librosa.stft(y, n_fft=frame, hop_length=hop, window="hann"))
    rms=np.sqrt(np.mean(S**2, axis=0)+1e-12)
    flux=np.maximum(S[:,1:]-S[:,:-1],0.0).mean(axis=0)
    flux=np.concatenate([[0.0],flux],axis=0)
    return rms, flux

def _normalize01(a):
    a=a.astype(np.float32, copy=False); mn=float(a.min()); mx=float(a.max())
    return np.zeros_like(a, dtype=np.float32) if mx<=mn+1e-12 else (a-mn)/(mx-mn)

# ---------- improved picker ----------
def pick_segments(y: np.ndarray, sr:int, seconds:int, top_k:int, thr_scale:float, device:str, prefer_vocals:bool):
    frame=max(1024, int(sr*0.046)); hop=max(256, frame//4); win=seconds*sr
    if TORCH_OK and device=="cuda":
        yt=torch.from_numpy(y).to(device)
        rms_t, flux_t=_stft_feats_torch(yt, sr, frame, hop)
        dr=torch.relu(rms_t[1:]-rms_t[:-1]); dr=torch.cat([dr.new_zeros(1),dr],dim=0)
        rms=rms_t.detach().cpu().numpy(); flux=flux_t.detach().cpu().numpy(); onset=dr.detach().cpu().numpy()
    else:
        rms,flux=_stft_feats_librosa(y,sr,frame,hop)
        onset=np.concatenate([[0.0], np.maximum(rms[1:]-rms[:-1], 0.0)])
    base = 0.55*_normalize01(rms) + 0.35*_normalize01(flux) + 0.10*_normalize01(onset)
    gate = (rms > float(rms.mean())*float(thr_scale)).astype(np.float32)
    score = base * gate
    if prefer_vocals:
        vad = _vad_strength_frames(y, sr, len(score), hop)
        score = score * (0.4 + 0.6*vad)
    order=np.argsort(score)[::-1]
    picked: List[Tuple[int,int]]=[]; fps: List[np.ndarray]=[]
    min_center_gap=int(1.0*sr)
    for idx in order:
        if len(picked)>=top_k: break
        s=idx*hop; e=s+win
        if e>len(y) or score[idx]<=0.0: continue
        if any(not (e<=s2 or s>=e2) for (s2,e2) in picked): continue
        # антидублі (швидкий fp)
        fp = (y[s:e: max(1,sr//120)]).astype(np.float32, copy=False)
        if fps and max(float(np.dot(fp[:200],f[:200])/(np.linalg.norm(fp[:200])*np.linalg.norm(f[:200])+1e-9)) for f in fps) >= 0.97:
            continue
        s_al=_align_to_beat(s, win, y, sr); e_al=s_al+win
        picked.append((s_al,e_al)); fps.append(fp)
    return picked

# ====================== workers ======================

@dataclass
class WorkerParams:
    detect_gender: bool
    prefer_vocals: bool
    chunk_seconds: int
    top_k: int
    thr_scale: float
    device: str
    presets: List[str]
    ceiling_db: float
    two_stage: bool  # якщо True — різати в shorts_all/

class SongWorker(QThread):
    sig_log = Signal(int, str)
    sig_file = Signal(int, str)
    sig_prog = Signal(int, int)
    sig_done = Signal(int)

    def __init__(self, wid:int, tasks:Queue, params:WorkerParams, parent=None):
        super().__init__(parent)
        self.wid=wid; self.tasks=tasks; self.p=params
        self.stop_flag=False; self.done_files=0; self.total=max(1,self.tasks.qsize())

    def stop(self): self.stop_flag=True

    def run(self):
        self.sig_prog.emit(self.wid,0)
        while not self.stop_flag:
            if self.tasks.empty(): break
            try: path=self.tasks.get_nowait()
            except Exception: break
            try:
                self.sig_file.emit(self.wid, os.path.basename(path))
                self._process_one(path)
                self.done_files+=1
                self.sig_prog.emit(self.wid, int(100*self.done_files/self.total))
            except Exception as e:
                self.sig_log.emit(self.wid, f"ERROR {os.path.basename(path)}: {e}")
        self.sig_done.emit(self.wid)

    def _process_one(self, path:str):
        # load mono 44.1k
        if TORCH_OK:
            wav, sr0 = torchaudio.load(path); wav = wav.mean(dim=0)
            wav = wav.to(self.p.device if self.p.device=="cuda" else "cpu", dtype=torch.float32)
            if sr0!=44100: wav=torchaudio.functional.resample(wav, sr0, 44100); sr=44100
            else: sr=sr0
            y=wav.detach().cpu().numpy().astype(np.float32, copy=False)
        else:
            if not librosa: raise RuntimeError("No audio backend (need torchaudio or librosa).")
            y, sr = librosa.load(path, sr=44100, mono=True); y=y.astype(np.float32, copy=False)

        segs = pick_segments(y, sr, self.p.chunk_seconds, self.p.top_k, self.p.thr_scale, self.p.device, self.p.prefer_vocals)
        if not segs:
            self.sig_log.emit(self.wid, f"No strong moments: {os.path.basename(path)}"); return

        base_dir=os.path.dirname(path)
        # two-stage: все у shorts_all/
        if self.p.two_stage:
            out_dir=os.path.join(base_dir, "shorts_all")
        else:
            # одностадійний: одразу за статтю (або в shorts)
            if self.p.detect_gender:
                gender=self._decide_gender_on_top(y, sr, segs)
                sub={"MAN":"men","WOM":"women"}.get(gender,"unknown")
            else:
                sub="shorts"
            out_dir=os.path.join(base_dir, sub)
        _ensure_dir(out_dir)
        name,_=os.path.splitext(os.path.basename(path))
        for i,(s,e) in enumerate(segs,1):
            seg = enhance_audio(y[s:e], sr, self.p.presets, self.p.ceiling_db)
            suffix = f"_TOP{i}.wav"
            if not self.p.two_stage and self.p.detect_gender:
                # додаємо MAN_/WOM_/UNK_ в ім’я
                gender=self._decide_gender_on_piece(y[s:e], sr)
                out = f"{gender}_{name}{suffix}"
            else:
                out = f"{name}{suffix}"
            _save_wav(os.path.join(out_dir,out), seg, sr)
        self.sig_log.emit(self.wid, f"OK {os.path.basename(path)} → {os.path.basename(out_dir)} (x{len(segs)})")

    # ---- gender helpers for one-stage ----
    def _decide_gender_on_top(self, y: np.ndarray, sr:int, segs: List[Tuple[int,int]])->str:
        profs=[]
        K=min(3, len(segs))
        for s,e in segs[:K]:
            profs.append(self._profile_any(y[s:e], sr))
        return _decide_gender(profs)

    def _decide_gender_on_piece(self, seg: np.ndarray, sr:int)->str:
        return _decide_gender([self._profile_any(seg, sr)])

    def _profile_any(self, x: np.ndarray, sr:int)->dict:
        if CREPE_OK: 
            p=_pitch_profile_crepe(x, sr, self.p.device)
            if p["median"]>0: return p
        if TORCH_OK and self.p.device=="cuda":
            t=torch.from_numpy(x).to(self.p.device)
            return _pitch_profile_torch(t, sr)
        return _pitch_profile_librosa(x, sr)

# ---- separate classifier worker (stage 2) ----
class ClassifyWorker(QThread):
    sig_log = Signal(int, str)
    sig_file = Signal(int, str)
    sig_prog = Signal(int, int)
    sig_done = Signal(int)

    def __init__(self, wid:int, tasks:Queue, root_dir:str, device:str, parent=None):
        super().__init__(parent)
        self.wid=wid; self.tasks=tasks; self.root=root_dir; self.device=device
        self.stop_flag=False; self.done_files=0; self.total=max(1,self.tasks.qsize())

    def stop(self): self.stop_flag=True

    def run(self):
        self.sig_prog.emit(self.wid,0)
        while not self.stop_flag:
            if self.tasks.empty(): break
            try: path=self.tasks.get_nowait()
            except Exception: break
            try:
                self.sig_file.emit(self.wid, os.path.basename(path))
                self._process_one(path)
                self.done_files+=1
                self.sig_prog.emit(self.wid, int(100*self.done_files/self.total))
            except Exception as e:
                self.sig_log.emit(self.wid, f"ERROR {os.path.basename(path)}: {e}")
        self.sig_done.emit(self.wid)

    def _process_one(self, path:str):
        # load audio
        if TORCH_OK:
            wav, sr0 = torchaudio.load(path); wav = wav.mean(dim=0)
            if sr0!=44100: wav=torchaudio.functional.resample(wav, sr0, 44100); sr=44100
            else: sr=sr0
            y=wav.detach().cpu().numpy().astype(np.float32, copy=False)
        else:
            if not librosa: raise RuntimeError("No audio backend (need torchaudio or librosa).")
            y, sr = librosa.load(path, sr=44100, mono=True); y=y.astype(np.float32, copy=False)

        # robust profile on whole piece (досить довгий уривок)
        prof = self._profile_any(y, sr)
        gender = _decide_gender([prof])

        target={"MAN":"men","WOM":"women"}.get(gender,"unknown")
        out_dir=os.path.join(self.root, target); _ensure_dir(out_dir)
        dst=os.path.join(out_dir, os.path.basename(path))
        try:
            shutil.move(path, dst)
            self.sig_log.emit(self.wid, f"MOVE → {target}: {os.path.basename(path)}")
        except Exception as e:
            self.sig_log.emit(self.wid, f"FAILED MOVE {os.path.basename(path)}: {e}")

    def _profile_any(self, x: np.ndarray, sr:int)->dict:
        if CREPE_OK:
            p=_pitch_profile_crepe(x, sr, "cuda" if (TORCH_OK and torch.cuda.is_available()) else "cpu")
            if p["median"]>0: return p
        if TORCH_OK and torch.cuda.is_available():
            t=torch.from_numpy(x).to("cuda")
            return _pitch_profile_torch(t, sr)
        return _pitch_profile_librosa(x, sr)

# ====================== UI ======================

class WorkerPanel(QFrame):
    def __init__(self, wid:int, title:str, parent=None):
        super().__init__(parent)
        self.setProperty("class","worker-card")
        self.lbl_title=QLabel(f"{title} #{wid+1}"); self.lbl_title.setObjectName("workerTitle")
        self.lbl_file=QLabel("— idle —")
        self.bar=QProgressBar(); self.bar.setRange(0,100); self.bar.setValue(0)
        lay=QVBoxLayout(self); lay.addWidget(self.lbl_title); lay.addWidget(self.lbl_file); lay.addWidget(self.bar)

class ShortsPage(QWidget):
    page_name="Audio Shorts Cut (GPU Multi-Worker, 2-Stage)"

    def __init__(self):
        super().__init__()
        self.host=None; self.tasks=None
        self.workers:List[QThread]=[]; self.panels:List[WorkerPanel]=[]
        self.running=False

        self.selected_presets: List[str] = []
        self.ceiling_db: float = -1.0

        self._build_ui(); self._style()
        dev=_device_select(True); self.lbl_device.setText(f"Device: {dev.upper()} {'(CUDA)' if dev=='cuda' else ''}")

    def set_host(self, host): self.host=host
    def apply_scale(self, scale:float): pass
    def handle_start(self, auto_mode=False): self._start()
    def handle_stop(self): self._stop_all()

    def _build_ui(self):
        root=QVBoxLayout(self)

        # ---- form ----
        form=QFormLayout()
        self.ed_in=QLineEdit(); self.ed_in.setPlaceholderText("Виберіть папку з музикою (.mp3/.wav)")
        btn_in=QPushButton("Browse"); btn_in.clicked.connect(self._choose_in)
        row=QHBoxLayout(); row.addWidget(self.ed_in,1); row.addWidget(btn_in)

        self.sp_workers=QSpinBox(); self.sp_workers.setRange(1,10); self.sp_workers.setValue(2)
        self.sp_chunks =QSpinBox(); self.sp_chunks.setRange(1,5); self.sp_chunks.setValue(2)
        self.sp_len    =QSpinBox(); self.sp_len.setRange(5,120); self.sp_len.setValue(30)
        self.sp_thr    =QDoubleSpinBox(); self.sp_thr.setRange(0.5,5.0); self.sp_thr.setSingleStep(0.1); self.sp_thr.setValue(1.8)
        self.chk_gender=QCheckBox("Розпізнавання голосу (в одностадійному режимі)")
        self.chk_vocal =QCheckBox("Пріоритет вокалу (VAD)")
        self.chk_two_stage=QCheckBox("Двостадійний режим (спочатку все у 'shorts_all/')")

        # ---- presets panel ----
        presets_frame = QFrame(); presets_frame.setProperty("class","preset-card")
        pv = QVBoxLayout(presets_frame)
        pv.addWidget(QLabel("Покращення звуку (оберіть пресети):"))

        grid = QGridLayout()
        self.preset_checks = {}
        for i, name in enumerate(PRESET_LIST):
            cb = QCheckBox(name); self.preset_checks[name]=cb
            grid.addWidget(cb, i//2, i%2)
        pv.addLayout(grid)

        # limiter slider
        hl = QHBoxLayout()
        self.sld_ceiling = QSlider(Qt.Horizontal); self.sld_ceiling.setRange(0, 180); self.sld_ceiling.setValue(10)  # 0..-18 dBFS
        self.lbl_ceiling = QLabel("Верхній поріг: -1.0 dBFS")
        self.sld_ceiling.valueChanged.connect(self._on_ceiling_change)
        hl.addWidget(self.lbl_ceiling); hl.addWidget(self.sld_ceiling)
        pv.addLayout(hl)

        # controls
        self.btn_apply=QPushButton("Застосувати")
        self.btn_start=QPushButton("Старт (Нарізати)")
        self.btn_classify=QPushButton("Класифікувати (MEN/WOM/UNK)")
        self.btn_stop =QPushButton("Стоп"); self.btn_stop.setEnabled(False)
        self.btn_clear=QPushButton("Очистити кеш")

        form.addRow("Вхідна папка:", row)
        form.addRow("К-ть воркерів:", self.sp_workers)
        form.addRow("К-ть шматків на трек:", self.sp_chunks)
        form.addRow("Довжина шортсу (с):", self.sp_len)
        form.addRow("Поріг емоційності:", self.sp_thr)
        form.addRow(self.chk_gender)
        form.addRow(self.chk_vocal)
        form.addRow(self.chk_two_stage)

        top = QHBoxLayout()
        top.addLayout(form, 2)
        right = QVBoxLayout(); right.addWidget(presets_frame)
        self.lbl_device=QLabel("Device: —"); self.lbl_device.setStyleSheet("color:#a3e635;font-weight:600;")
        right.addWidget(self.lbl_device, alignment=Qt.AlignRight)
        top.addLayout(right, 2)

        ctrl=QHBoxLayout(); ctrl.addStretch(1); ctrl.addWidget(self.btn_apply); ctrl.addWidget(self.btn_clear); ctrl.addWidget(self.btn_start); ctrl.addWidget(self.btn_classify); ctrl.addWidget(self.btn_stop)

        root.addLayout(top); root.addLayout(ctrl)

        self.global_bar=QProgressBar(); self.global_bar.setRange(0,100); self.global_bar.setValue(0)
        root.addWidget(self.global_bar)

        self.scroll=QScrollArea(); self.scroll.setWidgetResizable(True)
        self.cards_host=QWidget(); self.cards_layout=QVBoxLayout(self.cards_host)
        self.scroll.setWidget(self.cards_host); root.addWidget(self.scroll,1)

        self.btn_start.clicked.connect(self._start)
        self.btn_classify.clicked.connect(self._start_classify)
        self.btn_stop.clicked.connect(self._stop_all)
        self.btn_clear.clicked.connect(self._clear_cache)
        self.btn_apply.clicked.connect(self._apply_presets)

    def _style(self):
        pal=self.palette()
        pal.setColor(QPalette.Window, QColor("#0f172a"))
        pal.setColor(QPalette.Base, QColor("#0f172a"))
        pal.setColor(QPalette.Text, QColor("#e2e8f0"))
        self.setPalette(pal)
        self.setStyleSheet("""
            QWidget { color:#e2e8f0; font-size:14px; }
            QLineEdit, QSpinBox, QDoubleSpinBox { background:#111827; border:1px solid #334155; border-radius:8px; padding:6px 8px; }
            QPushButton { background:#2563eb; border:none; border-radius:10px; padding:8px 14px; font-weight:700; }
            QPushButton:disabled { background:#1f2937; color:#94a3b8; }
            QProgressBar { background:#0b1220; border:1px solid #334155; border-radius:8px; text-align:center; }
            QProgressBar::chunk { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #22c55e, stop:1 #14b8a6); border-radius:8px; }
            QLabel#workerTitle { font-size:16px; font-weight:800; color:#93c5fd; }
            QFrame[class="worker-card"], QFrame[class="preset-card"] { background:#111827; border:1px solid #334155; border-radius:14px; padding:10px; }
        """)

    # ---------- runtime ----------
    def _choose_in(self):
        d=QFileDialog.getExistingDirectory(self,"Виберіть папку з музикою")
        if d: self.ed_in.setText(d)

    def _on_ceiling_change(self, val:int):
        db = -val/10.0
        self.lbl_ceiling.setText(f"Верхній поріг: {db:.1f} dBFS")

    def _collect_presets(self)->List[str]:
        return [name for name,cb in self.preset_checks.items() if cb.isChecked()]

    def _apply_presets(self):
        self.selected_presets = self._collect_presets()
        self.ceiling_db = -self.sld_ceiling.value()/10.0
        self._log(f"Застосовано пресети: {', '.join(self.selected_presets) if self.selected_presets else '(нема)'}; стеля={self.ceiling_db:.1f} dBFS")

    def _list_audio(self, root_dir:str, exts=(".mp3",".wav")):
        return sorted([os.path.join(root_dir,f) for f in os.listdir(root_dir) if f.lower().endswith(exts)])

    # ---- Stage 1: CUT ----
    def _start(self):
        if self.running: return
        root=(self.ed_in.text() or "").strip()
        if not root or not os.path.isdir(root): return self._log("Оберіть коректну папку.")
        files=self._list_audio(root)
        if not files: return self._log("Немає .mp3/.wav у цій папці.")

        # presets / ceiling (якщо не натискав «Застосувати», беремо поточні значення)
        self.selected_presets = self._collect_presets()
        self.ceiling_db = -self.sld_ceiling.value()/10.0

        two_stage=self.chk_two_stage.isChecked()
        detect=self.chk_gender.isChecked() and (not two_stage)

        # фільтр уже оброблених
        filtered=[]
        for p in files:
            name,_=os.path.splitext(os.path.basename(p))
            if detect:
                if any(os.path.exists(os.path.join(root, sub, f"{pref}_{name}_TOP1.wav"))
                       for sub,pref in (("men","MAN"),("women","WOM"),("unknown","UNK"))): continue
            elif two_stage:
                if os.path.exists(os.path.join(root,"shorts_all",f"{name}_TOP1.wav")): continue
            else:
                if os.path.exists(os.path.join(root,"shorts",f"{name}_TOP1.wav")): continue
            filtered.append(p)
        if not filtered: return self._log("Усе вже оброблено.")

        self.tasks=Queue(); [self.tasks.put(p) for p in filtered]
        n=self.sp_workers.value(); dev=_device_select(True)
        self._log(f"Нарізка: files={len(filtered)}; workers={n}; device={dev}; two_stage={two_stage}; detect_gender={detect}; VAD={self.chk_vocal.isChecked()}; presets={self.selected_presets}; ceiling={self.ceiling_db:.1f} dB")

        p=WorkerParams(
            detect_gender=detect,
            prefer_vocals=self.chk_vocal.isChecked(),
            chunk_seconds=self.sp_len.value(),
            top_k=self.sp_chunks.value(),
            thr_scale=self.sp_thr.value(),
            device=dev,
            presets=self.selected_presets,
            ceiling_db=self.ceiling_db,
            two_stage=two_stage
        )

        self._clear_cards(); self.workers.clear()
        for i in range(n):
            panel=WorkerPanel(i,"Cut Worker", self.cards_host); self.cards_layout.addWidget(panel); self.panels.append(panel)
            w=SongWorker(i, self.tasks, p, self)
            w.sig_log.connect(self._on_log); w.sig_file.connect(self._on_file); w.sig_prog.connect(self._on_prog); w.sig_done.connect(self._on_done)
            self.workers.append(w); w.start()

        self.global_bar.setValue(0); self.running=True
        self.btn_start.setEnabled(False); self.btn_classify.setEnabled(False); self.btn_stop.setEnabled(True)

        self.timer=QTimer(self); self.timer.setInterval(300); self.timer.timeout.connect(self._tick); self.timer.start()

    # ---- Stage 2: CLASSIFY ----
    def _start_classify(self):
        if self.running: return
        root=(self.ed_in.text() or "").strip()
        if not root or not os.path.isdir(root): return self._log("Оберіть коректну папку.")
        src=os.path.join(root, "shorts_all")
        if not os.path.isdir(src): return self._log("Немає папки 'shorts_all'. Спочатку запустіть нарізку з двостадійним режимом.")
        files=self._list_audio(src, (".wav",))
        if not files: return self._log("Немає файлів у 'shorts_all'.")

        q=Queue(); [q.put(p) for p in files]
        n=self.sp_workers.value(); dev=_device_select(True)
        self._log(f"Класифікація: files={len(files)}; workers={n}; device={dev}; CREPE={CREPE_OK}")

        self._clear_cards(); self.workers.clear()
        for i in range(n):
            panel=WorkerPanel(i,"Classify", self.cards_host); self.cards_layout.addWidget(panel); self.panels.append(panel)
            w=ClassifyWorker(i, q, root, dev, self)
            w.sig_log.connect(self._on_log); w.sig_file.connect(self._on_file); w.sig_prog.connect(self._on_prog); w.sig_done.connect(self._on_done)
            self.workers.append(w); w.start()

        self.global_bar.setValue(0); self.running=True
        self.btn_start.setEnabled(False); self.btn_classify.setEnabled(False); self.btn_stop.setEnabled(True)

        self.timer=QTimer(self); self.timer.setInterval(300); self.timer.timeout.connect(self._tick); self.timer.start()

    def _stop_all(self):
        if not self.running: return
        for w in self.workers:
            if hasattr(w,"stop"): w.stop()
        self._log("Stop signal sent.")

    # ---- cache clear ----
    def _clear_cache(self):
        root=(self.ed_in.text() or "").strip()
        if not root or not os.path.isdir(root): return self._log("Оберіть папку для очищення.")
        subdirs=["shorts","shorts_all","men","women","unknown"]; removed=0
        for sd in subdirs:
            p=os.path.join(root, sd)
            if not os.path.isdir(p): continue
            for f in list(os.listdir(p)):
                if not f.lower().endswith(".wav"): continue
                if "_TOP" in f or f.startswith(("MAN_","WOM_","UNK_")) or True:  # у двостадійному видаляємо і з all
                    try: os.remove(os.path.join(p,f)); removed+=1
                    except Exception: pass
            try:
                if not os.listdir(p): os.rmdir(p)
            except Exception: pass
        self._log(f"Кеш очищено. Видалено файлів: {removed}")

    def _clear_cards(self):
        for i in reversed(range(self.cards_layout.count())):
            w=self.cards_layout.itemAt(i).widget()
            if w is not None: w.setParent(None)
        self.panels=[]

    # ---- signals ----
    def _on_log(self, wid:int, msg:str): self._log(f"[W{wid+1}] {msg}")
    def _on_file(self, wid:int, fn:str):
        if 0<=wid<len(self.panels): self.panels[wid].lbl_file.setText(fn)
    def _on_prog(self, wid:int, p:int):
        if 0<=wid<len(self.panels): self.panels[wid].bar.setValue(p)
    def _on_done(self, wid:int):
        if 0<=wid<len(self.panels):
            self.panels[wid].bar.setValue(100); self.panels[wid].lbl_file.setText("— done —")
        if all(not w.isRunning() for w in self.workers):
            self.running=False; self.btn_start.setEnabled(True); self.btn_classify.setEnabled(True); self.btn_stop.setEnabled(False)
            if hasattr(self,"timer") and self.timer: self.timer.stop()
            self.global_bar.setValue(100); self._log("Готово.")

    def _tick(self):
        if not self.running: return
        vals=[p.bar.value() for p in self.panels] if self.panels else []
        if vals: self.global_bar.setValue(int(sum(vals)/len(vals)))

    # ---- host log proxy ----
    def _log(self, m:str):
        if self.host and hasattr(self.host,"log"):
            try: self.host.log(self, m); return
            except Exception: pass
        print(m)
