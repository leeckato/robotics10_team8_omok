"""
손 판정 로직 (ROS 와 무관한 순수 Python) — hand_node.py 가 이 클래스를 감쌉니다.

process(bgr, stamp_sec) -> Result(valid, present, reason, debug)
  valid=False : 판 영역을 아직 못 찾음 / 검사 중 예외   (손 없음으로 처리하지 않음)
  present     : 판 영역(검사 영역)에 손이 있는지 (hand_detect.HandDetector 의 확정 상태)

검사 영역 (roi_mode)
  marker  : (기본) 비전 노드와 같은 marker_calibration.json + ArUco 마커 4개로 판 위치를 구해
            '보정된 판 이미지'로 판정 (격자 바깥 margin_cells 칸까지). 비전 노드의 transform_grid 와 같은 기준.
            마커가 가려져도 마지막 위치를 유지, marker_lost_sec 넘게 안 보이면 valid=false.
  grid    : 영상에서 바둑판 그리드를 찾아 '보정된 판 이미지'로 판정 (격자 바깥 margin_cells 칸까지).
            grid_refresh_sec 마다, 손이 없을 때만 다시 찾고 3px 이상 움직였으면 갱신.
  full    : 원본 영상 전체 (규격 문서의 '보수적 처리'. 판 밖의 손도 손으로 판정)
  polygon : roi_polygon 에 적은 다각형 (원본 영상 픽셀 좌표)
"""
import json
import os
from dataclasses import dataclass, field

import cv2
import numpy as np

from team_hand.board_detect import apply_warp, detect_grid, warp_matrix
from team_hand.hand_detect import HandDetector

PKG_DIR = os.path.dirname(os.path.abspath(__file__))

DEFAULTS = dict(
    roi_mode='marker',           # marker | grid | full | polygon
    calibration='~/.config/gomoku/marker_calibration.json',   # 비전 노드 calibration 파라미터와 같은 파일
    marker_lost_sec=5.0,         # 마커 4개가 이보다 오래 안 보이면 valid=false (그 전에는 마지막 위치 사용)
    roi_polygon='',              # 'x1,y1 x2,y2 x3,y3 x4,y4'
    grid_n=8,
    cell_px=60,
    margin_cells=0.6,            # 비전 노드와 같은 '격자 바깥 약 0.6칸'
    grid_min_ratio=0.7,          # 교차점의 70% 이상 찾아야 그리드로 인정
    grid_refresh_sec=5.0,
    grid_move_px=3.0,            # 비전 노드 board_revision 기준과 같은 3px
    method='both',               # both | model | diff
    hand_model='opencv',         # opencv | auto | mediapipe
    palm_model_path='',          # 비우면 패키지에 포함된 models/palm_detection_full.tflite
    palm_score=0.5,
    mediapipe_model_path='',
    diff_threshold=35,
    change_ratio=0.025,
    motion_ratio=0.005,
    hand_frames=2,
    clear_seconds=0.3,           # 3초 대기는 게임 제어가 하므로 짧게
    stuck_seconds=5.0,
    ignore_shadow=True,
    shadow_min=0.35,
    shadow_chroma=0.04,
)


@dataclass
class Result:
    valid: bool
    present: bool = False
    reason: str = ''
    debug: np.ndarray = field(default=None, repr=False)


def default_palm_model():
    """설치된 패키지(share/team_hand/models) -> 소스 폴더 순서로 찾기"""
    try:
        from ament_index_python.packages import get_package_share_directory
        p = os.path.join(get_package_share_directory('team_hand'), 'models', 'palm_detection_full.tflite')
        if os.path.exists(p):
            return p
    except Exception:
        pass
    return os.path.join(PKG_DIR, 'models', 'palm_detection_full.tflite')


def parse_polygon(text):
    pts = [tuple(float(v) for v in p.split(',')) for p in str(text).split()]
    if len(pts) < 3:
        raise ValueError('roi_polygon 은 "x1,y1 x2,y2 x3,y3 x4,y4" 형식으로 3점 이상')
    return pts


