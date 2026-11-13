"""
marker 모드 시험: 비전 노드와 같은 보정 파일(marker_calibration.json) + ArUco 4개
합성 영상은 gomoku_system/tests/test_vision.py 와 같은 방식 (600x600, 마커 0~3, 격자 145~455)
  python3 -m pytest test/test_marker_mode.py -v
"""
import json
import os
import sys

import cv2
import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from team_hand.processor import HandProcessor  # noqa: E402

if not hasattr(cv2, 'aruco') or not hasattr(cv2.aruco, 'ArucoDetector'):
    pytest.skip('OpenCV aruco 없음', allow_module_level=True)

FPS = 10                      # 비전 노드 /vision/image_raw 발행 주기
RNG = np.random.default_rng(1)
MARKER_POS = [(15, 15), (495, 15), (495, 495), (15, 495)]


def scene():
    img = np.full((600, 600, 3), 190, np.uint8)
    d = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    for i, (x, y) in enumerate(MARKER_POS):
        a = cv2.aruco.generateImageMarker(d, i, 85)
        img[y - 5:y + 90, x - 5:x + 90] = 255
        img[y:y + 85, x:x + 85] = cv2.cvtColor(a, cv2.COLOR_GRAY2BGR)
    for i in range(8):
        t = round(145 + 310 * i / 7)
        cv2.line(img, (145, t), (455, t), (45, 45, 45), 1)
        cv2.line(img, (t, 145), (t, 455), (45, 45, 45), 1)
    return img


@pytest.fixture
def cal_file(tmp_path):
    img = scene()
    d = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    corners, ids, _ = cv2.aruco.ArucoDetector(d).detectMarkers(img)
    markers = {str(int(i)): c.reshape(4, 2).tolist() for c, i in zip(corners, ids.flatten())}
    grid = [[145 + 310 * c / 7, 145 + 310 * r / 7] for r in range(8) for c in range(8)]
    p = tmp_path / 'marker_calibration.json'
    p.write_text(json.dumps(dict(dictionary='DICT_4X4_50', image_size=[600, 600], n=8,
                                 markers=markers, grid=grid, colors={})))
    return str(p)


def noisy(img):
    return np.clip(img.astype(np.int16) + RNG.normal(0, 2, img.shape), 0, 255).astype(np.uint8)


def with_hand(img, k):
    """k=0: 화면 아래 밖, k=1: 판 중앙까지 (살색 손 + 소매)"""
    f = img.copy()
    cy = int(700 - k * (700 - 300))
    cv2.rectangle(f, (255, cy + 40), (345, 700), (60, 60, 140), -1)
    cv2.ellipse(f, (300, cy + 10), (45, 60), 0, 0, 360, (120, 160, 215), -1)
    return f


def make(cal, **kw):
    return HandProcessor({'roi_mode': 'marker', 'calibration': cal, 'method': 'diff', **kw}, log=lambda *_: None)


def run(proc, frames, t0=0.0):
    return [(r.valid, r.present, r.reason) for r in
            (proc.process(noisy(f), t0 + i / FPS) for i, f in enumerate(frames))]


def test_hand_enter_leave(cal_file):
    p, base = make(cal_file), scene()
    frames = [base] * 10 + [with_hand(base, k) for k in np.linspace(0, 1, 6)] + [with_hand(base, 1)] * 5 \
        + [with_hand(base, k) for k in np.linspace(1, 0, 6)] + [base] * 10
    out = run(p, frames)
    assert all(v for v, _, _ in out), [r for r in out if not r[0]][:3]
    pres = [pr for _, pr, _ in out]
    assert not any(pres[:10])                  # 빈 판
    assert any(pres[16:21])                    # 손이 판 위
    assert not any(pres[-4:])                  # 손 빠지면 다시 없음


def test_hand_outside_board_ignored(cal_file):
    """판 밖(격자+0.6칸 바깥)의 움직임은 무시"""
    p, base = make(cal_file), scene()
    frames = [base] * 10
    for k in range(10):
        f = base.copy()
        cv2.ellipse(f, (60 + k * 3, 300), (35, 50), 0, 0, 360, (120, 160, 215), -1)   # 판 왼쪽 바깥
        frames.append(f)
    out = run(p, frames)
    assert all(v for v, _, _ in out)
    assert not any(pr for _, pr, _ in out)


def test_marker_covered_keeps_region_then_invalid(cal_file):
    p, base = make(cal_file, marker_lost_sec=1.0), scene()
    covered = base.copy()
    cv2.rectangle(covered, (480, 0), (600, 120), (190, 190, 190), -1)     # 마커 1 가림 (판 밖)
    out = run(p, [base] * 5 + [covered] * 20)
    assert all(v for v, _, _ in out[:15])       # 1초까지는 마지막 위치로 정상 검사
    assert not out[-1][0] and '마커' in out[-1][2]
    out2 = run(p, [base] * 3, t0=10.0)          # 다시 보이면 복구
    assert out2[-1][0]


def test_no_calibration_is_invalid(tmp_path):
    p = make(str(tmp_path / 'none.json'))
    v, pr, reason = run(p, [scene()])[0]
    assert not v and not pr and '보정 파일 없음' in reason


def test_image_size_mismatch_is_invalid(cal_file):
    p = make(cal_file)
    v, _, reason = run(p, [cv2.resize(scene(), (640, 480))])[0]
    assert not v and '영상 크기' in reason


def test_board_moved_updates_region(cal_file):
    p, base = make(cal_file), scene()
    M = np.float32([[1, 0, 6], [0, 1, 4]])
    moved = cv2.warpAffine(base, M, (600, 600), borderValue=(190, 190, 190))
    run(p, [base] * 5)
    c0 = p.board_corners.copy()
    out = run(p, [moved] * 8, t0=1.0)
    assert all(v for v, _, _ in out)
    assert abs(float((p.board_corners - c0)[:, 0].mean()) - 6) < 1.0
    assert not out[-1][1]                       # 이동 후 기준 화면을 새로 잡아 손 없음
