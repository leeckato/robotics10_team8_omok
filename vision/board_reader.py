"""
카메라 프레임 -> '확정된' 판 상태

board_detect(보정) + stone_classifier(돌 판별) + hand_detect(손) 를 묶고,
손이 없고 같은 결과가 stable_frames 프레임 연속일 때만 확정 상태를 돌려줍니다.
"""
import os
from collections import deque
from dataclasses import dataclass, field

import numpy as np

from utils.config import project_path, warp_size
from vision.board_detect import apply_warp
from vision.hand_detect import HandDetector
from vision.stone_classifier import StoneClassifier


@dataclass
class ReadResult:
    warped: np.ndarray            # 보정 이미지
    grid: np.ndarray              # 이번 프레임 인식 결과 (n, n)
    hand: bool                    # 손 감지 여부
    stable: np.ndarray = None     # 확정된 판 (안정화 완료 시에만, 아니면 None)
    stable_count: int = 0         # 현재 같은 결과가 몇 프레임 연속인지
    extras: dict = field(default_factory=dict)


class BoardReader:
    def __init__(self, W, size, classifier, hand_detector, stable_frames=10):
        self.W = W
        self.size = size
        self.classifier = classifier
        self.hand = hand_detector
        self.stable_frames = stable_frames
        self._history = deque(maxlen=stable_frames)
        self._last_stable = None

    @classmethod
    def from_config(cls, cfg):
        path = project_path(cfg['paths']['grid_H'])
        if not os.path.exists(path):
            raise FileNotFoundError(
                f'{path} 가 없습니다. 먼저 판 캘리브레이션을 하세요 '
                '(GUI의 [캘리브레이션] 또는 python tools/calibrate_board.py)')
        W = np.load(path)
        return cls(W, warp_size(cfg), StoneClassifier.from_config(cfg),
                   HandDetector.from_config(cfg), cfg['vision']['stable_frames'])

    def set_matrix(self, W):
        self.W = W
        self.reset()

    def reset(self):
        self._history.clear()
        self._last_stable = None
        self.hand.reference = None

    def process(self, frame):
        warped = apply_warp(frame, self.W, self.size)
        hand = self.hand.detect(warped, frame, self.W)
        grid = self.classifier.classify(warped)

        if hand:
            self._history.clear()           # 손이 있으면 안정화 카운트 초기화
        else:
            self._history.append(grid)

        count = 0
        for g in reversed(self._history):
            if np.array_equal(g, grid):
                count += 1
            else:
                break

        stable = None
        if not hand and count >= self.stable_frames:
            stable = grid.copy()
            if self._last_stable is None or not np.array_equal(stable, self._last_stable):
                self.hand.set_reference(warped)     # 새 확정 상태 = 손 감지 기준
            self._last_stable = stable
        return ReadResult(warped, grid, hand, stable, count)
