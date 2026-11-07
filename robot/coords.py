"""
판 좌표 (row, col) -> 로봇 좌표 (x, y) mm

카메라와 로봇이 '판 좌표'를 공통 언어로 쓰므로 카메라-로봇 캘리브레이션이 필요 없습니다.
tools/calibrate_robot.py 로 로봇팔 끝을 판의 네 모서리 교차점에 맞추고
그 좌표를 저장하면, 나머지 칸은 원근 변환으로 계산됩니다.

calib/robot_board.json 예:
{
  "n": 8,
  "corners": {            # 로봇 좌표 [x, y]
    "0,0": [120.0, 80.0],     # row 0, col 0   (보정 이미지의 좌상단)
    "0,7": [120.0, -80.0],    # row 0, col n-1 (우상단)
    "7,7": [280.0, -80.0],    # row n-1, col n-1 (우하단)
    "7,0": [280.0, 80.0]      # row n-1, col 0 (좌하단)
  }
}
"""
import json
import os

import cv2
import numpy as np


class BoardToRobot:
    def __init__(self, n, corners):
        self.n = n
        keys = ['0,0', f'0,{n - 1}', f'{n - 1},{n - 1}', f'{n - 1},0']
        src = np.float32([[0, 0], [n - 1, 0], [n - 1, n - 1], [0, n - 1]])   # (col, row)
        dst = np.float32([corners[k] for k in keys])
        self.T = cv2.getPerspectiveTransform(src, dst)

    @classmethod
    def load(cls, path):
        with open(path, 'r', encoding='utf-8') as f:
            d = json.load(f)
        return cls(d['n'], d['corners'])

    @classmethod
    def from_config(cls, cfg):
        from utils.config import project_path
        path = project_path(cfg['paths']['robot_board'])
        if not os.path.exists(path):
            raise FileNotFoundError(
                f'{path} 가 없습니다. 먼저 python tools/calibrate_robot.py 를 실행하세요')
        return cls.load(path)

    @staticmethod
    def save(path, n, corners):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({'n': n, 'corners': corners}, f, indent=2)

    def to_robot(self, row, col):
        p = cv2.perspectiveTransform(np.float32([[[col, row]]]), self.T)[0, 0]
        return float(p[0]), float(p[1])
