"""
손이 판 위에 있는지 감지

method = 'diff' (기본, 추가 설치 불필요)
  보정된 판 이미지에서
   - 직전 프레임 대비 변화가 크면 -> 움직이는 중 (손)
   - 기준 이미지(마지막으로 확정된 판) 대비 큰 변화 덩어리가 있으면 -> 손
     (돌 하나는 칸 넓이보다 작으므로, blob_cells 배수보다 큰 덩어리만 손으로 봄)
   - 변화 덩어리가 보정 이미지 테두리에 닿아 있으면 -> 판 밖에서 들어온 손

method = 'mediapipe'
  pip install mediapipe 후 사용. 원본 프레임에서 손 랜드마크를 찾아
  판 영역(호모그래피로 계산) 안에 있으면 손으로 판단.
"""
import cv2
import numpy as np


class HandDetector:
    def __init__(self, method='diff', cell=60, diff_threshold=40,
                 blob_cells=2.0, motion_ratio=0.01):
        self.method = method
        self.cell = cell
        self.diff_threshold = diff_threshold
        self.blob_area = blob_cells * cell * cell
        self.motion_ratio = motion_ratio
        self.reference = None      # 마지막 확정 판 이미지 (gray, blur)
        self._prev = None
        self._mp_hands = None
        if method == 'mediapipe':
            self._init_mediapipe()

    @classmethod
    def from_config(cls, cfg):
        h = cfg['vision']['hand']
        return cls(h.get('method', 'diff'), cfg['board']['cell'], h.get('diff_threshold', 40),
                   h.get('blob_cells', 2.0), h.get('motion_ratio', 0.01))

    def _init_mediapipe(self):
        try:
            import mediapipe as mp
            self._mp_hands = mp.solutions.hands.Hands(
                static_image_mode=False, max_num_hands=2, min_detection_confidence=0.5)
        except Exception as e:          # 설치 안 됨 / 새 버전 API 차이
            print(f'[hand_detect] mediapipe 사용 불가 ({e}) -> diff 방식으로 대체')
            self.method = 'diff'

    @staticmethod
    def _prep(warped):
        g = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
        return cv2.GaussianBlur(g, (7, 7), 0)

    def set_reference(self, warped):
        """판 상태가 확정될 때마다 호출 -> 이후 변화량의 기준"""
        self.reference = self._prep(warped)

    def detect(self, warped, frame=None, W=None):
        """손이 있으면 True"""
        if self.method == 'mediapipe' and frame is not None and W is not None:
            return self._detect_mediapipe(frame, W, warped.shape[0])
        return self._detect_diff(warped)

    def _detect_diff(self, warped):
        g = self._prep(warped)
        hand = False

        # 1) 직전 프레임 대비 움직임
        if self._prev is not None and self._prev.shape == g.shape:
            moving = cv2.absdiff(g, self._prev) > self.diff_threshold // 2
            if moving.mean() > self.motion_ratio:
                hand = True
        self._prev = g

        # 2) 기준 이미지 대비 큰 변화 덩어리
        if not hand and self.reference is not None and self.reference.shape == g.shape:
            changed = (cv2.absdiff(g, self.reference) > self.diff_threshold).astype(np.uint8)
            changed = cv2.morphologyEx(changed, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
            n, lab, st, _ = cv2.connectedComponentsWithStats(changed)
            H, Wd = g.shape
            for i in range(1, n):
                x, y, w, h, area = st[i]
                touches_edge = x <= 1 or y <= 1 or x + w >= Wd - 1 or y + h >= H - 1
                if area > self.blob_area or (touches_edge and area > self.cell * self.cell * 0.5):
                    hand = True
                    break
        return hand

    def _detect_mediapipe(self, frame, W, size):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        res = self._mp_hands.process(rgb)
        if not res.multi_hand_landmarks:
            return False
        h, w = frame.shape[:2]
        for hand in res.multi_hand_landmarks:
            pts = np.float32([[lm.x * w, lm.y * h] for lm in hand.landmark])
            q = cv2.perspectiveTransform(pts[None], W)[0]          # 원본 -> 보정 좌표
            inside = (q[:, 0] > -self.cell) & (q[:, 0] < size + self.cell) & \
                     (q[:, 1] > -self.cell) & (q[:, 1] < size + self.cell)
            if inside.any():
                return True
        return False
