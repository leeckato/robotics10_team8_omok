"""
ROS 없이 판정 로직 시험 (합성 바둑판 영상)
  python3 -m pytest test/test_processor.py -v      (패키지 폴더에서)
"""
import os
import sys
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from team_hand.processor import HandProcessor, fill_image_msg, image_msg_to_bgr, parse_polygon  # noqa: E402

FPS = 30
RNG = np.random.default_rng(0)


def board_frame(angle=0.0):
    """회색 책상 위 흰 종이에 8x8 그리드 (1280x720)"""
    img = np.full((720, 1280, 3), (95, 100, 105), np.uint8)
    cv2.rectangle(img, (380, 120), (900, 620), (235, 238, 240), -1)
    for i in range(8):
        x = 460 + i * 50
        y = 195 + i * 50
        cv2.line(img, (460, y), (810, y), (40, 40, 40), 2)
        cv2.line(img, (x, 195), (x, 545), (40, 40, 40), 2)
    if angle:
        M = cv2.getRotationMatrix2D((640, 360), angle, 1.0)
        img = cv2.warpAffine(img, M, (1280, 720), borderValue=(95, 100, 105))
    return img


def noisy(img):
    return np.clip(img.astype(np.int16) + RNG.normal(0, 2, img.shape), 0, 255).astype(np.uint8)


def with_hand(img, k):
    """k=0: 화면 아래 밖, k=1: 판 중앙까지 들어옴 (살색 손 + 소매)"""
    f = img.copy()
    cy = int(800 - k * (800 - 330))
    cv2.rectangle(f, (590, cy + 50), (690, 900), (60, 60, 140), -1)
    cv2.ellipse(f, (640, cy + 20), (55, 75), 0, 0, 360, (120, 160, 215), -1)
    return f


def run(proc, frames):
    out = []
    for i, f in enumerate(frames):
        r = proc.process(noisy(f), i / FPS)
        out.append((r.valid, r.present, r.reason))
    return out


def make(**kw):
    return HandProcessor({'method': 'diff', 'roi_mode': 'grid', **kw}, log=lambda *_: None)


def test_grid_found_and_hand_cycle():
    base = board_frame()
    frames = [base] * 30
    frames += [with_hand(base, min(1, i / 10)) for i in range(40)]      # 들어와서 머묾
    frames += [with_hand(base, max(0, 1 - i / 10)) for i in range(15)]  # 나감
    frames += [base] * 30
    res = run(make(), frames)
    assert all(v for v, _, _ in res)                                  # 판을 찾았으므로 전부 valid
    present = [p for _, p, _ in res]
    assert not any(present[:30])                                      # 처음엔 손 없음
    assert any(present[35:70])                                        # 손 들어옴
    assert not any(present[-15:])                                     # 손 나간 뒤 손 없음


def test_no_board_is_invalid_not_absent():
    blank = np.full((720, 1280, 3), 100, np.uint8)
    res = run(make(), [blank] * 20)
    assert all(not v for v, _, _ in res)
    assert '그리드' in res[0][2] or '판 영역' in res[0][2]


def test_stone_is_not_hand():
    base = board_frame()
    stone = base.copy()
    cv2.circle(stone, (560, 345), 20, (25, 25, 25), -1)
    res = run(make(), [base] * 20 + [stone] * 40)
    assert all(v for v, _, _ in res)
    assert not any(p for _, p, _ in res)


def test_grid_ignores_outside_but_full_does_not():
    base = board_frame()
    out = base.copy()
    cv2.rectangle(out, (1000, 300), (1200, 500), (120, 160, 215), -1)   # 판 밖의 '손'
    frames = [base] * 20 + [out] * 30
    assert not any(p for _, p, _ in run(make(roi_mode='grid'), frames))
    assert any(p for _, p, _ in run(make(roi_mode='full'), frames))


def test_polygon_mode():
    base = board_frame()
    out = base.copy()
    cv2.rectangle(out, (1000, 300), (1200, 500), (120, 160, 215), -1)
    poly = '430,145 840,145 840,595 430,595'
    frames = [base] * 20 + [out] * 30
    assert not any(p for _, p, _ in run(make(roi_mode='polygon', roi_polygon=poly), frames))
    assert len(parse_polygon(poly)) == 4


def test_rotated_camera():
    base = board_frame(angle=12)
    frames = [base] * 20 + [with_hand(base, 1)] * 20
    res = run(make(), frames)
    assert all(v for v, _, _ in res)
    assert any(p for _, p, _ in res[20:])


def test_failure_is_invalid():
    p = make(roi_mode='full')
    r = p.process(np.zeros((10, 10), np.uint8), 0.0)                   # 흑백 2차원 -> 검사 실패
    assert r.valid is False and '검사 실패' in r.reason


def test_image_msg_conversion():
    bgr = (RNG.random((4, 5, 3)) * 255).astype(np.uint8)
    msg = fill_image_msg(SimpleNamespace(), bgr, header='h')
    assert msg.encoding == 'bgr8' and msg.step == 15
    assert np.array_equal(image_msg_to_bgr(msg), bgr)
    # 줄 끝 여백(step > width*3) + rgb8
    pad = np.zeros((4, 20), np.uint8)
    pad[:, :15] = bgr[:, :, ::-1].reshape(4, 15)
    m2 = SimpleNamespace(encoding='rgb8', height=4, width=5, step=20, data=pad.tobytes())
    assert np.array_equal(image_msg_to_bgr(m2), bgr)
    with pytest.raises(ValueError):
        image_msg_to_bgr(SimpleNamespace(encoding='mono8', height=4, width=5, step=5, data=b'0' * 20))
