"""grid1_Color.png: 흰 종이 위 8x8 그리드, (4,5) 흑돌, (5,6) 백돌"""
import numpy as np

from vision.board_detect import detect_grid, warp_board


def test_detects_full_grid(board_img):
    pts, M, found = detect_grid(board_img, 8)
    assert pts.shape == (8, 8, 2)
    assert found >= 60                          # 백돌에 가린 1개 정도만 빠짐


def test_corner_positions(board_img):
    pts, _, _ = detect_grid(board_img, 8)
    # 사진에서 눈으로 확인한 대략적인 모서리 위치 (픽셀)
    expected = {(0, 0): (458, 194), (0, 7): (716, 193), (7, 0): (437, 451), (7, 7): (721, 451)}
    for (r, c), (x, y) in expected.items():
        assert np.hypot(*(pts[r, c] - (x, y))) < 10, (r, c, pts[r, c])


def test_warp_size(board_img):
    _, M, _ = detect_grid(board_img, 8)
    w, W = warp_board(board_img, M, 8, 60, 40)
    assert w.shape == (500, 500, 3)
    assert W.shape == (3, 3)
