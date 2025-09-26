# -*- coding: utf-8 -*-
from __future__ import annotations
"""
effects_render.py
Превʼю та генератори PNG-оверлеїв для ефектів (зірки/дощ/дим) +
примітивний індикатор «руху камери» для превʼю.

Ключові принципи:
  • Будь-яка «прозорість» у UI задається як 0..100 (%), у коді мапиться на 0..1.
  • Превʼю максимально збігається з тим, що робить ffmpeg:
      - EQ: висота/позиція baseline відповідає виразу в бекенді.
      - Зірки/дощ/дим: вигляд близький до PNG, який піде в ffmpeg.
Експорт:
  make_eq_overlay(dict, W, H)           -> QPixmap
  make_stars_overlay(dict, W, H)        -> QPixmap
  make_rain_overlay(dict, W, H)         -> QPixmap
  make_smoke_overlay(dict, W, H)        -> QPixmap
  draw_motion_indicator(QPainter, QRect, dict)
"""

from typing import Dict, Tuple, Optional, List
import random, math

from PySide6.QtCore import Qt, QRect, QPoint
from PySide6.QtGui import (
    QPixmap, QPainter, QColor, QPen, QBrush, QImage, QRadialGradient
)

# -------------------- Utils --------------------

def _pct_to_alphaf(op: int) -> float:
    return max(0.02, min(1.0, (int(op) if op is not None else 100) / 100.0))

def _qcolor(hex_or_name: str) -> QColor:
    try:
        return QColor(hex_or_name or "#FFFFFF")
    except Exception:
        return QColor("#FFFFFF")

# -------------------- EQ (превʼю) --------------------

