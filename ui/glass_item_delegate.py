# D:\VOIKAN R\ui\glass_item_delegate.py

from __future__ import annotations
from PySide6.QtCore import Qt, QRectF, QSize, QMargins
from PySide6.QtGui import QPainter, QColor, QLinearGradient, QFont, QPen, QIcon
from PySide6.QtWidgets import QStyledItemDelegate, QStyle, QStyleOptionViewItem

ITEM_HEIGHT = 68; RADIUS = 16; ICON_SIZE = 36; FONT_FAMILY = "Segoe UI"; FONT_PT = 14
BASE_CLR = QColor(18, 22, 28); BASE_A_N = 205; BASE_A_H = 215; OUT_A_N = 70; OUT_A_H = 120; OUT_W_N = 1.4

def _accent_for(label: str) -> QColor:
    t = (label or "").lower()
    if "suno" in t or "аудіо" in t: return QColor(80, 140, 255)
    if "фото" in t or "vertex" in t: return QColor(35, 198, 210)
    if "youtube" in t or "монтаж" in t: return QColor(255, 72, 72)
    if "планер" in t: return QColor(112, 88, 255)
    if "autofill" in t: return QColor(168, 85, 247)
    return QColor(120, 140, 255)

class GlassItemDelegate(QStyledItemDelegate):
    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:
        return QSize(option.rect.width(), ITEM_HEIGHT)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        painter.save(); painter.setRenderHint(QPainter.Antialiasing, True)

        rect = option.rect.marginsRemoved(QMargins(10, 8, 10, 8))
        isSel = bool(option.state & QStyle.State_Selected)
        isHo = bool(option.state & QStyle.State_MouseOver)

        label = index.data(Qt.DisplayRole) or ""; icon = index.data(Qt.DecorationRole)
        accent = _accent_for(label)

        if isSel:
            painter.setPen(Qt.NoPen); painter.setBrush(accent)
            painter.drawRoundedRect(QRectF(rect), RADIUS, RADIUS)
            pen_color = QColor("white"); pen_color.setAlpha(150)
            painter.setPen(QPen(pen_color, 1.5)); painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(QRectF(rect).adjusted(1, 1, -1, -1), RADIUS - 1, RADIUS - 1)
        else:
            base = QColor(BASE_CLR); base.setAlpha(BASE_A_H if isHo else BASE_A_N)
            painter.setPen(Qt.NoPen); painter.setBrush(base)
            painter.drawRoundedRect(QRectF(rect), RADIUS, RADIUS)
            gloss = QLinearGradient(rect.topLeft(), rect.bottomLeft())
            gloss.setColorAt(0.0, QColor(255,255,255,32)); gloss.setColorAt(1.0, QColor(255,255,255,0))
            painter.setBrush(gloss); painter.drawRoundedRect(QRectF(rect), RADIUS, RADIUS)
            ring = QRectF(rect).adjusted(1.0, 1.0, -1.0, -1.0)
            out = QColor("white"); out.setAlpha(OUT_A_H if isHo else OUT_A_N)
            painter.setBrush(Qt.NoBrush); painter.setPen(QPen(out, OUT_W_N))
            painter.drawRoundedRect(ring, RADIUS - 1, RADIUS - 1)

        if isinstance(icon, QIcon) and not icon.isNull():
            pm = icon.pixmap(ICON_SIZE, ICON_SIZE)
            icon_rect = QRectF(rect.left() + 14, rect.center().y() - ICON_SIZE/2, ICON_SIZE, ICON_SIZE)
            painter.drawPixmap(icon_rect.topLeft(), pm)
        
        txt_rect = QRectF(rect.left() + 14 + ICON_SIZE + 14, rect.top(), rect.width() - (14 + ICON_SIZE + 14), rect.height())
        font = painter.font(); font.setFamily(FONT_FAMILY); font.setPointSize(FONT_PT); font.setBold(True)
        painter.setFont(font); painter.setPen(QColor(250, 250, 250))
        painter.drawText(txt_rect, Qt.AlignVCenter | Qt.AlignLeft, label)
        
        painter.restore()