"""
보정된 판 이미지 -> 각 교차점 상태 (0=빈칸, 1=흑, 2=백)

각 교차점 주변 원형 패치에서 특징을 뽑아 분류합니다.
  v_med : 밝기 중앙값          (흑돌이면 낮음)
  s_med : 채도 중앙값          (나무색 판이면 빈칸이 높고, 흰 돌은 낮음)
  dark  : 어두운 픽셀 비율      (흑돌이 작거나 살짝 비껴 놓여도 잡힘)
  edge  : 엣지 픽셀 비율        (흰 종이 위 흰 돌은 테두리 엣지로 구분)
  v_std : 밝기 표준편차

분류 방법 두 가지
  1) 캘리브레이션 모델(권장): tools/calibrate_stones.py 로 실제 돌을 라벨링해
     클래스별 특징 평균(centroid)을 저장 -> 가장 가까운 클래스로 분류.
     빈 판 기준(reference)을 함께 저장하면 칸마다 '빈 판 대비 변화량'을 써서
     조명 불균일, 흰 종이 위 흰 돌에도 강해짐.
  2) 기본 규칙: 캘리브레이션 파일이 없을 때. 흑돌은 잘 잡지만,
     흰 종이 위 흰 돌은 구분이 어려움 (색 있는 판/돌 권장).
"""
import json
import os

import cv2
import numpy as np

FEATURES = ['v_med', 's_med', 'dark', 'edge', 'v_std']
EMPTY, BLACK, WHITE = 0, 1, 2

DEFAULT_RULES = {
    'dark_v': 70,          # 이 밝기 미만 픽셀을 '어두운 픽셀'로 셈
    'black_dark': 0.10,    # 어두운 픽셀 비율이 이 이상이면 흑 (빈칸은 보통 0에 가까움)
    'white_s_max': 40,     # (색 있는 판일 때) 채도 이하 + 밝으면 백
    'white_v_min': 150,
    'empty_s_min': 40,     # 빈칸(판 색)의 최소 채도. 흰 종이면 이 규칙이 무력해짐
}


def point_features(warped, n, cell, margin, patch_ratio=0.35, dark_v=70):
    """(n, n, len(FEATURES)) 특징 배열"""
    r = max(3, int(cell * patch_ratio))
    hsv = cv2.cvtColor(warped, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (3, 3), 0), 50, 150)
    pad = r + 1
    hsv = cv2.copyMakeBorder(hsv, pad, pad, pad, pad, cv2.BORDER_REPLICATE)
    edges = cv2.copyMakeBorder(edges, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0)

    yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
    disk = (xx ** 2 + yy ** 2) <= r * r

    out = np.zeros((n, n, len(FEATURES)), np.float32)
    for row in range(n):
        for col in range(n):
            cx, cy = margin + col * cell + pad, margin + row * cell + pad
            ph = hsv[cy - r:cy + r + 1, cx - r:cx + r + 1][disk]
            pe = edges[cy - r:cy + r + 1, cx - r:cx + r + 1][disk]
            v, s = ph[:, 2].astype(np.float32), ph[:, 1].astype(np.float32)
            out[row, col] = [np.median(v), np.median(s), (v < dark_v).mean(),
                             (pe > 0).mean(), v.std()]
    return out


class StoneClassifier:
    def __init__(self, n=8, cell=60, margin=40, patch_ratio=0.35, model=None):
        self.n, self.cell, self.margin, self.patch_ratio = n, cell, margin, patch_ratio
        self.model = model or {}
        self.rules = {**DEFAULT_RULES, **self.model.get('rules', {})}

    # ---------- 생성 / 저장 ----------
    @classmethod
    def from_config(cls, cfg):
        from utils.config import project_path
        b = cfg['board']
        path = project_path(cfg['paths']['stone_model'])
        model = None
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                model = json.load(f)
        return cls(b['n'], b['cell'], b['margin'], cfg['vision']['patch_ratio'], model)

    def save(self, path):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.model, f, indent=2, ensure_ascii=False)

    @property
    def is_calibrated(self):
        return 'centroids' in self.model

    def features(self, warped):
        return point_features(warped, self.n, self.cell, self.margin,
                              self.patch_ratio, self.rules['dark_v'])

    def _delta(self, f):
        """빈 판 기준이 있으면 칸별 변화량 특징을 뒤에 붙임"""
        ref = self.model.get('reference')
        if ref is None:
            return f
        return np.concatenate([f, f - np.asarray(ref, np.float32)], axis=-1)

    # ---------- 캘리브레이션 ----------
    def set_reference(self, empty_warped):
        """돌이 하나도 없는 판 이미지를 기준으로 저장 (기존 학습 결과는 특징 차원이 달라져 초기화)"""
        self.model['reference'] = self.features(empty_warped).tolist()
        for k in ('centroids', 'scale', 'counts', 'features'):
            self.model.pop(k, None)

    def fit(self, warped, labels):
        """
        warped: 보정 이미지, labels: (n, n) 정답 (0/1/2).
        여러 장을 쓰려면 fit_many 사용.
        """
        self.fit_many([(warped, labels)])

    def fit_many(self, samples):
        X, y = [], []
        for warped, labels in samples:
            f = self._delta(self.features(warped))
            X.append(f.reshape(-1, f.shape[-1]))
            y.append(np.asarray(labels).reshape(-1))
        X, y = np.concatenate(X), np.concatenate(y)
        centroids, counts = {}, {}
        for c in (EMPTY, BLACK, WHITE):
            if (y == c).any():
                centroids[str(c)] = X[y == c].mean(0).tolist()
                counts[str(c)] = int((y == c).sum())
        # 특징 크기가 제각각이라 표준화용 스케일 (클래스 내부 표준편차 + 클래스 간 거리)
        spread = np.std(X, axis=0) + 1e-3
        self.model.update({'centroids': centroids, 'scale': spread.tolist(), 'counts': counts,
                           'features': FEATURES + (['d_' + k for k in FEATURES]
                                                   if 'reference' in self.model else [])})

    # ---------- 분류 ----------
    def classify(self, warped):
        """(n, n) int 배열 반환"""
        f = self.features(warped)
        if self.is_calibrated:
            return self._classify_centroid(self._delta(f))
        return self._classify_rules(f)

    def _classify_centroid(self, f):
        scale = np.asarray(self.model['scale'], np.float32)
        keys = sorted(self.model['centroids'], key=int)
        C = np.asarray([self.model['centroids'][k] for k in keys], np.float32)
        d = (((f[..., None, :] - C) / scale) ** 2).sum(-1)       # (n, n, k)
        return np.asarray([int(k) for k in keys])[d.argmin(-1)]

    def _classify_rules(self, f):
        r = self.rules
        v, s, dark = f[..., 0], f[..., 1], f[..., 2]
        grid = np.zeros((self.n, self.n), int)
        grid[(s < r['white_s_max']) & (v > r['white_v_min'])] = WHITE
        # 판 채도가 낮으면(흰 종이) 위 규칙이 빈칸까지 백으로 만들므로 끔
        if np.median(s) < r['empty_s_min']:
            grid[:] = EMPTY
        grid[dark > r['black_dark']] = BLACK
        return grid


def grid_to_text(grid):
    sym = {EMPTY: '·', BLACK: '●', WHITE: '○'}
    return '\n'.join(' '.join(sym[int(x)] for x in row) for row in grid)