def make_eq_overlay(eq_ui: Dict, W: int, H: int) -> QPixmap:
    """
    Малює 1:1 із логікою бекенда:
        - 'height'  -> висота смуг
        - 'y_offset' (-100..100) -> baseline зсув від центру екрана
        - 'mirror'   -> віддзеркалення вниз
        - 'baseline' -> тонка лінія по baseline
        - 'opacity'  -> 0..100 (%)
    """
    img = QImage(W, H, QImage.Format_ARGB32_Premultiplied)
    img.fill(0)
    p = QPainter(img)
    try:
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform, True)

        bars = max(8, min(256, int(eq_ui.get("bars", 96))))
        thick = max(1, min(12, int(eq_ui.get("thickness", 3))))
        eq_h = max(40, min(H, int(eq_ui.get("height", H//3))))
        y_pct = max(-100, min(100, int(eq_ui.get("y_offset", 0))))
        mirror_on = bool(eq_ui.get("mirror", True))
        baseline_on = bool(eq_ui.get("baseline", False))
        color = _qcolor(eq_ui.get("color", "#FFFFFF"))
        alpha_f = _pct_to_alphaf(eq_ui.get("opacity", 90))

        baseline_y = int((H/2) + (H/2)*(y_pct/100.0))
        y_top_up = max(0, min(H - eq_h, baseline_y - eq_h))

        # пен
        col = QColor(color)
        col.setAlphaF(alpha_f)
        pen = QPen(col, thick, Qt.SolidLine, Qt.SquareCap, Qt.MiterJoin)
        p.setPen(pen)

        # вибір режиму
        mode = str(eq_ui.get("mode", "bar")).lower()
        rnd = random.Random(0xBADBEEF ^ (bars<<2) ^ (W<<1) ^ (H<<3))

        def gen_vals(n: int) -> List[float]:
            # синтетика «звук» — шум + рівна огинаюча
            return [0.25 + 0.75*rnd.random() for _ in range(n)]

        vals = gen_vals(bars)
        
        if mode == "line":
            prev_pt = QPoint(0, y_top_up + eq_h)
            xw = W / bars
            for i, v in enumerate(vals):
                h = int(eq_h * v)
                x = int(i * xw)
                y1 = y_top_up + (eq_h - h)
                if i > 0:
                    p.drawLine(prev_pt, QPoint(x, y1))
                prev_pt = QPoint(x, y1)
                
        elif mode == "dot":
            xw = W / bars
            for i, v in enumerate(vals):
                h = int(eq_h * v)
                x = int(i * xw)
                y1 = y_top_up + (eq_h - h)
                p.fillRect(x, y1, max(2, thick), max(2, thick), QBrush(col))
                
        else:  # mode == "bar"
            xw = W / bars
            for i, v in enumerate(vals):
                h = int(eq_h * v)
                x = int(i * xw)
                p.fillRect(x, y_top_up + (eq_h - h), max(1, int(xw)-1), h, QBrush(col))

        if mirror_on:
            if mode == "line":
                prev_pt = QPoint(0, baseline_y)
                xw = W / bars
                for i, v in enumerate(vals):
                    h = int(eq_h * v)
                    x = int(i * xw)
                    y1 = baseline_y + int(eq_h * v)
                    if i > 0:
                        p.drawLine(prev_pt, QPoint(x, y1))
                    prev_pt = QPoint(x, y1)
                    
            elif mode == "dot":
                xw = W / bars
                for i, v in enumerate(vals):
                    h = int(eq_h * v)
                    x = int(i * xw)
                    y1 = baseline_y + int(eq_h * v)
                    p.fillRect(x, y1, max(2, thick), max(2, thick), QBrush(col))
                    
            else:  # mode == "bar"
                xw = W / bars
                for i, v in enumerate(vals):
                    h = int(eq_h * v)
                    x = int(i * xw)
                    p.fillRect(x, baseline_y, max(1, int(xw)-1), h, QBrush(col))

        if baseline_on:
            bl = QColor("#FFFFFF")
            bl.setAlphaF(min(1.0, alpha_f * 0.6))
            p.fillRect(0, max(1, min(H-2, baseline_y)), W, 1, bl)
    finally:
        p.end()
    return QPixmap.fromImage(img)

# -------------------- Зірки (превʼю) --------------------

def make_stars_overlay(stars_ui: Dict, W: int, H: int) -> QPixmap:
    if not stars_ui.get("enabled", False):
        pm = QPixmap(W, H)
        pm.fill(Qt.transparent)
        return pm

    cnt = max(0, int(stars_ui.get("count", 600)))
    size = max(1, int(stars_ui.get("size", 2)))
    col = _qcolor(stars_ui.get("color", "#FFFFFF"))
    opf = _pct_to_alphaf(stars_ui.get("opacity", 85))

    img = QImage(W, H, QImage.Format_ARGB32_Premultiplied)
    img.fill(0)
    p = QPainter(img)
    try:
        rnd = random.Random(0xFEEDFACE ^ (W<<1) ^ (H<<2) ^ (cnt<<3))
        for _ in range(cnt):
            x = rnd.randint(0, W-1)
            y = rnd.randint(0, H-1)
            s = size + rnd.randint(0, max(1, size//2))
            c = QColor(col)
            c.setAlphaF(opf)
            p.fillRect(x, y, s, s, QBrush(c))
            if s <= 5:
                c2 = QColor(c)
                c2.setAlpha(max(70, int(155 - 20*s)))
                p.fillRect(x - 2*s, y + s//2, 4*s, 1, c2)
                p.fillRect(x + s//2, y - 2*s, 1, 4*s, c2)
    finally:
        p.end()
    return QPixmap.fromImage(img)

# -------------------- Дощ (превʼю) --------------------

def make_rain_overlay(rain_ui: Dict, W: int, H: int) -> QPixmap:
    if not rain_ui.get("enabled", False):
        pm = QPixmap(W, H)
        pm.fill(Qt.transparent)
        return pm

    cnt = max(0, int(rain_ui.get("count", 1000)))
    L = max(5, int(rain_ui.get("length", 40)))
    thick = max(1, int(rain_ui.get("thickness", 2)))
    angle = float(rain_ui.get("angle_deg", 15.0))
    col = _qcolor(rain_ui.get("color", "#9BE2FF"))
    opf = _pct_to_alphaf(rain_ui.get("opacity", 55))

    img = QImage(W, H, QImage.Format_ARGB32_Premultiplied)
    img.fill(0)
    p = QPainter(img)
    try:
        p.setRenderHint(QPainter.Antialiasing, True)
        c = QColor(col)
        c.setAlphaF(opf)
        pen = QPen(c, thick, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        p.setPen(pen)

        rnd = random.Random(0x5151DEAD ^ (W<<1) ^ (H<<2))
        dx = int(L * math.cos(math.radians(angle)))
        dy = int(L * math.sin(math.radians(angle))) + 1
        for _ in range(cnt):
            x = rnd.randint(-W//4, W + W//4)
            y = rnd.randint(-H//4, H + H//4)
            p.drawLine(x, y, x + dx, y + dy)
    finally:
        p.end()
    return QPixmap.fromImage(img)

# -------------------- Дим (превʼю) --------------------

def make_smoke_overlay(sm_ui: Dict, W: int, H: int) -> QPixmap:
    if not sm_ui.get("enabled", False):
        pm = QPixmap(W, H)
        pm.fill(Qt.transparent)
        return pm

    density = max(0, int(sm_ui.get("density", 60)))
    col = _qcolor(sm_ui.get("color", "#A0A0A0"))
    opf = _pct_to_alphaf(sm_ui.get("opacity", 35))

    img = QImage(W, H, QImage.Format_ARGB32_Premultiplied)
    img.fill(0)
    p = QPainter(img)
    try:
        p.setRenderHint(QPainter.Antialiasing, True)
        rnd = random.Random(0xC0FFEE ^ (W<<1) ^ (H<<2))
        for _ in range(density):
            x = rnd.randint(0, W-1)
            y = rnd.randint(0, H-1)
            r = rnd.randint(12, 64)
            grad = QRadialGradient(x, y, r)
            c1 = QColor(col)
            c1.setAlphaF(opf * 0.25)
            c2 = QColor(col)
            c2.setAlphaF(0.0)
            grad.setColorAt(0.0, c1)
            grad.setColorAt(1.0, c2)
            p.setBrush(QBrush(grad))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPoint(x, y), r, r)
    finally:
        p.end()
    return QPixmap.fromImage(img)

# -------------------- Motion indicator (превʼю) --------------------

def draw_motion_indicator(p: QPainter, rect: QRect, mv_ui: Dict):
    if not mv_ui.get("enabled", False): 
        return
        
    try:
        p.save()
        p.setRenderHint(QPainter.Antialiasing, True)
        c = QColor("#00E0FF")
        c.setAlpha(180)
        p.setPen(QPen(c, 2))

        direction = str(mv_ui.get("direction", "lr"))
        if direction in ("lr", "rl"):
            y = rect.center().y()
            p.drawLine(10, y, rect.width()-10, y)
        elif direction in ("up", "down"):
            x = rect.center().x()
            p.drawLine(x, 10, x, rect.height()-10)
        elif direction in ("zin", "zout"):
            x0, y0 = rect.center().x()-40, rect.center().y()-30
            p.drawRect(x0, y0, 80, 60)
        elif direction == "rotate":
            r = min(rect.width(), rect.height())//3
            p.drawEllipse(rect.center(), r, r)
        elif direction == "shake":
            for i in range(6):
                y = rect.center().y() - 20 + i*8
                p.drawLine(20, y, rect.width()-20, y)
    finally:
        p.restore()