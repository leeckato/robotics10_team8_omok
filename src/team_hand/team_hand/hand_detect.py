"""
손이 판 위에 있는지 감지 (손 모델 + 변화 감지 + 그림자 무시 + 디바운스)

판정 (한 프레임)
  ① 손 모델이 찾은 손이 판 영역 안에 있음                     (method: model / both)
  ② 기준 화면 대비 판 영역의 change_ratio 이상이 바뀜          (method: diff / both)
  ③ 직전 프레임 대비 판 영역의 motion_ratio 이상이 움직임       (method: diff / both)
  -> 하나라도 걸리면 '감지'. 그림자(같은 색, 밝기만 변함)는 ②③에서 제외.
  ※ both 는 가위·펜 같은 물체도 잡음 (판 위에 뭔가 있으면 판을 읽으면 안 되므로).
     손만 잡으려면 method: model

손 모델 (hand_model)
  mediapipe : MediaPipe HandLandmarker (손 관절 21개). 윈도우 보안 정책이 DLL 을 막으면 사용 불가
  opencv    : MediaPipe 의 손바닥 검출 모델(palm_detection_full.tflite)을 OpenCV DNN 으로 실행.
              opencv-python 만 있으면 동작 (OpenCV 4.8 이상), MediaPipe 설치/DLL 불필요
  auto      : mediapipe 를 시도하고 안 되면 opencv

확정 (여러 프레임)
  HAND : 감지가 hand_frames 번 연속
  CLEAR: clear_seconds 동안 감지 없음 -> 이때 기준 화면 갱신 (새로 놓인 돌은 배경이 됨)
  안전장치: HAND 인데 stuck_seconds 동안 움직임·MediaPipe 손이 없으면
            조명/배경 변화로 보고 기준 화면 재설정

사용 (오목 프로젝트: BoardReader 가 호출)
    det = HandDetector.from_config(cfg)
    hand = det.detect(warped, frame, W)   # warped: 보정된 판 이미지, frame: 원본, W: 원본->보정 행렬
    # hand == True 이면 판 읽기 보류

단독 사용 (보정 없이 원본 화면에서)
    det = HandDetector(roi=[(x1, y1), (x2, y2), (x3, y3), (x4, y4)])
    hand = det.detect(frame)

단독 실행 데모 (프로젝트 폴더에서)
    python -m vision.hand_detect --cam 2
"""
import os
import time
import urllib.request

import cv2
import numpy as np

MODEL_URL = ('https://storage.googleapis.com/mediapipe-models/hand_landmarker/'
             'hand_landmarker/float16/latest/hand_landmarker.task')
PALM_MODEL = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'models', 'palm_detection_full.tflite')
HAND, CLEAR = 'HAND', 'CLEAR'


