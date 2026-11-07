"""카메라 원본 / 보정+인식 결과 화면 (탭)"""
import cv2
import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QLabel, QSizePolicy, QTabWidget


def cv_to_qimage(img):
    """OpenCV BGR 이미지 -> QImage"""
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    rgb = np.ascontiguousarray(rgb)
    h, w, _ = rgb.shape
    return QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888).copy()


def draw_recognition(warped, grid, n, cell, margin):
    """보정 이미지 위에 인식 결과 표시: 흑=빨강 채움, 백=파랑 테두리, 빈칸=작은 회색 점"""
    vis = warped.copy()
    r = int(cell * 0.35)
    for row in range(n):
        for col in range(n):
            c = (margin + col * cell, margin + row * cell)
            v = int(grid[row, col])
            if v == 1:
                cv2.circle(vis, c, r, (0, 0, 255), 3)
            elif v == 2:
                cv2.circle(vis, c, r, (255, 120, 0), 3)
            else:
                cv2.circle(vis, c, 3, (160, 160, 160), -1)
    return vis


class ImageLabel(QLabel):
    """비율을 유지하며 크기에 맞춰 이미지를 그리는 라벨. 클릭 시 원본 이미지 좌표를 알려줌"""
    clicked = Signal(int, int, int)       # x, y (원본 이미지 좌표), 마우스 버튼

    def __init__(self, text='', parent=None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(320, 240)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet('background:#222; color:#aaa;')
        self._pix = None

    def set_image(self, img):
        self._pix = QPixmap.fromImage(cv_to_qimage(img))
        self._update()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._update()

    def _update(self):
        if self._pix is not None:
            self.setPixmap(self._pix.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def mousePressEvent(self, e):
        if self._pix is None or self.pixmap() is None:
            return
        shown = self.pixmap().size()
        ox = (self.width() - shown.width()) / 2
        oy = (self.height() - shown.height()) / 2
        sx = self._pix.width() / shown.width()
        x = (e.position().x() - ox) * sx
        y = (e.position().y() - oy) * sx
        if 0 <= x < self._pix.width() and 0 <= y < self._pix.height():
            btn = 1 if e.button() == Qt.LeftButton else 2
            self.clicked.emit(int(x), int(y), btn)


class CameraView(QTabWidget):
    def __init__(self, n=8, cell=60, margin=40, parent=None):
        super().__init__(parent)
        self.n, self.cell, self.margin = n, cell, margin
        self.raw = ImageLabel('카메라 연결 대기 중…')
        self.warped = ImageLabel('판 캘리브레이션 후 표시됩니다')
        self.addTab(self.raw, '카메라 원본')
        self.addTab(self.warped, '보정 + 인식 결과')

    def show_frame(self, frame):
        self.raw.set_image(frame)

    def show_result(self, res):
        vis = draw_recognition(res.warped, res.grid, self.n, self.cell, self.margin)
        if res.hand:
            cv2.putText(vis, 'HAND', (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
        self.warped.set_image(vis)
