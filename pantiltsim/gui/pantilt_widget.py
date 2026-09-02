"""Widget que desenha a unidade Pan-Tilt com antena helicoidal acoplada.

Toda a ilustração é vetorial (QPainter), sem depender de nenhuma imagem
externa. O objetivo é demonstrar visualmente, em tempo real, a mudança de
posição de pan (rotação no eixo vertical) e tilt (rotação no eixo
horizontal), conforme os valores recebidos via RS-485/USB usando o
protocolo do fabricante.

Estratégia de desenho (vista frontal 2D):
    - Um dial tipo "bússola" no canto superior mostra o ângulo de pan
      numericamente e com um ponteiro.
    - O corpo do PTU (base fixa + cabeçote) e a antena helicoidal são
      desenhados com uma leve compressão horizontal proporcional a
      cos(pan) para sugerir a rotação em torno do eixo vertical, e o
      conjunto cabeçote+antena gira de fato (rotação 2D) para representar
      o tilt.
"""

from __future__ import annotations

import math

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QBrush, QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import QWidget


class PanTiltWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.pan_deg = 0.0
        self.tilt_deg = 0.0
        self.pan_target_deg = 0.0
        self.tilt_target_deg = 0.0
        self.in_motion = False
        self.setMinimumSize(360, 360)

    def set_state(self, pan_deg: float, tilt_deg: float, pan_target: float, tilt_target: float, in_motion: bool):
        self.pan_deg = pan_deg
        self.tilt_deg = tilt_deg
        self.pan_target_deg = pan_target
        self.tilt_target_deg = tilt_target
        self.in_motion = in_motion
        self.update()

    # ------------------------------------------------------------------
    def paintEvent(self, event):  # noqa: N802 (nome exigido pelo Qt)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        self._draw_background(painter, w, h)
        self._draw_compass(painter, w - 78, 78, 58)
        self._draw_pantilt_assembly(painter, w * 0.5, h * 0.62, min(w, h))
        self._draw_labels(painter, w, h)

    # ------------------------------------------------------------------
    def _draw_background(self, painter: QPainter, w: int, h: int) -> None:
        gradient = QLinearGradient(0, 0, 0, h)
        gradient.setColorAt(0.0, QColor(24, 30, 38))
        gradient.setColorAt(1.0, QColor(12, 15, 20))
        painter.fillRect(0, 0, w, h, QBrush(gradient))

        floor_y = int(h * 0.86)
        painter.setPen(QPen(QColor(60, 70, 82), 1))
        painter.setBrush(QBrush(QColor(30, 36, 45)))
        painter.drawRect(0, floor_y, w, h - floor_y)

    def _draw_compass(self, painter: QPainter, cx: float, cy: float, radius: float) -> None:
        painter.save()
        painter.setPen(QPen(QColor(90, 100, 115), 1.5))
        painter.setBrush(QBrush(QColor(20, 24, 30, 200)))
        painter.drawEllipse(QPointF(cx, cy), radius, radius)

        painter.setPen(QPen(QColor(70, 80, 95), 1))
        for tick_deg in range(0, 360, 30):
            a = math.radians(tick_deg)
            x1 = cx + (radius - 6) * math.sin(a)
            y1 = cy - (radius - 6) * math.cos(a)
            x2 = cx + radius * math.sin(a)
            y2 = cy - radius * math.cos(a)
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        needle_angle = math.radians(self.pan_deg)
        tip = QPointF(cx + (radius - 10) * math.sin(needle_angle), cy - (radius - 10) * math.cos(needle_angle))
        tail = QPointF(cx - (radius - 10) * 0.3 * math.sin(needle_angle), cy + (radius - 10) * 0.3 * math.cos(needle_angle))
        painter.setPen(QPen(QColor(255, 140, 40), 3))
        painter.drawLine(tail, tip)
        painter.setPen(QPen(QColor(230, 230, 230), 1))
        painter.setBrush(QBrush(QColor(230, 230, 230)))
        painter.drawEllipse(QPointF(cx, cy), 3, 3)

        painter.setPen(QColor(190, 195, 205))
        painter.setFont(QFont("Sans Serif", 8))
        painter.drawText(QRectF(cx - radius, cy + radius + 4, 2 * radius, 16), Qt.AlignCenter, "PAN")
        painter.restore()

    def _draw_pantilt_assembly(self, painter: QPainter, cx: float, base_y: float, scale_ref: float) -> None:
        unit = scale_ref / 360.0  # fator de escala baseado no tamanho do widget

        pan_rad = math.radians(self.pan_deg)
        squeeze = 0.35 + 0.65 * abs(math.cos(pan_rad))

        # --- tripé / base fixa (não gira) ---------------------------------
        leg_span = 70 * unit
        leg_top = QPointF(cx, base_y - 30 * unit)
        painter.setPen(QPen(QColor(80, 88, 100), 4 * unit))
        for dx in (-leg_span, 0, leg_span):
            painter.drawLine(leg_top, QPointF(cx + dx, base_y + 40 * unit))

        painter.setPen(QPen(QColor(70, 78, 90), 1))
        painter.setBrush(QBrush(QColor(55, 62, 72)))
        base_rect = QRectF(cx - 46 * unit, base_y - 46 * unit, 92 * unit, 20 * unit)
        painter.drawRoundedRect(base_rect, 4 * unit, 4 * unit)

        pivot = QPointF(cx, base_y - 46 * unit)

        # --- cabeçote (pan) + antena (tilt), ambos ao redor do pivot ------
        painter.save()
        painter.translate(pivot)
        painter.scale(squeeze, 1.0)
        painter.rotate(-self.tilt_deg)

        head_w, head_h = 64 * unit, 44 * unit
        head_rect = QRectF(-head_w / 2, -head_h - 6 * unit, head_w, head_h)
        head_color = QColor(235, 120, 40) if self.in_motion else QColor(210, 100, 40)
        painter.setPen(QPen(QColor(255, 255, 255, 60), 1))
        painter.setBrush(QBrush(head_color))
        painter.drawRoundedRect(head_rect, 6 * unit, 6 * unit)

        painter.setPen(QPen(QColor(255, 255, 255, 90), 1))
        painter.setBrush(QBrush(QColor(40, 44, 52)))
        painter.drawEllipse(QPointF(0, -6 * unit), 8 * unit, 8 * unit)

        mast_top_y = head_rect.top()
        self._draw_helical_antenna(painter, unit, mast_top_y)

        painter.restore()

    def _draw_helical_antenna(self, painter: QPainter, unit: float, head_top_y: float) -> None:
        mast_height = 130 * unit
        coil_radius = 14 * unit
        turns = 7
        samples_per_turn = 14

        base_pt = QPointF(0, head_top_y)
        top_y = head_top_y - mast_height

        painter.setPen(QPen(QColor(200, 205, 215), 2 * unit))
        painter.drawLine(base_pt, QPointF(0, head_top_y - 12 * unit))

        path = QPainterPath()
        path.moveTo(0, head_top_y - 12 * unit)
        total_samples = turns * samples_per_turn
        for i in range(total_samples + 1):
            t = i / total_samples
            angle = t * turns * 2 * math.pi
            x = coil_radius * math.sin(angle)
            y = (head_top_y - 12 * unit) - t * (mast_height - 12 * unit)
            path.lineTo(x, y)

        painter.setPen(QPen(QColor(255, 200, 90), 2.2 * unit, cap=Qt.RoundCap, join=Qt.RoundJoin))
        painter.drawPath(path)

        painter.setPen(QPen(QColor(255, 220, 140), 1))
        painter.setBrush(QBrush(QColor(255, 220, 140)))
        painter.drawEllipse(QPointF(0, top_y), 3 * unit, 3 * unit)

    def _draw_labels(self, painter: QPainter, w: int, h: int) -> None:
        painter.setPen(QColor(210, 215, 225))
        painter.setFont(QFont("Sans Serif", 10, QFont.Bold))
        text = f"PAN {self.pan_deg:7.2f}°  (alvo {self.pan_target_deg:7.2f}°)"
        painter.drawText(QRectF(10, 10, w - 20, 22), Qt.AlignLeft, text)
        text = f"TILT {self.tilt_deg:7.2f}°  (alvo {self.tilt_target_deg:7.2f}°)"
        painter.drawText(QRectF(10, 32, w - 20, 22), Qt.AlignLeft, text)

        status = "EM MOVIMENTO" if self.in_motion else "PARADO"
        color = QColor(255, 170, 60) if self.in_motion else QColor(120, 220, 140)
        painter.setPen(color)
        painter.drawText(QRectF(10, 54, w - 20, 20), Qt.AlignLeft, status)
