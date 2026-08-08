# -*- coding: utf-8 -*-
"""爱心入口悬浮球：屏幕上显示一颗呼吸的爱心，单击切换显示/隐藏操作面板。"""
import time

from PyQt5.QtCore import QPointF, Qt, QTimer
from PyQt5.QtGui import QColor, QLinearGradient, QPainter, QPainterPath
from PyQt5.QtWidgets import QWidget


class HeartEntry(QWidget):
    """一颗悬浮在屏幕上的爱心小球：单击 = 开关操作面板；按住可拖动位置。"""

    def __init__(self, parent=None, size=52, on_click=None):
        super().__init__(parent)
        self._size = size
        self._on_click = on_click
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(size, size)
        self._beat_t = 0.0
        self._drag = None
        self._scale = 1.0

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._beat)
        self._timer.start(33)

        self._path = None  # 预生成心形路径（缓存）
        self._make_path()

    def _make_path(self):
        """经典心形贝塞尔曲线，居中于控件。"""
        s = self._size
        path = QPainterPath()
        # 心形（px 单位）
        path.moveTo(s * 0.5, s * 0.86)
        path.cubicTo(s * 0.05, s * 0.55, s * 0.12, s * 0.16, s * 0.5, s * 0.30)
        path.cubicTo(s * 0.88, s * 0.16, s * 0.95, s * 0.55, s * 0.5, s * 0.86)
        self._path = path

    def _beat(self):
        """心跳节奏：1.4s 周期，跳两下。"""
        now = time.time()
        self._t0 = getattr(self, "_t0", now)
        t = (now - self._t0) % 1.4
        if t < 0.15:
            self._scale = 1.0 + 0.10 * (t / 0.15)
        elif t < 0.35:
            self._scale = 1.1 - 0.06 * ((t - 0.15) / 0.2)
        elif t < 0.5:
            self._scale = 1.04 + 0.06 * ((t - 0.35) / 0.15)
        else:
            self._scale = 1.10 - 0.10 * ((t - 0.5) / 0.9)
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        c = w / 2.0
        sc = self._scale
        g = QLinearGradient(0, 0, 0, h)
        g.setColorAt(0.0, QColor(255, 120, 160, 235))
        g.setColorAt(1.0, QColor(235, 60, 100, 235))
        p.save()
        p.translate(c, h * 0.5)
        p.scale(sc, sc)
        p.translate(-c, -h * 0.5)
        p.setPen(QColor(255, 255, 255, 60))
        p.setBrush(g)
        p.drawPath(self._path)
        # 高光
        hl = QPainterPath()
        hl.addEllipse(QPointF(w * 0.36, h * 0.20), w * 0.13, h * 0.09)
        p.setBrush(QColor(255, 255, 255, 110))
        p.setPen(Qt.NoPen)
        p.drawPath(hl)
        p.restore()
        p.end()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_t = e.globalPos() - self.frameGeometry().topLeft()
            self._drag_start = e.globalPos()
            self._drag_moved = False

    def mouseMoveEvent(self, e):
        if self._drag_t is not None and (e.buttons() & Qt.LeftButton):
            if (e.globalPos() - self._drag_start).manhattanLength() > 5:
                self._drag_moved = True
            if self._drag_moved:
                self.move(e.globalPos() - self._drag_t)

    def mouseReleaseEvent(self, e):
        if self._drag_t is not None and e.button() == Qt.LeftButton:
            moved = self._drag_moved
            self._drag_t = None
            if not moved and self._on_click is not None:
                self._on_click()

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton:
            if self._on_click is not None:
                self._on_click()