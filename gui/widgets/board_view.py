"""확정된 판 상태를 바둑판 그림으로 표시 (마지막 수, AI 수 강조)"""
import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget


class BoardView(QWidget):
    def __init__(self, n=8, parent=None):
        super().__init__(parent)
        self.n = n
        self.grid = np.zeros((n, n), int)
        self.last_move = None
        self.ai_target = None          # 로봇이 놓을 예정인 칸
        self.setMinimumSize(260, 260)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_board(self, grid, last_move=None):
        self.grid = np.asarray(grid).copy()
        self.last_move = last_move
        if last_move is not None and self.ai_target == tuple(last_move):
            self.ai_target = None
        self.update()

    def set_ai_target(self, row, col):
        self.ai_target = (row, col)
        self.update()

    def clear(self):
        self.set_board(np.zeros((self.n, self.n), int))
        self.ai_target = None
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        side = min(self.width(), self.height())
        ox, oy = (self.width() - side) / 2, (self.height() - side) / 2
        margin = side * 0.08
        step = (side - 2 * margin) / (self.n - 1)

        def pt(r, c):
            return QPointF(ox + margin + c * step, oy + margin + r * step)

        p.fillRect(QRectF(ox, oy, side, side), QColor('#e3b878'))
        p.setPen(QPen(QColor('#3b2a14'), 1.5))
        for i in range(self.n):
            p.drawLine(pt(i, 0), pt(i, self.n - 1))
            p.drawLine(pt(0, i), pt(self.n - 1, i))

        # 좌표 숫자
        p.setFont(QFont('Arial', max(7, int(step * 0.22))))
        p.setPen(QColor('#5a4020'))
        for i in range(self.n):
            a = pt(i, 0)
            p.drawText(QPointF(a.x() - margin * 0.75, a.y() + 4), str(i))
            b = pt(0, i)
            p.drawText(QPointF(b.x() - 4, b.y() - margin * 0.45), str(i))

        rad = step * 0.42
        for r in range(self.n):
            for c in range(self.n):
                v = int(self.grid[r, c])
                if not v:
                    continue
                p.setPen(QPen(QColor('#000'), 1))
                p.setBrush(QBrush(QColor('#111') if v == 1 else QColor('#f7f7f7')))
                p.drawEllipse(pt(r, c), rad, rad)

        if self.last_move is not None:
            r, c = self.last_move
            p.setPen(Qt.NoPen)
            p.setBrush(QColor('#e53935'))
            p.drawEllipse(pt(r, c), rad * 0.28, rad * 0.28)

        if self.ai_target is not None:
            r, c = self.ai_target
            pen = QPen(QColor('#1e88e5'), 3, Qt.DashLine)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(pt(r, c), rad, rad)
        p.end()
