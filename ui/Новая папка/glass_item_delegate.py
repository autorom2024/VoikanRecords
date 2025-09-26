# -*- coding: utf-8 -*-
from __future__ import annotations

from PySide6.QtCore import Qt, QRectF, QSize, QMargins
from PySide6.QtGui import (
    QPainter, QColor, QLinearGradient, QRadialGradient,
    QFont, QPen, QIcon
)
from PySide6.QtWidgets import QStyledItemDelegate, QListView, QStyle, QStyleOptionViewItem

# === Style tuned to match the reference exactly ===
ITEM_HEIGHT = 68
RADIUS      = 16
PLATE_SIZE  = 40
ICON_SIZE   = 36
FONT_FAMILY = "Segoe UI"
FONT_PT     = 14

# Base glass
BASE_CLR = QColor(18, 22, 28)
BASE_A_N = 205   # normal
BASE_A_H = 215   # hover
BASE_A_S = 235   # selected (slightly darker/denser)

# Tint inside glass (very subtle)
TINT_A_N = 40
TINT_A_H = 64
TINT_A_S = 80

# Outline
OUT_A_N = 70
OUT_A_H = 120
OUT_A_S = 220
OUT_W_N = 1.4
OUT_W_S = 2.0

# Outer neon bloom around the ring (additive)
GLOW_A_N = 55
GLOW_A_H = 120
GLOW_A_S = 210
GLOW_RAD = 1.10


def _accent_for(label: str) -> QColor:
    t = (label or "").lower()
    if "suno" in t or "аудіо" in t or "audio" in t:
        return QColor(112, 88, 255)   # violet/blue
    if "photo" in t or "фото" in t or "vertex" in t:
        return QColor(35, 198, 210)   # cyan
    if "youtube" in t or "монтаж" in t or "video" in t:
        return QColor(255, 72, 72)    # red
    if "планер" in t or "planner" in t:
        return QColor(80, 140, 255)   # blue
    if "autofill" in t:
        return QColor(168, 85, 247)   # purple
    return QColor(120, 140, 255)


class GlassItemDelegate(QStyledItemDelegate):
    """Neon glass tile: dark plane, glossy top, thin neon ring + soft outer glow.
    Exact visual match to reference. Pure painting; logic untouched.
    """

    def __init__(self, parent: QListView | None = None, card_radius: int = RADIUS):
        super().__init__(parent)
        self.radius = card_radius
        try:
            print("GLASS_REF v1:", __file__)
        except Exception:
            pass

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:
        return QSize(option.rect.width(), ITEM_HEIGHT)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        painter.save(); painter.setRenderHint(QPainter.Antialiasing, True)

        rect  = option.rect.marginsRemoved(QMargins(10, 8, 10, 8))
        isSel = bool(option.state & QStyle.State_Selected)
        isHo  = bool(option.state & QStyle.State_MouseOver)

        label = index.data(Qt.DisplayRole) or ""
        icon  = index.data(Qt.DecorationRole)
        accent = _accent_for(label)

        # 1) Dark glass plane
        base = QColor(BASE_CLR)
        base.setAlpha(BASE_A_S if isSel else (BASE_A_H if isHo else BASE_A_N))
        painter.setPen(Qt.NoPen); painter.setBrush(base)
        painter.drawRoundedRect(QRectF(rect), self.radius, self.radius)

        # 2) Subtle accent tint inside (very low alpha)
        tint = QColor(accent); tint.setAlpha(TINT_A_S if isSel else (TINT_A_H if isHo else TINT_A_N))
        painter.setBrush(tint)
        painter.drawRoundedRect(QRectF(rect), self.radius, self.radius)

        # 3) Soft top gloss
        gloss = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        gloss.setColorAt(0.0, QColor(255,255,255,32))
        gloss.setColorAt(0.55, QColor(255,255,255,12))
        gloss.setColorAt(1.0, QColor(255,255,255,0))
        painter.setBrush(gloss)
        painter.drawRoundedRect(QRectF(rect).adjusted(0,0,0,-1), self.radius, self.radius)

        # 4) Neon ring (thin stroke)
        ring = QRectF(rect).adjusted(1.0, 1.0, -1.0, -1.0)
        out  = QColor(accent); out.setAlpha(OUT_A_S if isSel else (OUT_A_H if isHo else OUT_A_N))
        painter.setBrush(Qt.NoBrush); painter.setPen(QPen(out, OUT_W_S if isSel else OUT_W_N))
        painter.drawRoundedRect(ring, self.radius-1, self.radius-1)

        # 5) Outer bloom (additive)
        painter.save(); painter.setCompositionMode(QPainter.CompositionMode_Plus)
        a = GLOW_A_S if isSel else (GLOW_A_H if isHo else GLOW_A_N)
        if a > 0:
            g = QRadialGradient(rect.center(), max(rect.width(), rect.height()) * GLOW_RAD)
            c = QColor(accent); c.setAlpha(a)
            g.setColorAt(0.0, c)
            g.setColorAt(0.8, QColor(c.red(), c.green(), c.blue(), int(a*0.25)))
            g.setColorAt(1.0, QColor(0,0,0,0))
            painter.setBrush(g); painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(QRectF(rect).adjusted(-8,-8,8,8), self.radius+8, self.radius+8)
        painter.restore()

        # 6) Icon plate (subtle glass square)
        icon_box  = rect.marginsRemoved(QMargins(14, 12, 14, 12))
        plateRect = QRectF(icon_box.left(), icon_box.center().y()-PLATE_SIZE/2, PLATE_SIZE, PLATE_SIZE)
        plate = QLinearGradient(plateRect.topLeft(), plateRect.bottomLeft())
        plate.setColorAt(0.0, QColor(255,255,255,22))
        plate.setColorAt(1.0, QColor(255,255,255,8))
        painter.setPen(Qt.NoPen); painter.setBrush(plate)
        painter.drawRoundedRect(plateRect, 10, 10)

        # 7) Icon (larger, crisp), slight additive glow
        if isinstance(icon, QIcon) and not icon.isNull():
            pm = icon.pixmap(ICON_SIZE, ICON_SIZE, QIcon.Active if (isSel or isHo) else QIcon.Normal)
            painter.save(); painter.setCompositionMode(QPainter.CompositionMode_Plus)
            ig = QColor(accent); ig.setAlpha(100 if isSel else (70 if isHo else 40))
            painter.setPen(ig)
            painter.drawPixmap(int(plateRect.left()+2), int(plateRect.top()+2), pm)
            painter.restore()
            painter.drawPixmap(int(plateRect.left()+2), int(plateRect.top()+2), pm)

        # 8) Text with small bloom
        txt = QRectF(plateRect.right()+14, rect.top(), rect.width()-(plateRect.width()+14+16), rect.height())
        font = painter.font(); font.setFamily(FONT_FAMILY); font.setPointSize(FONT_PT); font.setBold(True)
        painter.setFont(font)
        painter.save(); painter.setCompositionMode(QPainter.CompositionMode_Plus)
        tg = QColor(accent); tg.setAlpha(110 if isSel else (70 if isHo else 40))
        painter.setPen(tg); painter.drawText(txt.adjusted(0,1,0,1), Qt.AlignVCenter | Qt.AlignLeft, label)
        painter.restore()
        painter.setPen(QColor(242,246,252) if (isSel or isHo) else QColor(225,229,235))
        painter.drawText(txt, Qt.AlignVCenter | Qt.AlignLeft, label)

        painter.restore()
