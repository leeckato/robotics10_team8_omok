"""
로봇 ↔ 판 캘리브레이션 -> calib/robot_board.json

로봇팔 끝(그리퍼/흡착 노즐)을 판의 네 모서리 교차점 위에 차례로 맞추고 좌표를 기록합니다.
row/col 방향은 GUI 의 '보정 + 인식 결과' 화면과 같습니다
(row 0 = 보정 이미지 위쪽, col 0 = 왼쪽).

  python tools/calibrate_robot.py            # 로봇에서 현재 좌표를 읽음 (get_position 구현 필요)
  python tools/calibrate_robot.py --manual   # 좌표를 직접 입력 (티칭 펜던트 값 등)

좌표를 맞출 때는 tools/jog_robot.py 나 로봇 제조사 프로그램을 사용하세요.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from robot.arm import MockArm, create_arm  # noqa: E402
from robot.coords import BoardToRobot  # noqa: E402
from utils.config import load_config, project_path  # noqa: E402


def ask_xy(prompt):
    while True:
        s = input(prompt).replace(',', ' ').split()
        try:
            x, y = float(s[0]), float(s[1])
            return [x, y]
        except (ValueError, IndexError):
            print('  "x y" 형식으로 입력하세요 (예: 150 -80)')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--manual', action='store_true', help='좌표 직접 입력')
    ap.add_argument('--test', action='store_true', help='저장 후 네 모서리를 차례로 방문해서 확인')
    a = ap.parse_args()

    cfg = load_config()
    n = cfg['board']['n']
    arm = None if a.manual else create_arm(cfg)
    manual = a.manual or isinstance(arm, MockArm)
    if arm is not None:
        arm.connect()
    if manual and not a.manual:
        print('robot.driver 가 mock 이라 좌표를 직접 입력합니다.')

    names = {'0,0': '좌상단 (row 0, col 0)',
             f'0,{n - 1}': f'우상단 (row 0, col {n - 1})',
             f'{n - 1},{n - 1}': f'우하단 (row {n - 1}, col {n - 1})',
             f'{n - 1},0': f'좌하단 (row {n - 1}, col 0)'}
    corners = {}
    for key, name in names.items():
        print(f'\n▶ {name} 교차점')
        if manual:
            corners[key] = ask_xy('  로봇 좌표 x y 입력: ')
        else:
            input('  로봇팔 끝을 교차점 바로 위에 맞춘 뒤 Enter...')
            x, y, z = arm.get_position()
            corners[key] = [float(x), float(y)]
            print(f'  기록: ({x:.1f}, {y:.1f})  z={z:.1f}')

    path = project_path(cfg['paths']['robot_board'])
    BoardToRobot.save(path, n, corners)
    print('\n저장:', path)

    b2r = BoardToRobot(n, corners)
    mid = n // 2
    print(f'확인: 중앙 ({mid}, {mid}) -> 로봇 {tuple(round(v, 1) for v in b2r.to_robot(mid, mid))}')

    if a.test and arm is not None and not manual:
        z = cfg['robot']['z_safe']
        for key in names:
            r, c = map(int, key.split(','))
            x, y = b2r.to_robot(r, c)
            input(f'Enter -> ({r}, {c}) 위 z={z} 로 이동')
            arm.move_to(x, y, z)
        arm.home(cfg['robot']['home'])
    if arm is not None:
        arm.close()


if __name__ == '__main__':
    main()
