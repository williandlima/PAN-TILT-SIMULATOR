"""Widget que exibe a unidade Pan-Tilt com a antena helicoidal acoplada.

O desenho da unidade em si fica em `ptu_render.py` (modelo 3D projetado);
aqui ficam o fundo, os instrumentos de leitura (bússola de pan e arco de
tilt), o alvo comandado e os rótulos de estado.
"""

from __future__ import annotations

import math

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QBrush, QColor, QFont, QLinearGradient, QPainter, QPen
from PyQt5.QtWidgets import QWidget

from . import ptu_render

COLOR_TEXT = QColor(214, 219, 228)
COLOR_DIM = QColor(126, 134, 148)
COLOR_ACCENT = QColor(255, 158, 56)
COLOR_TARGET = QColor(96, 176, 255)
COLOR_IDLE = QColor(118, 214, 142)


class PanTiltWidget(QWidget):
    """Vista principal do simulador: a unidade e seus instrumentos."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pan_deg = 0.0
        self.tilt_deg = 0.0
        self.pan_target_deg = 0.0
        self.tilt_target_deg = 0.0
        self.pan_range = (-159.0, 159.0)
        self.tilt_range = (-90.0, 90.0)
        self.in_motion = False
        self.model_name = "PTU-D300E"
        self.setMinimumSize(420, 420)

    def set_state(self, snapshot: dict) -> None:
        self.pan_deg = snapshot["pan_deg"]
        self.tilt_deg = snapshot["tilt_deg"]
        self.pan_target_deg = snapshot["pan_target_deg"]
        self.tilt_target_deg = snapshot["tilt_target_deg"]
        self.pan_range = snapshot["pan_range_deg"]
        self.tilt_range = snapshot["tilt_range_deg"]
        self.in_motion = snapshot["in_motion"]
        self.model_name = snapshot.get("model", self.model_name)
        self.update()

    # ------------------------------------------------------------------
    def paintEvent(self, event):  # noqa: N802 (assinatura exigida pelo Qt)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        self._draw_background(painter, w, h)
        ptu_render.render(painter, w, h, self.pan_deg, self.tilt_deg)
        self._draw_compass(painter, 74, h - 82, 56)
        self._draw_tilt_gauge(painter, w - 60, h - 82, 56)
        self._draw_labels(painter, w, h)

    # ------------------------------------------------------------------
    def _draw_background(self, painter: QPainter, w: int, h: int) -> None:
        gradient = QLinearGradient(0, 0, 0, h)
        gradient.setColorAt(0.0, QColor(30, 36, 46))
        gradient.setColorAt(0.62, QColor(19, 23, 30))
        gradient.setColorAt(1.0, QColor(13, 16, 21))
        painter.fillRect(0, 0, w, h, QBrush(gradient))

    def _draw_compass(self, painter: QPainter, cx: float, cy: float, radius: float) -> None:
        """Rosa dos ventos com a posição de pan atual e a comandada."""
        painter.save()
        painter.setPen(QPen(QColor(78, 88, 104), 1.4))
        painter.setBrush(QBrush(QColor(16, 20, 27, 210)))
        painter.drawEllipse(QPointF(cx, cy), radius, radius)

        painter.setPen(QPen(QColor(64, 72, 86), 1))
        for tick in range(0, 360, 15):
            a = math.radians(tick)
            inner = radius - (9 if tick % 45 == 0 else 5)
            painter.drawLine(
                QPointF(cx + inner * math.sin(a), cy - inner * math.cos(a)),
                QPointF(cx + radius * math.sin(a), cy - radius * math.cos(a)),
            )

        self._draw_limit_arc(painter, cx, cy, radius - 3, self.pan_range)

        target_angle = math.radians(self.pan_target_deg)
        painter.setPen(QPen(COLOR_TARGET, 1.6, Qt.DashLine))
        painter.drawLine(
            QPointF(cx, cy),
            QPointF(cx + (radius - 8) * math.sin(target_angle), cy - (radius - 8) * math.cos(target_angle)),
        )

        angle = math.radians(self.pan_deg)
        painter.setPen(QPen(COLOR_ACCENT, 3))
        painter.drawLine(
            QPointF(cx - radius * 0.28 * math.sin(angle), cy + radius * 0.28 * math.cos(angle)),
            QPointF(cx + (radius - 10) * math.sin(angle), cy - (radius - 10) * math.cos(angle)),
        )
        painter.setBrush(QBrush(COLOR_TEXT))
        painter.setPen(QPen(COLOR_TEXT, 1))
        painter.drawEllipse(QPointF(cx, cy), 2.6, 2.6)

        painter.setPen(COLOR_DIM)
        painter.setFont(QFont("Sans Serif", 7))
        painter.drawText(QRectF(cx - radius, cy + radius + 2, 2 * radius, 14), Qt.AlignCenter, "PAN")
        painter.restore()

    def _draw_limit_arc(self, painter: QPainter, cx: float, cy: float, radius: float, span: tuple) -> None:
        """Marca a faixa de curso permitida (limites vigentes) no instrumento."""
        low, high = span
        rect = QRectF(cx - radius, cy - radius, 2 * radius, 2 * radius)
        # Qt mede ângulos a partir das 3 horas, no sentido anti-horário, em 1/16°.
        start = int((90 - high) * 16)
        length = int((high - low) * 16)
        painter.setPen(QPen(QColor(96, 176, 255, 90), 3))
        painter.setBrush(Qt.NoBrush)
        painter.drawArc(rect, start, length)

    def _draw_tilt_gauge(self, painter: QPainter, cx: float, cy: float, radius: float) -> None:
        """Arco de elevação mostrando o tilt atual e o comandado."""
        painter.save()
        rect = QRectF(cx - radius, cy - radius, 2 * radius, 2 * radius)
        painter.setPen(QPen(QColor(78, 88, 104), 1.4))
        painter.setBrush(QBrush(QColor(16, 20, 27, 210)))
        painter.drawPie(rect, -90 * 16, 180 * 16)

        low, high = self.tilt_range
        painter.setPen(QPen(QColor(96, 176, 255, 90), 3))
        painter.setBrush(Qt.NoBrush)
        painter.drawArc(rect.adjusted(3, 3, -3, -3), int(low * 16), int((high - low) * 16))

        painter.setPen(QPen(QColor(64, 72, 86), 1))
        for tick in range(-90, 91, 15):
            a = math.radians(tick)
            inner = radius - (9 if tick % 45 == 0 else 5)
            painter.drawLine(
                QPointF(cx + inner * math.cos(a), cy - inner * math.sin(a)),
                QPointF(cx + radius * math.cos(a), cy - radius * math.sin(a)),
            )

        target = math.radians(self.tilt_target_deg)
        painter.setPen(QPen(COLOR_TARGET, 1.6, Qt.DashLine))
        painter.drawLine(
            QPointF(cx, cy),
            QPointF(cx + (radius - 8) * math.cos(target), cy - (radius - 8) * math.sin(target)),
        )

        angle = math.radians(self.tilt_deg)
        painter.setPen(QPen(COLOR_ACCENT, 3))
        painter.drawLine(
            QPointF(cx, cy),
            QPointF(cx + (radius - 10) * math.cos(angle), cy - (radius - 10) * math.sin(angle)),
        )
        painter.setBrush(QBrush(COLOR_TEXT))
        painter.setPen(QPen(COLOR_TEXT, 1))
        painter.drawEllipse(QPointF(cx, cy), 2.6, 2.6)

        painter.setPen(COLOR_DIM)
        painter.setFont(QFont("Sans Serif", 7))
        painter.drawText(QRectF(cx - radius, cy + 6, 2 * radius, 14), Qt.AlignCenter, "TILT")
        painter.restore()

    def _draw_labels(self, painter: QPainter, w: int, h: int) -> None:
        painter.setPen(COLOR_TEXT)
        painter.setFont(QFont("Sans Serif", 12, QFont.Bold))
        painter.drawText(QRectF(14, 10, w - 28, 22), Qt.AlignLeft, self.model_name)

        painter.setFont(QFont("Monospace", 10))
        painter.drawText(QRectF(14, 36, w - 28, 20), Qt.AlignLeft, f"PAN  {self.pan_deg:8.2f}°")
        painter.drawText(QRectF(14, 56, w - 28, 20), Qt.AlignLeft, f"TILT {self.tilt_deg:8.2f}°")

        painter.setPen(COLOR_TARGET)
        painter.setFont(QFont("Monospace", 8))
        painter.drawText(QRectF(14, 78, w - 28, 18), Qt.AlignLeft, f"alvo {self.pan_target_deg:.2f}° / {self.tilt_target_deg:.2f}°")

        painter.setPen(COLOR_ACCENT if self.in_motion else COLOR_IDLE)
        painter.setFont(QFont("Sans Serif", 9, QFont.Bold))
        painter.drawText(
            QRectF(14, 96, w - 28, 18),
            Qt.AlignLeft,
            "EM MOVIMENTO" if self.in_motion else "EM POSIÇÃO",
        )