# ════════════════════════ OpenCV 손바닥 검출 ════════════════════════
class _OpenCVPalm:
    """
    MediaPipe 손바닥 검출 모델(TFLite)을 OpenCV DNN 으로 실행. 손등이 보여도 검출됨.
    detect() -> 손마다 (9, 2) 점 배열: 손가락까지 덮도록 넓힌 박스의 꼭짓점 4 + 변 중점 4 + 중심
    """
    SIZE = 192

    def __init__(self, model_path=PALM_MODEL, score=0.5, expand=2.0):
        if not hasattr(cv2.dnn, 'readNetFromTFLite'):
            raise RuntimeError(f'OpenCV {cv2.__version__} 는 TFLite 모델을 못 읽음 (4.8 이상 필요: '
                               'pip install -U opencv-python)')
        if not os.path.exists(model_path):
            raise FileNotFoundError(f'손바닥 모델 없음: {model_path}')
        self.net = None
        if hasattr(cv2.dnn, 'ENGINE_CLASSIC'):   # OpenCV 5: 새 엔진은 출력을 한 번에 못 꺼내 2배 느림 -> 기존 엔진
            try:
                self.net = cv2.dnn.readNetFromTFLite(model_path, engine=cv2.dnn.ENGINE_CLASSIC)
            except (cv2.error, TypeError):
                self.net = None
        if self.net is None:
            self.net = cv2.dnn.readNetFromTFLite(model_path)
        self.score = score
        self.expand = expand                    # 손바닥 박스 -> 손가락까지 덮도록 확대 배율
        self._layout = None                     # OpenCV 버전에 따라 입력 모양(NCHW/NHWC)이 달라 처음에 확인
        a = []
        for fm, n in ((24, 2), (12, 6)):        # SSD 앵커: 24x24x2 + 12x12x6 = 2016
            for y in range(fm):
                for x in range(fm):
                    a += [((x + 0.5) / fm, (y + 0.5) / fm)] * n
        self.anchors = np.float32(a)
        self.boxes = []                         # 마지막 검출 (x, y, w, h, score) 원본 좌표

    def _forward(self, x):
        err = None
        for layout in ([self._layout] if self._layout else ['nchw', 'nhwc']):
            blob = x.transpose(2, 0, 1)[None] if layout == 'nchw' else x[None]
            try:
                self.net.setInput(blob)
                try:
                    outs = self.net.forward(['Identity', 'Identity_1'])
                except cv2.error:                # 일부 OpenCV 버전: 출력을 하나씩 꺼내야 함
                    outs = [self.net.forward('Identity_1')]
                    self.net.setInput(blob)
                    outs.append(self.net.forward('Identity'))
                self._layout = layout
                reg = next(o for o in outs if o.shape[-1] == 18).reshape(-1, 18)
                cls = next(o for o in outs if o.shape[-1] == 1).reshape(-1)
                return reg, cls
            except (cv2.error, StopIteration) as e:
                err = e
        raise RuntimeError(f'손바닥 모델 실행 실패: {err}')

    def detect(self, bgr, t=None):
        h, w = bgr.shape[:2]
        s = self.SIZE / max(h, w)                # 비율 유지 + 검은 여백 (letterbox)
        nh, nw = int(round(h * s)), int(round(w * s))
        top, left = (self.SIZE - nh) // 2, (self.SIZE - nw) // 2
        canvas = np.zeros((self.SIZE, self.SIZE, 3), np.uint8)
        canvas[top:top + nh, left:left + nw] = cv2.resize(bgr, (nw, nh))
        x = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0   # 0~1 정규화

        reg, cls = self._forward(x)
        score = 1.0 / (1.0 + np.exp(-np.clip(cls, -50, 50)))
        keep = score > self.score
        self.boxes = []
        if not keep.any():
            return []
        r, a, sc = reg[keep], self.anchors[keep], score[keep]
        cx = (r[:, 0] / self.SIZE + a[:, 0]) * self.SIZE
        cy = (r[:, 1] / self.SIZE + a[:, 1]) * self.SIZE
        bw, bh = r[:, 2], r[:, 3]
        rects = np.stack([cx - bw / 2, cy - bh / 2, bw, bh], 1)
        idx = np.array(cv2.dnn.NMSBoxes(rects.tolist(), sc.tolist(), self.score, 0.3)).reshape(-1)

        hands = []
        for i in idx:
            ccx, ccy = (cx[i] - left) / s, (cy[i] - top) / s          # 원본 좌표
            hw, hh = bw[i] / s * self.expand / 2, bh[i] / s * self.expand / 2
            self.boxes.append((ccx - hw, ccy - hh, 2 * hw, 2 * hh, float(sc[i])))
            hands.append(np.float32([[ccx + dx * hw, ccy + dy * hh]
                                     for dx, dy in ((-1, -1), (1, -1), (1, 1), (-1, 1),
                                                    (0, -1), (1, 0), (0, 1), (-1, 0), (0, 0))]))
        return hands

    def close(self):
        pass