class HandProcessor:
    def __init__(self, params=None, log=print):
        p = {**DEFAULTS, **(params or {})}
        self.p = p
        self.log = log
        if p['roi_mode'] not in ('marker', 'grid', 'full', 'polygon'):
            raise ValueError(f"roi_mode 는 marker/grid/full/polygon: {p['roi_mode']}")
        self.n = int(p['grid_n'])
        self.cell = int(p['cell_px'])
        self.margin = int(round(self.cell * float(p['margin_cells'])))
        self.size = 2 * self.margin + self.cell * (self.n - 1)
        self.W = None                    # 원본 -> 보정 판 이미지 행렬 (grid 모드)
        self.board_corners = None        # 원본 영상의 판 영역 네 꼭짓점 (표시/이동 판단용)
        self._last_grid_try = None
        self.cal = None                  # marker 모드: 보정 파일 내용
        self._cal_error = ''
        self._last_cal_try = None
        self._aruco = None
        self._marker_seen = None         # 마커 4개를 마지막으로 확인한 시각

        roi =parse_polygon(p['roi_polygon']) if p['roi_mode'] == 'polygon' else None
        mp_path = p['mediapipe_model_path'] or os.path.join(PKG_DIR, 'models', 'hand_landmarker.task')
        self.det = HandDetector(
            method=p['method'], hand_model=p['hand_model'],
            palm_model_path=p['palm_model_path'] or default_palm_model(), palm_score=float(p['palm_score']),
            model_path=mp_path, diff_threshold=float(p['diff_threshold']),
            change_ratio=float(p['change_ratio']), motion_ratio=float(p['motion_ratio']),
            hand_frames=int(p['hand_frames']), clear_seconds=float(p['clear_seconds']),
            stuck_seconds=float(p['stuck_seconds']), ignore_shadow=bool(p['ignore_shadow']),
            shadow_min=float(p['shadow_min']), shadow_chroma=float(p['shadow_chroma']),
            roi=roi, verbose=False)
        self.log(f"[team_hand] 검사 영역={p['roi_mode']}, 방식={self.det.method}, "
                 f"손 모델={getattr(self.det, 'hand_model', None) or '없음(변화 감지만)'}")

    # ───────── 판 영역 (grid 모드) ─────────
    def _try_grid(self, bgr, stamp):
        self._last_grid_try = stamp
        try:
            _, M, found = detect_grid(bgr, self.n)
        except Exception as e:
            return f'그리드 검출 실패: {e}'
        if found < self.n * self.n * float(self.p['grid_min_ratio']):
            return f'그리드 교차점 부족 {found}/{self.n * self.n}'
        W = warp_matrix(M, self.cell, self.margin)
        corners = self._corners(W)
        moved = None if self.board_corners is None else float(np.abs(corners - self.board_corners).max())
        if moved is None or moved >= float(self.p['grid_move_px']):
            self.W, self.board_corners = W, corners
            self.det.reset()              # 영역이 바뀌면 손 없는 기준 화면도 새로 (손 없을 때만 호출됨)
            self.log(f'[team_hand] 판 영역 {"설정" if moved is None else f"갱신 ({moved:.1f}px 이동)"}: '
                     f'교차점 {found}/{self.n * self.n}')
        return ''

    def _corners(self, W):
        c = np.float32([[0, 0], [self.size, 0], [self.size, self.size], [0, self.size]])
        return cv2.perspectiveTransform(c[None], np.linalg.inv(W))[0]

    def _set_region(self, W, how):
        """판 영역 설정/갱신. grid_move_px 이상 움직였을 때만 바꾸고 손 없는 기준 화면을 새로 잡음"""
        corners = self._corners(W)
        moved = None if self.board_corners is None else float(np.abs(corners - self.board_corners).max())
        if moved is None or moved >= float(self.p['grid_move_px']):
            self.W, self.board_corners = W, corners
            self.det.reset()
            self.log(f'[team_hand] 판 영역 {"설정" if moved is None else f"갱신 ({moved:.1f}px 이동)"}: {how}')

    # ───────── 판 영역 (marker 모드: 비전 노드와 같은 보정 파일 + ArUco) ─────────
    def _load_calibration(self, stamp):
        self._last_cal_try = stamp
        path = os.path.expanduser(str(self.p['calibration']))
        try:
            with open(path, encoding='utf-8') as f:
                cal = json.load(f)
            grid = np.float32(cal['grid']).reshape(-1, 2)
            n = int(cal['n'])
            if grid.shape[0] != n * n or set(cal['markers']) != {'0', '1', '2', '3'}:
                raise ValueError('grid/markers 형식 오류')
        except FileNotFoundError:
            self._cal_error = f'보정 파일 없음: {path} (비전 담당 calibrate 먼저 실행)'
            return False
        except Exception as e:
            self._cal_error = f'보정 파일 읽기 실패 ({path}): {e}'
            return False
        if not hasattr(cv2, 'aruco') or not hasattr(cv2.aruco, 'ArucoDetector'):
            self._cal_error = 'OpenCV aruco 없음 (opencv-contrib-python 필요)'
            return False
        d = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
        prm = cv2.aruco.DetectorParameters()
        prm.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
        self._aruco = cv2.aruco.ArucoDetector(d, prm)
        self.n = n
        self.size = 2 * self.margin + self.cell * (self.n - 1)
        # 보정 시 교차점 64개 -> 격자 좌표(col,row) 호모그래피 (마커 위치로 매 프레임 옮김)
        self._cal_grid = grid
        self._cal_markers = np.concatenate([np.float32(cal['markers'][str(i)]).reshape(4, 2)
                                            for i in range(4)])
        self._grid_idx = np.float32([[c, r] for r in range(n) for c in range(n)])
        self.cal = cal
        self._cal_error = ''
        self.log(f'[team_hand] 보정 파일 사용: {path} ({n}x{n}, 영상 {cal.get("image_size")})')
        return True

    def _find_markers(self, bgr):
        """비전 노드 stone_detection_marker.transform_grid 와 같은 조건. 성공하면 현재 영상의 교차점 (n*n,2)"""
        corners, ids, _ = self._aruco.detectMarkers(bgr)
        if ids is None:
            return None
        found = {}
        for c, i in zip(corners, ids.flatten()):
            i = int(i)
            if i in (0, 1, 2, 3):
                if i in found:                 # 같은 ID 두 개 -> 신뢰 불가
                    return None
                found[i] = c.reshape(4, 2).astype(np.float32)
        if set(found) != {0, 1, 2, 3}:
            return None
        target = np.concatenate([found[i] for i in range(4)])
        H, inl = cv2.findHomography(self._cal_markers, target, cv2.RANSAC, 2.0)
        if H is None or not np.isfinite(H).all() or inl is None or inl.mean() < .875:
            return None
        if np.max(np.linalg.norm(cv2.perspectiveTransform(self._cal_markers[None], H)[0] - target, axis=1)) > 3.0:
            return None
        grid = cv2.perspectiveTransform(self._cal_grid[None], H)[0]
        h, w = bgr.shape[:2]
        if not np.isfinite(grid).all() or not np.all((grid[:, 0] > 0) & (grid[:, 0] < w - 1) &
                                                     (grid[:, 1] > 0) & (grid[:, 1] < h - 1)):
            return None
        return grid

    def _marker_region(self, bgr, stamp):
        """marker 모드 영역 갱신. 문제가 있으면 이유 문자열, 정상이면 ''"""
        if self.cal is None:
            if self._last_cal_try is None or stamp - self._last_cal_try >= 2.0:
                self._load_calibration(stamp)
            if self.cal is None:
                return self._cal_error or '보정 파일 대기'
        size = self.cal.get('image_size')
        if size and [bgr.shape[1], bgr.shape[0]] != [int(size[0]), int(size[1])]:
            return f'영상 크기 {bgr.shape[1]}x{bgr.shape[0]} != 보정 파일 {size[0]}x{size[1]}'
        grid = self._find_markers(bgr)
        if grid is not None:
            self._marker_seen = stamp
            M, _ = cv2.findHomography(grid, self._grid_idx)     # 원본 픽셀 -> 격자 좌표
            if M is not None:
                self._set_region(warp_matrix(M, self.cell, self.margin), '마커 4개')
        if self.W is None:
            return '마커 4개를 확인할 수 없음 (판 영역 없음)'
        lost = stamp - (self._marker_seen or stamp)
        if lost > float(self.p['marker_lost_sec']):
            return f'마커가 {lost:.1f}초째 안 보임'
        return ''

    # ───────── 판정 ─────────
    def process(self, bgr, stamp_sec, want_debug=False):
        try:
            mode = self.p['roi_mode']
            if mode == 'marker':
                reason = self._marker_region(bgr, stamp_sec)
                if reason:
                    return Result(False, reason=reason)
                img = apply_warp(bgr, self.W, self.size)
                present = self.det.detect(img, bgr, self.W, t=stamp_sec)
            elif mode == 'grid':
                due = self._last_grid_try is None or \
                    stamp_sec - self._last_grid_try >= float(self.p['grid_refresh_sec'])
                quiet = not self.det.is_hand and not self.det.last.get('detected', False)
                if self.W is None and (self._last_grid_try is None or stamp_sec - self._last_grid_try >= 0.5):
                    reason = self._try_grid(bgr, stamp_sec)
                    if self.W is None:
                        return Result(False, reason=reason or '판 영역 없음')
                elif self.W is not None and due and quiet:
                    self._try_grid(bgr, stamp_sec)    # 실패해도 기존 영역 유지
                if self.W is None:
                    return Result(False, reason='판 영역 없음 (재시도 대기)')
                img = apply_warp(bgr, self.W, self.size)
                present = self.det.detect(img, bgr, self.W, t=stamp_sec)
            else:
                img = bgr
                present = self.det.detect(bgr, t=stamp_sec)
            debug = self.det.draw(img) if want_debug else None
            return Result(True, bool(present), '', debug)
        except Exception as e:                      # 검사 실패는 '손 없음'이 아니라 무효
            return Result(False, reason=f'검사 실패: {type(e).__name__}: {e}')

    def close(self):
        self.det.close()


# ───────── sensor_msgs/Image <-> numpy (cv_bridge 없이) ─────────
def image_msg_to_bgr(msg):
    enc = (msg.encoding or '').lower()
    if enc not in ('bgr8', 'rgb8'):
        raise ValueError(f'지원하지 않는 영상 형식: {msg.encoding} (bgr8 필요)')
    h, w, step = int(msg.height), int(msg.width), int(msg.step)
    buf = np.frombuffer(msg.data, dtype=np.uint8)
    if buf.size < h * step or step < w * 3:
        raise ValueError(f'영상 크기 불일치: {w}x{h}, step={step}, data={buf.size}')
    img = buf[:h * step].reshape(h, step)[:, :w * 3].reshape(h, w, 3)
    if enc == 'rgb8':
        img = img[:, :, ::-1]
    return np.ascontiguousarray(img)


def fill_image_msg(msg, bgr, header):
    msg.header = header
    msg.height, msg.width = int(bgr.shape[0]), int(bgr.shape[1])
    msg.encoding = 'bgr8'
    msg.is_bigendian = 0
    msg.step = int(bgr.shape[1] * 3)
    msg.data = np.ascontiguousarray(bgr, dtype=np.uint8).tobytes()
    return msg
