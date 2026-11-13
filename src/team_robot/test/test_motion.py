"""
착수 동작 계획 시험 (ROS 불필요): omok_pick_place.py 의 plan() 과 같은 좌표/순서인지
  python3 -m pytest test/ -v
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from team_robot.motion import DEFAULTS, PlanError, Planner, check_grid, load_grid  # noqa: E402

GRID = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'grid_robot_coordinates.json')


@pytest.fixture
def planner():
    return Planner(load_grid(GRID), dict(DEFAULTS))


def test_standby_is_supply_above(planner):
    sx, sy, sz = planner.standby()
    assert (sx, sy) == (273.4, -81.6)
    assert sz == pytest.approx(163.258 + 30.0)     # (0,0) Z + lift = 193.26 (supply.py Z_ABOVE 193.3)


def test_plan_matches_omok_pick_place(planner):
    steps = planner.plan(3, 2)
    kinds = [s.kind for s in steps]
    assert kinds == ['line', 'line', 'close', 'line', 'line', 'line', 'open', 'line', 'line', 'wait']
    assert [s.stage for s in steps] == ['PICKING'] * 4 + ['MOVING'] + ['PLACING'] * 3 + ['RETURNING'] * 2
    assert steps[1].xyz == [273.4, -81.6, 140.0]                       # 집기 Z
    assert steps[4].xyz == pytest.approx([398.397, 88.375, 163.248 + 30])  # (3,2) 위
    assert steps[5].xyz == pytest.approx([398.397, 88.375, 145.0])     # 놓기 Z
    assert steps[8].xyz == planner.standby()                           # 복귀 = 대기 위치


def test_row_is_x_col_is_y(planner):
    """좌표 파일: row 가 늘면 X +50, col 이 늘면 Y +50"""
    a, b, c = planner.grid[(0, 0)], planner.grid[(1, 0)], planner.grid[(0, 1)]
    assert b[0] - a[0] == pytest.approx(50, abs=0.1) and c[1] - a[1] == pytest.approx(50, abs=0.1)


def test_out_of_range(planner):
    with pytest.raises(PlanError):
        planner.plan(8, 0)


def test_low_z_rejected():
    p = dict(DEFAULTS, place_z=120.0)
    with pytest.raises(PlanError):
        Planner(load_grid(GRID), p).plan(0, 0)


def test_bad_grid(tmp_path):
    g = load_grid(GRID)
    del g[(7, 7)]
    with pytest.raises(PlanError):
        check_grid(g)
    g = load_grid(GRID)
    g[(4, 4)] = [g[(4, 4)][0] + 20, g[(4, 4)][1], g[(4, 4)][2]]
    with pytest.raises(PlanError):
        check_grid(g)