# ════════════════════════ MediaPipe ════════════════════════
class _MediaPipeHands:
    """mediapipe 0.10 Tasks API (HandLandmarker, VIDEO 모드)"""

    def __init__(self, model_path, num_hands=2, min_conf=0.5):
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions
        from mediapipe.tasks.python.vision import HandLandmarker, HandLandmarkerOptions, RunningMode

        if not os.path.exists(model_path):
            os.makedirs(os.path.dirname(os.path.abspath(model_path)), exist_ok=True)
            print(f'[hand_detect] 손 모델 다운로드 중... -> {model_path}')
            try:
                urllib.request.urlretrieve(MODEL_URL, model_path)
            except Exception:
                if os.path.exists(model_path):
                    os.remove(model_path)
                raise
        self.mp = mp
        self.detector = HandLandmarker.create_from_options(HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=model_path),
            running_mode=RunningMode.VIDEO,
            num_hands=num_hands,
            min_hand_detection_confidence=min_conf,
            min_hand_presence_confidence=min_conf,
            min_tracking_confidence=min_conf))
        self._last_ts = -1

    def detect(self, bgr, t):
        """손마다 (21, 2) 픽셀 좌표 배열 목록"""
        h, w = bgr.shape[:2]
        image = self.mp.Image(image_format=self.mp.ImageFormat.SRGB,
                              data=cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
        ts = max(int(t * 1000), self._last_ts + 1)          # VIDEO 모드: 타임스탬프가 계속 증가해야 함
        self._last_ts = ts
        res = self.detector.detect_for_video(image, ts)
        return [np.float32([[lm.x * w, lm.y * h] for lm in hand]) for hand in res.hand_landmarks]

    def close(self):
        self.detector.close()


# ════════════════════════ 손 감지기 ════════════════════════
class HandDetector:
    def __init__(self, method='both', diff_threshold=35, change_ratio=0.025, motion_ratio=0.005,
                 hand_frames=2, clear_seconds=1.0, stuck_seconds=5.0,
                 ignore_shadow=True, shadow_min=0.35, shadow_chroma=0.04,
                 roi=None, model_path='hand_landmarker.task', blur_ksize=9, verbose=True,
                 hand_model='auto', palm_model_path=PALM_MODEL, palm_score=0.5):
        """
        method        : 'both'(손 모델 + 변화 감지) | 'diff'(변화 감지만) | 'model'(손 모델만, 'mediapipe' 도 같은 뜻)
        hand_model    : 'auto' | 'opencv' | 'mediapipe'  (위 설명 참고)
        palm_score    : opencv 손바닥 검출 점수 기준 (오검출이 있으면 0.6~0.7, 손을 놓치면 0.4)
        diff_threshold: 색 차이(0~255)가 이보다 크면 '변한 픽셀'
        change_ratio  : 기준 화면 대비 변한 픽셀 비율이 이보다 크면 감지 (돌 하나는 보통 0.5% 미만)
        motion_ratio  : 직전 프레임 대비 움직인 픽셀 비율이 이보다 크면 감지
        hand_frames   : 연속 N 프레임 감지 -> HAND
        clear_seconds : 이 시간 동안 감지 없음 -> CLEAR
        stuck_seconds : HAND 인데 이 시간 동안 정지 -> 기준 화면 재설정
        ignore_shadow : 그림자 무시
        shadow_min    : 밝기가 이 배율까지 어두워져도 색이 같으면 그림자 (검은 소매를 놓치면 0.45~0.5)
        shadow_chroma : 색 비율 차이가 이보다 작으면 '같은 색' (그림자가 아직 잡히면 0.05~0.06)
        roi           : 검사 영역 다각형 [(x, y), ...] (detect 에 넣는 image 좌표). None = 전체
        """
        self.method = 'model' if method == 'mediapipe' else method
        self.diff_threshold = diff_threshold
        self.change_ratio = change_ratio
        self.motion_ratio = motion_ratio
        self.hand_frames = hand_frames
        self.clear_seconds = clear_seconds
        self.stuck_seconds = stuck_seconds
        self.ignore_shadow = ignore_shadow
        self.shadow_min = shadow_min
        self.shadow_chroma = shadow_chroma
        self.blur_ksize = blur_ksize
        self.verbose = verbose

        self.roi = None if roi is None else np.float32(roi)
        self._roi_mask = None

        self.reference = None          # 손 없는 기준 화면 (blur). None 이면 다음 프레임으로 초기화
        self._prev = None
        self.state = CLEAR
        self._hits = 0
        self._last_hit_t = None
        self._still_since = None
        self.last = {}                 # 마지막 프레임 판정 상세 (화면 표시/디버깅용)

        self._mp = None                # 손 모델 (MediaPipe 또는 OpenCV 손바닥 검출)
        self.hand_model = None         # 실제로 쓰는 손 모델 이름 ('mediapipe' / 'opencv' / None)
        if self.method in ('both', 'model'):
            self._init_hand_model(hand_model, model_path, palm_model_path, palm_score)

    @classmethod
    def from_config(cls, cfg):
        """config.yaml 의 vision.hand 섹션 (없는 키는 기본값)"""
        from utils.config import project_path
        h = dict(cfg.get('vision', {}).get('hand', {}))
        keys = ['method', 'diff_threshold', 'change_ratio', 'motion_ratio', 'hand_frames',
                'clear_seconds', 'stuck_seconds', 'ignore_shadow', 'shadow_min', 'shadow_chroma',
                'hand_model', 'palm_score']
        kw = {k: h[k] for k in keys if k in h}
        if kw.get('method') == 'diff_only':
            kw['method'] = 'diff'
        kw['model_path'] = project_path(h.get('model_path', 'calib/hand_landmarker.task'))
        if 'palm_model_path' in h:
            kw['palm_model_path'] = project_path(h['palm_model_path'])
        return cls(**kw)

    def _init_hand_model(self, which, model_path, palm_model_path, palm_score):
        errors = []
        if which in ('auto', 'mediapipe'):
            try:
                self._mp = _MediaPipeHands(model_path)
                self.hand_model = 'mediapipe'
            except Exception as e:
                msg = f'MediaPipe 사용 불가 ({e})'
                if '4551' in str(e):
                    msg += ' <- 윈도우 보안 정책(스마트 앱 컨트롤 등)이 MediaPipe DLL 을 차단함'
                errors.append(msg)
        if self._mp is None and which in ('auto', 'opencv'):
            try:
                self._mp = _OpenCVPalm(palm_model_path, palm_score)
                self.hand_model = 'opencv'
            except Exception as e:
                errors.append(f'OpenCV 손바닥 모델 사용 불가 ({e})')

        if self._mp is not None:
            if self.verbose:
                note = ' (MediaPipe 대신)' if errors else ''
                print(f'[hand_detect] 손 모델: {self.hand_model}{note}')
            return
        print('[hand_detect] 손 모델을 쓸 수 없음 -> 변화 감지만 사용\n  ' + '\n  '.join(errors))
        self.method = 'diff'

    # ───────── 상태 관리 ─────────
    def set_roi(self, poly):
        """검사 영역 변경 (None = 전체). 기준 화면도 다시 잡음"""
        self.roi = None if poly is None else np.float32(poly)
        self._roi_mask = None
        self.reset()

    def set_reference(self, image):
        """손 없는 화면을 기준으로 지정 (BoardReader 가 판 확정 때 호출)"""
        self.reference = self._blur(image)

    def reset(self):
        """기준/상태 초기화. 다음 detect() 프레임이 새 기준 (손 없는 상태에서 호출)"""
        self.reference = None
        self._prev = None
        self.state = CLEAR
        self._hits = 0
        self._last_hit_t = None
        self._still_since = None

    @property
    def is_hand(self):
        return self.state == HAND

    def close(self):
        if self._mp is not None:
            self._mp.close()
            self._mp = None

    # ───────── 판정 ─────────
    def detect(self, image, frame=None, W=None, t=None):
        """
        image: 변화 감지할 이미지 (오목: 보정된 판 이미지, 단독: 원본 프레임)
        frame: 손 모델을 돌릴 원본 프레임 (없으면 image 사용)
        W    : frame -> image 좌표 변환 행렬 (frame 을 줄 때)
        t    : 시각(초). 생략하면 현재 시각 (동영상 파일 테스트 때 frame_idx / fps 를 넣으면 재현 가능)
        반환 : 확정된 손 상태 (True = 손 있음 -> 판 읽기 보류)
        """
        t = time.monotonic() if t is None else t
        mask = self._mask(image.shape)
        cur = self._blur(image)
        if self.reference is None or self.reference.shape != cur.shape:
            self.reference = cur
        if self._prev is None or self._prev.shape != cur.shape:
            self._prev = cur

        # ① 손 모델 (MediaPipe 관절 또는 OpenCV 손바닥 박스가 판 영역에 걸치면 손)
        mp_hit, hands = False, []
        if self._mp is not None:
            src = image if frame is None else frame
            hands = self._mp.detect(src, t)
            if frame is not None and W is not None and hands:
                hands = [cv2.perspectiveTransform(hd[None], W)[0] for hd in hands]   # 원본 -> image 좌표
            mp_hit = any(self._inside(hd, mask) for hd in hands)

        # ②③ 변화 / 움직임 (그림자 제외)
        change_hit = move_hit = False
        ratio, changed = 0.0, None
        if self.method in ('both', 'diff'):
            area = max(1, int(np.count_nonzero(mask)))
            changed = self._changed(cur, self.reference, mask).astype(np.uint8)
            changed = cv2.morphologyEx(changed, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
            ratio = float(changed.sum()) / area
            change_hit = ratio > self.change_ratio
            move_hit = self._changed(cur, self._prev, mask).sum() / area > self.motion_ratio
        self._prev = cur

        detected = mp_hit or change_hit or move_hit
        event = self._update_state(detected, move_hit or mp_hit, cur, t)
        self.last = dict(mp_hit=mp_hit, change_hit=change_hit, move_hit=move_hit, ratio=ratio,
                         changed=changed, hands=hands, detected=detected, event=event, t=t)
        return self.state == HAND

    def _update_state(self, detected, active, cur, t):
        """디바운스 + 기준 화면 관리. 상태가 바뀌면 HAND/CLEAR 반환"""
        if self._last_hit_t is None:
            self._last_hit_t = t - self.clear_seconds          # 시작 상태 = CLEAR 확정
        event = None
        if detected:
            self._hits += 1
            self._last_hit_t = t
            if self.state == CLEAR and self._hits >= self.hand_frames:
                self.state, event = HAND, HAND
        else:
            self._hits = 0
            if self.state == HAND and t - self._last_hit_t >= self.clear_seconds:
                self.state, event = CLEAR, CLEAR
                # 기준 화면은 'CLEAR 확정' 순간에만 갱신
                # (매 프레임 갱신하면 천천히 들어오는 손끝이 배경에 섞여 HAND 에서 못 빠져나옴)
                self.reference = cur

        # 안전장치: HAND 인데 오래 정지 -> 조명/배경 변화로 보고 기준 재설정
        if self.state == HAND and not active:
            if self._still_since is None:
                self._still_since = t
            elif t - self._still_since >= self.stuck_seconds:
                self.reference = cur
                self._still_since = None
                if self.verbose:
                    print('[hand_detect] 오래 정지 상태 -> 기준 화면 재설정 (조명/배경 변화로 판단)')
        else:
            self._still_since = None
        if event and self.verbose:
            print(f'[hand_detect] {"손 들어옴" if event == HAND else "손 없음 확정"}')
        return event

    # ───────── 내부 계산 ─────────
    def _blur(self, img):
        return cv2.GaussianBlur(img, (self.blur_ksize, self.blur_ksize), 0)

    def _mask(self, shape):
        h, w = shape[:2]
        if self._roi_mask is None or self._roi_mask.shape != (h, w):
            m = np.zeros((h, w), np.uint8)
            if self.roi is None:
                m[:] = 255
            else:
                cv2.fillPoly(m, [np.int32(np.round(self.roi))], 255)
            self._roi_mask = m
        return self._roi_mask

    @staticmethod
    def _inside(pts, mask):
        h, w = mask.shape
        for x, y in pts:
            xi, yi = int(x), int(y)
            if 0 <= xi < w and 0 <= yi < h and mask[yi, xi]:
                return True
        return False

    def _changed(self, cur, ref, mask):
        """
        색 차이가 크고(B,G,R 중 최대 차이) 그림자가 아닌 영역 픽셀.
        흑백으로 비교하면 '밝은 피부 vs 흰 종이' 를 놓치므로 컬러로 비교.
        그림자 판정은 바뀐 픽셀에만 계산 (전체 계산 대비 수 배 빠름).
        """
        diff = cv2.absdiff(cur, ref).max(axis=2)
        changed = (diff > self.diff_threshold) & (mask > 0)
        if self.ignore_shadow:
            ys, xs = np.nonzero(changed)
            if len(ys):
                sh = self._shadow_like(cur[ys, xs], ref[ys, xs])
                changed[ys[sh], xs[sh]] = False
        return changed

    def _shadow_like(self, c, r):
        """
        그림자(또는 조명 밝기 변화) = 밝기만 shadow_min ~ 1/shadow_min 배로 변하고 색 비율(B:G:R)은 그대로.
        흰 종이 위 그림자는 '같은 색, 더 어두움', 피부·색 있는 소매는 색 비율이 달라짐.
        c, r: (N, 3) 픽셀 배열
        """
        c = c.astype(np.float32) + 1.0
        r = r.astype(np.float32) + 1.0
        cs, rs = c.sum(1), r.sum(1)
        ratio = cs / rs
        chroma = np.abs(c / cs[:, None] - r / rs[:, None]).max(1)
        return (ratio > self.shadow_min) & (ratio < 1.0 / self.shadow_min) & (chroma < self.shadow_chroma)

    # ───────── 화면 표시 ─────────
    def draw(self, image):
        """판정 결과를 그린 이미지 (영역=노랑, 변화=분홍, 손 모델=빨강: MediaPipe 관절 점 / OpenCV 손 박스)"""
        vis = image.copy()
        if self.roi is not None:
            cv2.polylines(vis, [np.int32(np.round(self.roi))], True, (0, 255, 255), 2)
        ch = self.last.get('changed')
        if ch is not None and ch.shape == vis.shape[:2]:
            sel = ch > 0
            vis[sel] = (vis[sel] * 0.5 + np.array([255, 0, 255]) * 0.5).astype(np.uint8)
        for hd in self.last.get('hands', []):
            if self.hand_model == 'opencv':
                cv2.polylines(vis, [np.int32(np.round(hd[:4]))], True, (0, 0, 255), 2)
            else:
                for x, y in hd:
                    cv2.circle(vis, (int(x), int(y)), 3, (0, 0, 255), -1)
        hand = self.state == HAND
        cv2.putText(vis, f'{"HAND" if hand else "CLEAR"} hand_model={int(self.last.get("mp_hit", 0))} '
                         f'move={int(self.last.get("move_hit", 0))} chg={self.last.get("ratio", 0):.3f}',
                    (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255) if hand else (0, 160, 0), 2)
        return vis


# ════════════════════════ 단독 실행 데모 ════════════════════════
def _demo():
    """
    python -m vision.hand_detect --cam 2
    python -m vision.hand_detect --source 영상.mp4 --no-show
    calib/grid_H.npy 가 있으면 그 보정 행렬, 없으면 첫 프레임에서 그리드를 찾아 보정 이미지로 판정
    키: q 종료, g 그리드 다시 찾기
    """
    import argparse
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from utils.config import board_geometry, load_config, project_path, warp_size
    from vision.board_detect import apply_warp, detect_grid, warp_matrix
    from vision.camera import Camera

    ap = argparse.ArgumentParser()
    ap.add_argument('--cam', type=int)
    ap.add_argument('--source', help='동영상 파일')
    ap.add_argument('--no-show', action='store_true')
    a = ap.parse_args()

    cfg = load_config()
    n, cell, margin = board_geometry(cfg)
    size = warp_size(cfg)
    src = a.source or (a.cam if a.cam is not None else cfg['camera']['source'])
    is_file = isinstance(src, str) and not str(src).isdigit()
    cap = cv2.VideoCapture(src) if is_file else None
    cam = None if is_file else Camera(src, cfg['camera']['width'], cfg['camera']['height'])
    read = (lambda: cap.read()[1]) if is_file else cam.read
    fps = cap.get(cv2.CAP_PROP_FPS) if is_file else 0

    def find_W(frame):
        try:
            _, M, found = detect_grid(frame, n)
            print(f'그리드 검출: 교차점 {found}/{n * n}개')
            return warp_matrix(M, cell, margin) if found >= n * n * 0.7 else None
        except RuntimeError as e:
            print('그리드 검출 실패:', e)
            return None

    frame = read()
    gpath = project_path(cfg['paths']['grid_H'])
    W = find_W(frame) if (is_file or not os.path.exists(gpath)) else np.load(gpath)
    if W is None:
        raise SystemExit('판 영역을 찾지 못했습니다 (빈 판이 다 보이게 하고 다시 실행)')

    det = HandDetector.from_config(cfg)
    idx = 0
    try:
        while frame is not None:
            idx += 1
            warped = apply_warp(frame, W, size)
            det.detect(warped, frame, W, t=idx / fps if is_file else None)
            if det.last['event']:
                print(f'  [{idx}] {det.last["event"]}')
            if not a.no_show:
                cv2.imshow('hand detect (warped)', det.draw(warped))
                k = cv2.waitKey(1) & 0xFF
                if k == ord('q'):
                    break
                if k == ord('g'):
                    newW = find_W(frame)
                    if newW is not None:
                        W = newW
                        det.reset()
            frame = read()
    finally:
        det.close()
        if cam:
            cam.release()
        if cap:
            cap.release()
        cv2.destroyAllWindows()


if __name__ == '__main__':
    _demo()
