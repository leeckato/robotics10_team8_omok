"""
착수 동작 계획 (ROS 없음). board_control/omok_pick_place.py 의 plan() / pick_steps() 와 같은 순서와 값.

  대기 위치(standby) = 공급 위치 위 (SUPPLY_X, SUPPLY_Y, (0,0) 격자 Z + lift)
  1 공급 위로 이동 -> 2 집기 Z 로 하강 -> 3 그리퍼 닫기 -> 4 들어 올리기
  5 목표 칸 위로 -> 6 놓기 Z 로 하강 -> 7 그리퍼 열기 -> 8 상승
  9 공급 위치(대기 위치)로 복귀 -> 10 그리퍼 대기 값

좌표: grid_robot_coordinates.json (BASE, mm, 키 "row,col"). 픽셀 좌표는 쓰지 않음.
"""
import json
import math
import os
from dataclasses import dataclass, field

N = 8

# omok_pick_place.py 값 (J6 +90도, SPEED_SCALE 1.8)
DEFAULTS = dict(
    grid_json='~/ros2_ws/board_control/grid_robot_coordinates.json',
    rotation=[4.9588, 179.5272, 94.7379],         # 4.7379 + 90
    home_joint=[0.0, 0.0, 90.0, 0.0, 90.0, 90.0],
    vel=90.0, vel_rot=54.0, acc=90.0, acc_rot=54.0,
    joint_vel=36.0, joint_acc=36.0,
    lift=30.0, place_z=145.0, pick_z=140.0,
    supply_x=273.4, supply_y=-81.6,
    min_z=139.0,                                   # 이보다 낮은 목표는 거부 (집기 Z 140)
)


class PlanError(ValueError):
    pass


def load_grid(path):
    """{(row, col): [x, y, z]}  (omok_pick_place.load_grid 와 같은 형식 지원)"""
    with open(os.path.expanduser(path), encoding='utf-8') as f:
        data = json.load(f)
    if isinstance(data, dict) and isinstance(data.get('grid'), dict):
        data = data['grid']
    grid = {}
    for key, val in data.items():
        try:
            r, c = [int(s) for s in key.split(',')]
        except ValueError:
            continue
        if isinstance(val, dict):
            xyz = val['pos'][:3] if 'pos' in val else [val.get('x', val.get('X')), val.get('y', val.get('Y')),
                                                       val.get('z', val.get('Z'))]
        else:
            xyz = list(val)[:3]
        if len(xyz) == 3 and None not in xyz:
            grid[(r, c)] = [float(a) for a in xyz]
    return grid


def check_grid(grid, gap=50.0, tol=5.0):
    """64칸 모두 있고 이웃 간격이 gap±tol 인지 (test_all_grid.check_mapping 과 같은 기준)"""
    missing = [(r, c) for r in range(N) for c in range(N) if (r, c) not in grid]
    if missing:
        raise PlanError(f'좌표 파일에 칸이 없음: {missing[:5]}')
    for r in range(N):
        for c in range(N):
            p = grid[(r, c)]
            if not all(math.isfinite(v) for v in p):
                raise PlanError(f'({r},{c}) 좌표가 숫자가 아님')
            for nr, nc in ((r + 1, c), (r, c + 1)):
                if nr < N and nc < N and abs(math.dist(p, grid[(nr, nc)]) - gap) > tol:
                    raise PlanError(f'격자 간격 오류: ({r},{c})->({nr},{nc}) {math.dist(p, grid[(nr, nc)]):.1f}mm')


@dataclass
class Step:
    stage: str          # PICKING / MOVING / PLACING / RETURNING (규격 feedback)
    name: str
    kind: str           # line / close / open / wait
    xyz: list = field(default=None)


class Planner:
    def __init__(self, grid, p):
        self.grid, self.p = grid, p
        check_grid(grid)

    def standby(self):
        p = self.p
        return [p['supply_x'], p['supply_y'], self.grid[(0, 0)][2] + p['lift']]

    def plan(self, row, col):
        p = self.p
        if not (0 <= row < N and 0 <= col < N):
            raise PlanError(f'범위 밖: ({row},{col})')
        above = self.standby()
        tx, ty, tz = self.grid[(row, col)]
        steps = [
            Step('PICKING', '공급 위로 이동', 'line', above),
            Step('PICKING', f'공급 돌로 하강 (Z={p["pick_z"]:.0f})', 'line', [p['supply_x'], p['supply_y'], p['pick_z']]),
            Step('PICKING', '그리퍼 닫기 (잡기)', 'close'),
            Step('PICKING', '들어 올리기', 'line', above),
            Step('MOVING', f'({row},{col}) 위로 이동', 'line', [tx, ty, tz + p['lift']]),
            Step('PLACING', f'({row},{col})로 하강 (Z={p["place_z"]:.0f})', 'line', [tx, ty, p['place_z']]),
            Step('PLACING', '그리퍼 열기 (놓기)', 'open'),
            Step('PLACING', '상승', 'line', [tx, ty, tz + p['lift']]),
            Step('RETURNING', '공급 위치(대기 위치)로 복귀', 'line', above),
            Step('RETURNING', '그리퍼 대기 값', 'wait'),
        ]
        for s in steps:
            if s.xyz is not None and s.xyz[2] < p['min_z']:
                raise PlanError(f'{s.name}: Z={s.xyz[2]:.1f} 가 최저 높이 {p["min_z"]} 보다 낮음')
        return steps
