"""
캘리브레이션 다이얼로그
  [판] 탭: 빈 판을 비추고 그리드 검출 -> calib/grid_H.npy 저장
  [돌] 탭: 빈 판 기준 저장, 돌을 놓고 클릭으로 라벨링 -> 학습 -> calib/stone_thresholds.json
"""
import os

import numpy as np
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton,
                               QTabWidget, QVBoxLayout, QWidget)

from gui.widgets.camera_view import ImageLabel, draw_recognition
from utils.config import board_geometry, project_path, warp_size
from vision.board_detect import (apply_warp, detect_grid, draw_grid_overlay,
                                 draw_warped_points, warp_matrix)
from vision.stone_classifier import StoneClassifier, grid_to_text


class CalibrationDialog(QDialog):
    calibration_changed = Signal()

    def __init__(self, cfg, get_frame, parent=None):
        super().__init__(parent)
        self.setWindowTitle('캘리브레이션')
        self.resize(1000, 620)
        self.cfg, self.get_frame = cfg, get_frame
        self.n, self.cell, self.margin = board_geometry(cfg)
        self.size = warp_size(cfg)
        self.W = None
        self.changed = False

        tabs = QTabWidget()
        tabs.addTab(self._board_tab(), '① 판 (그리드)')
        tabs.addTab(self._stone_tab(), '② 돌 판별')
        btn_close = QPushButton('닫기')
        btn_close.clicked.connect(self.accept)
        lay = QVBoxLayout(self)
        lay.addWidget(tabs)
        lay.addWidget(btn_close)

        path = project_path(cfg['paths']['grid_H'])
        if os.path.exists(path):
            self.W = np.load(path)

    # ───────── ① 판 ─────────
    def _board_tab(self):
        w = QWidget()
        self.b_orig = ImageLabel('빈 판을 카메라에 비추고 [그리드 검출]을 누르세요')
        self.b_warp = ImageLabel('')
        self.b_info = QLabel('')
        btn_detect = QPushButton('그리드 검출')
        self.btn_save_board = QPushButton('저장')
        self.btn_save_board.setEnabled(False)
        btn_detect.clicked.connect(self._detect)
        self.btn_save_board.clicked.connect(self._save_board)

        imgs = QHBoxLayout()
        imgs.addWidget(self.b_orig, 3)
        imgs.addWidget(self.b_warp, 2)
        btns = QHBoxLayout()
        btns.addWidget(btn_detect)
        btns.addWidget(self.btn_save_board)
        btns.addWidget(self.b_info, 1)
        lay = QVBoxLayout(w)
        lay.addLayout(imgs, 1)
        lay.addLayout(btns)
        return w

    def _detect(self):
        frame = self.get_frame()
        if frame is None:
            self.b_info.setText('카메라 프레임 없음')
            return
        try:
            pts, M, found = detect_grid(frame, self.n)
        except Exception as e:
            self.b_info.setText(f'검출 실패: {e}')
            self.btn_save_board.setEnabled(False)
            return
        self._new_W = warp_matrix(M, self.cell, self.margin)
        warped = apply_warp(frame, self._new_W, self.size)
        self.b_orig.set_image(draw_grid_overlay(frame, pts))
        self.b_warp.set_image(draw_warped_points(warped, self.n, self.cell, self.margin))
        msg = f'교차점 {found}/{self.n * self.n}개 검출.'
        if found < self.n * self.n * 0.7:
            msg += ' ⚠ 너무 적음: 판 전체가 보이는지, 돌/손이 없는지 확인'
        else:
            msg += ' 빨간 점이 선 교차점과 맞으면 [저장]'
        self.b_info.setText(msg)
        self.btn_save_board.setEnabled(True)

    def _save_board(self):
        path = project_path(self.cfg['paths']['grid_H'])
        os.makedirs(os.path.dirname(path), exist_ok=True)
        np.save(path, self._new_W)
        self.W = self._new_W
        self.changed = True
        self.b_info.setText(f'저장 완료: {path}')

    # ───────── ② 돌 ─────────
    def _stone_tab(self):
        w = QWidget()
        self.clf = StoneClassifier.from_config(self.cfg)
        self.labels = np.zeros((self.n, self.n), int)
        self.samples = []
        self.s_warped = None

        self.s_img = ImageLabel('[화면 가져오기]를 누르세요')
        self.s_img.clicked.connect(self._on_click)
        self.s_info = QLabel()
        self.s_info.setWordWrap(True)
        self._update_stone_info()

        help_ = QLabel(
            '1) 돌이 없는 빈 판에서 [빈 판 기준 저장]\n'
            '2) 흑돌·백돌을 여러 칸에 놓고 [화면 가져오기]\n'
            '3) 이미지에서 교차점 클릭: 왼쪽 클릭 = 빈칸→흑→백 순환, 오른쪽 클릭 = 빈칸\n'
            '4) [샘플 추가] (돌 위치를 바꿔 2~4를 몇 번 반복하면 더 정확)\n'
            '5) [학습 + 저장] → [인식 테스트]로 확인')
        btns = [('화면 가져오기', self._grab), ('빈 판 기준 저장', self._set_reference),
                ('샘플 추가', self._add_sample), ('학습 + 저장', self._fit_save),
                ('인식 테스트', self._test), ('기본 규칙으로 초기화', self._reset_model)]
        col = QVBoxLayout()
        col.addWidget(help_)
        for text, fn in btns:
            b = QPushButton(text)
            b.clicked.connect(fn)
            col.addWidget(b)
        col.addWidget(self.s_info)
        col.addStretch(1)

        lay = QHBoxLayout(w)
        lay.addWidget(self.s_img, 3)
        lay.addLayout(col, 2)
        return w

    def _current_warped(self):
        if self.W is None:
            QMessageBox.warning(self, '알림', '먼저 ① 판 캘리브레이션을 저장하세요')
            return None
        frame = self.get_frame()
        if frame is None:
            return None
        return apply_warp(frame, self.W, self.size)

    def _grab(self):
        self.s_warped = self._current_warped()
        if self.s_warped is not None:
            self.labels = self.clf.classify(self.s_warped)     # 현재 인식 결과로 시작 -> 틀린 칸만 고치면 됨
            self._redraw()

    def _on_click(self, x, y, btn):
        if self.s_warped is None:
            return
        c = int(round((x - self.margin) / self.cell))
        r = int(round((y - self.margin) / self.cell))
        if 0 <= r < self.n and 0 <= c < self.n:
            self.labels[r, c] = 0 if btn == 2 else (self.labels[r, c] + 1) % 3
            self._redraw()

    def _redraw(self):
        self.s_img.set_image(draw_recognition(self.s_warped, self.labels,
                                              self.n, self.cell, self.margin))

    def _set_reference(self):
        warped = self._current_warped()
        if warped is None:
            return
        self.clf.set_reference(warped)
        self.samples.clear()
        self._save_model()
        self.s_info.setText('빈 판 기준 저장 완료. 이제 돌을 놓고 샘플을 추가하세요.')

    def _add_sample(self):
        if self.s_warped is None:
            return
        self.samples.append((self.s_warped.copy(), self.labels.copy()))
        b, wh = int((self.labels == 1).sum()), int((self.labels == 2).sum())
        self.s_info.setText(f'샘플 {len(self.samples)}개 (이번 샘플: 흑 {b}, 백 {wh})')

    def _fit_save(self):
        if not self.samples:
            QMessageBox.information(self, '알림', '샘플을 먼저 추가하세요')
            return
        self.clf.fit_many(self.samples)
        self._save_model()
        self._update_stone_info()

    def _test(self):
        warped = self._current_warped()
        if warped is None:
            return
        self.s_warped = warped
        self.labels = self.clf.classify(warped)
        self._redraw()
        self.s_info.setText('인식 결과:\n' + grid_to_text(self.labels))

    def _reset_model(self):
        path = project_path(self.cfg['paths']['stone_model'])
        if os.path.exists(path):
            os.remove(path)
        self.clf = StoneClassifier.from_config(self.cfg)
        self.samples.clear()
        self.changed = True
        self._update_stone_info()

    def _save_model(self):
        self.clf.save(project_path(self.cfg['paths']['stone_model']))
        self.changed = True

    def _update_stone_info(self):
        m = self.clf.model
        if 'centroids' in m:
            txt = f'학습된 모델 사용 중 (클래스별 샘플 수: {m.get("counts")})'
        else:
            txt = '기본 규칙 사용 중'
        if 'reference' in m:
            txt += ' · 빈 판 기준 있음'
        self.s_info.setText(txt)

    def done(self, r):
        if self.changed:
            self.calibration_changed.emit()
        super().done(r)
