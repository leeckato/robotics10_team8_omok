import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import cv2  # noqa: E402
import pytest  # noqa: E402

IMG = os.path.join(ROOT, 'tests', 'images', 'grid1_Color.png')


@pytest.fixture(scope='session')
def board_img():
    img = cv2.imread(IMG)
    assert img is not None, IMG
    return img


@pytest.fixture(scope='session')
def warped(board_img):
    from vision.board_detect import detect_grid, warp_board
    _, M, _ = detect_grid(board_img, 8)
    w, _ = warp_board(board_img, M, 8, 60, 40)
    return w
