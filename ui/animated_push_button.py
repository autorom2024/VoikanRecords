# -*- coding: utf-8 -*-
from __future__ import annotations

from PySide6.QtCore import (Qt, QPointF, QRect, QRectF, QEasingCurve, QPropertyAnimation,
                            QParallelAnimationGroup, Property, QObject)
from PySide6.QtGui import (QPainter, QColor, QLinearGradient, QRadialGradient, QIcon, QPen, QFontMetrics)
from PySide6.QtWidgets import QPushButton, QGraphicsDropShadowEffect


class _Ripple(QObject):
    def __init__(self, parent: 'AnimatedPushButton', center: QPointF, max_radius: float):
        super().__init__(parent)
        self._radius = 0.0
        self._opacity = 0.35
        self.center = QPointF(center)
        self.max_radius = float(max_radius)

    def _get_radius(self) -> float: return self._radius
    def _set_radius(self, v: float) -> None:
        self._radius = float(v); self.parent().update()
    radius = Property(float, _get_radius, _set_radius)

    def _get_opacity(self) -> float: return self._opacity
    def _set_opacity(self, v: float) -> None:
        self._opacity = float(v); self.parent().update()
    opacity = Property(float, _get_opacity, _set_opacity)


class AnimatedPushButton(QPushButton):
    """
    Скляна сучасна кнопка з анімаціями:
      - hover підсвіт, тінь і зовнішнє свічення (glow)
      - ripple-ефект при кліку
      - мікро-сквіз на натисканні
    Кольори визначаються за objectName:
      * "startBtn" -> зелена
      * "stopBtn"  -> червона
      * інші       -> нейтральна (синьо-сірий)
    """
    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)

        # Прибираємо дефолтний малюнок стилю (щоб QSS не перекривав фон)
        self.setStyleSheet("QPushButton { border: 0; background: transparent; padding: 0; }")
        self.setCursor(Qt.PointingHandCursor)
        self.setCheckable(False)

        self._hover = 0.0
        self._orig_geom = None
        self._ripples: list[_Ripple] = []

        # Тінь
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(18)
        self._shadow.setOffset(0, 6)
        self._shadow.setColor(QColor(0, 0, 0, 150))
        self.setGraphicsEffect(self._shadow)

        # === ВИПРАВЛЕНО: Додано 'self' як батьківський елемент для всіх анімацій ===
        # Анімації
        self._hover_anim = QPropertyAnimation(self, b"hoverProgress", self)
        self._hover_anim.setDuration(180)
        self._hover_anim.setEasingCurve(QEasingCurve.OutCubic)

        self._shadow_anim = QPropertyAnimation(self._shadow, b"blurRadius", self)
        self._shadow_anim.setDuration(200)
        self._shadow_anim.setEasingCurve(QEasingCurve.OutCubic)

        self._geom_anim = QPropertyAnimation(self, b"geometry", self)
        self._geom_anim.setDuration(110)
        self._geom_anim.setEasingCurve(QEasingCurve.OutQuad)

    # --- properties ---
    def getHover(self) -> float: return self._hover
    def setHover(self, v: float) -> None: self._hover = float(v); self.update()
    hoverProgress = Property(float, getHover, setHover)

    # --- colors ---
    def _variant_colors(self) -> tuple[QColor, QColor]:
        name = (self.objectName() or "").lower()
        if name == "startbtn":
            return QColor("#16A34A"), QColor("#22C55E")  # green
        if name == "stopbtn":
            return QColor("#DC2626"), QColor("#EF4444")  # red
        return QColor("#334155"), QColor("#3B82F6")      # neutral accent

    # --- events ---
    def enterEvent(self, e):
        self._hover_anim.stop(); self._hover_anim.setStartValue(self._hover); self._hover_anim.setEndValue(1.0); self._hover_anim.start()
        self._shadow_anim.stop(); self._shadow_anim.setStartValue(self._shadow.blurRadius()); self._shadow_anim.setEndValue(26); self._shadow_anim.start()
        self._shadow.setOffset(0, 10)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover_anim.stop(); self._hover_anim.setStartValue(self._hover); self._hover_anim.setEndValue(0.0); self._hover_anim.start()
        self._shadow_anim.stop(); self._shadow_anim.setStartValue(self._shadow.blurRadius()); self._shadow_anim.setEndValue(18); self._shadow_anim.start()
        self._shadow.setOffset(0, 6)
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        # ripple
        center = QPointF(e.position()) if hasattr(e, "position") else QPointF(e.pos())
        max_r = (self.rect().width()**2 + self.rect().height()**2) ** 0.5 * 0.6
        rip = _Ripple(self, center, max_r)
        self._ripples.append(rip)

        a1 = QPropertyAnimation(rip, b"radius"); a1.setDuration(360); a1.setStartValue(0.0); a1.setEndValue(max_r); a1.setEasingCurve(QEasingCurve.OutCubic)
        a2 = QPropertyAnimation(rip, b"opacity"); a2.setDuration(360); a2.setStartValue(0.35); a2.setEndValue(0.0); a2.setEasingCurve(QEasingCurve.OutQuad)
        grp = QParallelAnimationGroup(self); grp.addAnimation(a1); grp.addAnimation(a2)
        grp.finished.connect(lambda: (self._ripples.remove(rip) if rip in self._ripples else None, self.update()))
        grp.start()

        # micro-squeeze
        self._orig_geom = self.geometry()
        shrink = QRect(self._orig_geom.x() + 2, self._orig_geom.y() + 2, self._orig_geom.width() - 4, self._orig_geom.height() - 4)
        self._geom_anim.stop(); self._geom_anim.setStartValue(self._orig_geom); self._geom_anim.setEndValue(shrink); self._geom_anim.start()

        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        if self._orig_geom:
            self._geom_anim.stop(); self._geom_anim.setStartValue(self.geometry()); self._geom_anim.setEndValue(self._orig_geom); self._geom_anim.start()
        super().mouseReleaseEvent(e)

    # --- painting ---
    def paintEvent(self, _e):
        r = self.rect().adjusted(1, 1, -1, -1)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        base, accent = self._variant_colors()

        # base glass
        bg = QColor(20, 24, 30, 225)                       # dark panel
        tint = QColor(accent); tint.setAlphaF(0.22 + 0.18 * self._hover)
        if self.isDown() and self.isEnabled():
            bg = QColor(14, 16, 22, 235)
            tint.setAlpha(min(255, int(tint.alpha() + 20)))

        if not self.isEnabled():
            base = QColor("#6B7280"); accent = QColor("#9CA3AF"); tint = QColor(120, 120, 120, 60)

        painter.setPen(Qt.NoPen); painter.setBrush(bg)
        painter.drawRoundedRect(QRectF(r), 12, 12)

        painter.setBrush(tint)
        painter.drawRoundedRect(QRectF(r), 12, 12)

        # glossy highlight
        gloss = QLinearGradient(r.topLeft(), r.bottomLeft())
        gloss.setColorAt(0.0, QColor(255, 255, 255, int(30 + 24 * self._hover)))
        gloss.setColorAt(0.55, QColor(255, 255, 255, 10))
        gloss.setColorAt(1.0, QColor(255, 255, 255, 6))
        painter.setBrush(gloss)
        painter.drawRoundedRect(QRectF(r.adjusted(0, 0, 0, -1)), 12, 12)

        # inner stroke
        painter.setPen(QPen(QColor(255, 255, 255, 28 + int(22 * self._hover)), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(QRectF(r.adjusted(0.5, 0.5, -0.5, -0.5)), 11, 11)

        # outer glow on hover
        if self._hover > 0.0 and self.isEnabled():
            g = QRadialGradient(r.center(), max(r.width(), r.height()) * 0.8)
            glow_c = QColor(accent); glow_c.setAlpha(int(80 * self._hover))
            g.setColorAt(0.0, glow_c)
            g.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.setPen(Qt.NoPen); painter.setBrush(g)
            painter.drawRoundedRect(QRectF(r.adjusted(-6, -6, 6, 6)), 16, 16)

        # ripples
        for rip in list(self._ripples):
            rc = QColor(255, 255, 255, int(255 * max(0.0, min(1.0, rip.opacity))))
            painter.setPen(Qt.NoPen); painter.setBrush(rc)
            painter.drawEllipse(rip.center, rip.radius, rip.radius)

        # text (and optional icon)
        painter.setPen(QColor("#FFFFFF"))
        txt = self.text()
        painter.drawText(r, Qt.AlignCenter, txt)

        # focus ring
        if self.hasFocus():
            ring = QPen(QColor(accent), 2)
            ring.setStyle(Qt.DashLine)
            painter.setPen(ring); painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(QRectF(r.adjusted(2, 2, -2, -2)), 9, 9)