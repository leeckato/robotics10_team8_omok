"""
로봇팔 수동 조작 (콘솔)

  python tools/jog_robot.py

명령 (입력 후 Enter, 여러 개 이어서 입력 가능: 예 'www' = x+ 세 번)
  w / s : x + / -        a / d : y + / -        r / f : z + / -
  + / - : 이동 간격 2배 / 절반
  g     : 집기/놓기 전환
  h     : 대기 위치(home)로
  m x y z : 해당 좌표로 이동 (예: m 150 0 80)
  b r c : 판 (row, col) 위 z_safe 로 이동 (robot_board.json 필요)
  p     : 현재 좌표 출력
  q     : 종료
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from robot.arm import create_arm  # noqa: E402
from robot.coords import BoardToRobot  # noqa: E402
from utils.config import load_config  # noqa: E402

KEYS = {'w': (0, 1), 's': (0, -1), 'a': (1, 1), 'd': (1, -1), 'r': (2, 1), 'f': (2, -1)}


def main():
    cfg = load_config()
    arm = create_arm(cfg)
    arm.connect()
    try:
        b2r = BoardToRobot.from_config(cfg)
    except FileNotFoundError:
        b2r = None
    pos = list(arm.get_position())
    step, gripping = 10.0, False
    print(__doc__)

    while True:
        cmd = input(f'[{pos[0]:.1f}, {pos[1]:.1f}, {pos[2]:.1f}] step={step:g} > ').strip()
        if not cmd:
            continue
        parts = cmd.split()
        if parts[0] == 'q':
            break
        if parts[0] == 'm' and len(parts) == 4:
            pos = [float(v) for v in parts[1:]]
            arm.move_to(*pos)
            continue
        if parts[0] == 'b' and len(parts) == 3:
            if b2r is None:
                print('robot_board.json 이 없습니다 (tools/calibrate_robot.py)')
                continue
            x, y = b2r.to_robot(int(parts[1]), int(parts[2]))
            pos = [x, y, cfg['robot']['z_safe']]
            arm.move_to(*pos)
            continue
        moved = False
        for ch in cmd:
            if ch in KEYS:
                axis, sign = KEYS[ch]
                pos[axis] += sign * step
                moved = True
            elif ch == '+':
                step *= 2
            elif ch == '-':
                step = max(0.5, step / 2)
            elif ch == 'g':
                gripping = not gripping
                arm.grip(gripping)
            elif ch == 'h':
                arm.home(cfg['robot']['home'])
                pos = list(arm.get_position())
            elif ch == 'p':
                print('현재:', arm.get_position())
        if moved:
            arm.move_to(*pos)
    arm.close()


if __name__ == '__main__':
    main()
