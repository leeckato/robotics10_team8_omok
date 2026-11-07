"""
돌 판별 캘리브레이션 -> calib/stone_thresholds.json
(GUI 의 [캘리브레이션] > [② 돌 판별] 과 같은 기능의 OpenCV 창 버전)

  python tools/calibrate_stones.py
  python tools/calibrate_stones.py --image 사진.png    # 사진 한 장으로 라벨링

키
  e : 지금 화면을 '빈 판 기준'으로 저장 (돌이 없을 때)
  g : 지금 화면 가져오기 (현재 인식 결과로 라벨 초기화)
  마우스 : 왼쪽 클릭 = 빈칸→흑→백 순환, 오른쪽 클릭 = 빈칸
  a : 현재 라벨을 학습 샘플로 추가
  f : 학습 + 저장
  t : 인식 테스트 (콘솔에 결과 출력)
  q : 종료
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from gui.widgets.camera_view import draw_recognition  # noqa: E402
from utils.config import board_geometry, load_config, project_path, warp_size  # noqa: E402
from vision.board_detect import apply_warp  # noqa: E402
from vision.camera import Camera  # noqa: E402
from vision.stone_classifier import StoneClassifier, grid_to_text  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--image')
    a = ap.parse_args()

    cfg = load_config()
    n, cell, margin = board_geometry(cfg)
    size = warp_size(cfg)
    gpath = project_path(cfg['paths']['grid_H'])
    if not os.path.exists(gpath):
        raise SystemExit('먼저 python tools/calibrate_board.py 로 판 캘리브레이션을 하세요')
    W = np.load(gpath)
    clf = StoneClassifier.from_config(cfg)
    model_path = project_path(cfg['paths']['stone_model'])

    cam = Camera(a.image if a.image else cfg['camera']['source'],
                 cfg['camera']['width'], cfg['camera']['height'])
    st = {'warped': None, 'labels': np.zeros((n, n), int)}
    samples = []

    def on_mouse(ev, x, y, flags, _):
        if st['warped'] is None or ev not in (cv2.EVENT_LBUTTONDOWN, cv2.EVENT_RBUTTONDOWN):
            return
        c, r = int(round((x - margin) / cell)), int(round((y - margin) / cell))
        if 0 <= r < n and 0 <= c < n:
            lab = st['labels']
            lab[r, c] = 0 if ev == cv2.EVENT_RBUTTONDOWN else (lab[r, c] + 1) % 3

    cv2.namedWindow('label')
    cv2.setMouseCallback('label', on_mouse)
    print(__doc__)
    while True:
        frame = cam.read()
        if frame is None:
            break
        live = apply_warp(frame, W, size)
        cv2.imshow('live', live)
        if st['warped'] is not None:
            cv2.imshow('label', draw_recognition(st['warped'], st['labels'], n, cell, margin))
        k = cv2.waitKey(30) & 0xFF
        if k == ord('e'):
            clf.set_reference(live)
            samples.clear()
            clf.save(model_path)
            print('빈 판 기준 저장 완료')
        elif k == ord('g'):
            st['warped'] = live.copy()
            st['labels'] = clf.classify(live)
            print('화면 가져옴. 틀린 칸을 클릭해서 고치세요.')
        elif k == ord('a') and st['warped'] is not None:
            samples.append((st['warped'].copy(), st['labels'].copy()))
            print(f'샘플 {len(samples)}개 (흑 {(st["labels"] == 1).sum()}, 백 {(st["labels"] == 2).sum()})')
        elif k == ord('f'):
            if not samples:
                print('샘플이 없습니다 (a 로 추가)')
                continue
            clf.fit_many(samples)
            clf.save(model_path)
            print('학습 + 저장 완료:', model_path, clf.model.get('counts'))
        elif k == ord('t'):
            print(grid_to_text(clf.classify(live)), '\n')
        elif k == ord('q'):
            break
    cam.release()
    cv2.destroyAllWindows()


if __name__ == '__main__':
    main()
