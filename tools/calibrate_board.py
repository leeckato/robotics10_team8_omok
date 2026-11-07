"""
판(그리드) 캘리브레이션 -> calib/grid_H.npy

  python tools/calibrate_board.py                     # config.yaml 의 카메라 사용
  python tools/calibrate_board.py --image 사진.png      # 사진으로
  python tools/calibrate_board.py --cam 1              # 카메라 번호 지정

카메라 모드 키:  c = 지금 화면으로 검출/저장,  s = 화면 저장,  q = 종료
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from utils.config import board_geometry, load_config, project_path, warp_size  # noqa: E402
from vision.board_detect import (apply_warp, detect_grid, draw_grid_overlay,  # noqa: E402
                                 draw_warped_points, warp_matrix)
from vision.camera import Camera  # noqa: E402


def calibrate(img, cfg):
    n, cell, margin = board_geometry(cfg)
    try:
        pts, M, found = detect_grid(img, n)
    except Exception as e:
        print('검출 실패:', e)
        return None, None
    print(f'교차점 {found}/{n * n}개 검출')
    if found < n * n * 0.7:
        print('경고: 검출된 점이 너무 적음. 판 전체가 보이는지, 돌/손이 없는지 확인하세요.')
    return warp_matrix(M, cell, margin), pts


def save(W, cfg):
    path = project_path(cfg['paths']['grid_H'])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    np.save(path, W)
    print('저장:', path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--image')
    ap.add_argument('--cam', type=int)
    ap.add_argument('--no-show', action='store_true', help='창 없이 파일로만 저장')
    a = ap.parse_args()

    cfg = load_config()
    n, cell, margin = board_geometry(cfg)
    size = warp_size(cfg)

    if a.image:
        img = cv2.imread(a.image)
        if img is None:
            raise SystemExit(f'이미지를 열 수 없음: {a.image}')
        W, pts = calibrate(img, cfg)
        if W is None:
            return
        save(W, cfg)
        orig = draw_grid_overlay(img, pts)
        warped = draw_warped_points(apply_warp(img, W, size), n, cell, margin)
        cv2.imwrite(project_path('calib/board_overlay.png'), orig)
        cv2.imwrite(project_path('calib/board_warped.png'), warped)
        print('확인용 이미지: calib/board_overlay.png, calib/board_warped.png')
        if not a.no_show:
            cv2.imshow('detected', orig)
            cv2.imshow('warped', warped)
            cv2.waitKey(0)
            cv2.destroyAllWindows()
        return

    source = a.cam if a.cam is not None else cfg['camera']['source']
    cam = Camera(source, cfg['camera']['width'], cfg['camera']['height'])
    gpath = project_path(cfg['paths']['grid_H'])
    W = np.load(gpath) if os.path.exists(gpath) else None
    print("빈 판을 비추고 'c' 를 누르세요 (s: 저장, q: 종료)")
    while True:
        frame = cam.read()
        if frame is None:
            break
        cv2.imshow('camera', frame)
        if W is not None:
            cv2.imshow('warped', draw_warped_points(apply_warp(frame, W, size), n, cell, margin))
        k = cv2.waitKey(1) & 0xFF
        if k == ord('c'):
            newW, pts = calibrate(frame, cfg)
            if newW is not None:
                W = newW
                save(W, cfg)
                cv2.imshow('detected', draw_grid_overlay(frame, pts))
        elif k == ord('s'):
            cv2.imwrite(project_path('calib/cam_frame.png'), frame)
            print('저장: calib/cam_frame.png')
        elif k == ord('q'):
            break
    cam.release()
    cv2.destroyAllWindows()


if __name__ == '__main__':
    main()
