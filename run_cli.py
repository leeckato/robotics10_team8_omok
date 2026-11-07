"""
GUI 없이 콘솔로 게임 실행 (비전/로봇 디버깅용)

  python run_cli.py                 # 사람 선공
  python run_cli.py --robot-first   # 로봇 선공
  python run_cli.py --no-show       # OpenCV 창 없이
  python run_cli.py --config my.yaml

키 (OpenCV 창 활성화 상태): r = 다시 시작, c = 로봇 수 수동 확인, q = 종료
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import cv2  # noqa: E402

from ai.omok_ai import OmokAI  # noqa: E402
from game.controller import GameController  # noqa: E402
from game.state import GameState  # noqa: E402
from gui.widgets.camera_view import draw_recognition  # noqa: E402
from robot.arm import create_arm  # noqa: E402
from robot.coords import BoardToRobot  # noqa: E402
from robot.pick_place import PickPlace  # noqa: E402
from utils.config import DEFAULT_PATH, board_geometry, load_config, project_path  # noqa: E402
from vision.board_reader import BoardReader  # noqa: E402
from vision.camera import Camera  # noqa: E402
from vision.stone_classifier import grid_to_text  # noqa: E402


def build_placer(cfg):
    try:
        coords = BoardToRobot.from_config(cfg)
        arm = create_arm(cfg)
        arm.connect()
        placer = PickPlace.from_config(cfg, arm, coords)
        placer.go_home()
        return placer
    except Exception as e:
        print(f'[로봇] {e} -> 수동 모드')
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--robot-first', action='store_true')
    ap.add_argument('--no-show', action='store_true')
    ap.add_argument('--config', default=DEFAULT_PATH)
    a = ap.parse_args()

    cfg = load_config(a.config)
    n, cell, margin = board_geometry(cfg)

    def on_event(kind, d):
        if kind == 'log':
            tag = {'info': '', 'warn': '[!] ', 'error': '[X] '}[d['level']]
            print(tag + d['msg'])
        elif kind == 'state':
            print(f'── 상태: {d["text"]}')
        elif kind == 'board':
            print(grid_to_text(d['grid']), '\n')

    ctrl = GameController(BoardReader.from_config(cfg), OmokAI.from_config(cfg),
                          build_placer(cfg), cfg, on_event,
                          log_dir=project_path(cfg['paths']['log_dir']))
    cam = Camera.from_config(cfg)
    ctrl.start(human_first=not a.robot_first)

    try:
        while True:
            frame = cam.read()
            if frame is None:
                break
            ctrl.step(frame)
            res = ctrl.last_result
            if not a.no_show and res is not None:
                cv2.imshow('omok', draw_recognition(res.warped, res.grid, n, cell, margin))
                k = cv2.waitKey(1) & 0xFF
                if k == ord('q'):
                    break
                if k == ord('r'):
                    ctrl.start(human_first=not a.robot_first)
                if k == ord('c'):
                    ctrl.confirm_robot_move()
            if ctrl.state == GameState.GAME_OVER and a.no_show:
                break
    except KeyboardInterrupt:
        pass
    cam.release()
    cv2.destroyAllWindows()


if __name__ == '__main__':
    main()
