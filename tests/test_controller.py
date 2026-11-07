"""가짜 카메라 결과 / 가짜 AI / 가짜 로봇으로 상태머신 흐름 테스트 (하드웨어 불필요)"""
import numpy as np

from game import referee
from game.controller import GameController
from game.state import GameState
from robot.arm import MockArm
from robot.coords import BoardToRobot
from robot.pick_place import PickPlace
from vision.board_reader import ReadResult

N = 8


class FakeReader:
    """process() 가 미리 정한 '확정 판'을 돌려줌"""

    def __init__(self):
        self.stable = np.zeros((N, N), int)

    def reset(self):
        pass

    def process(self, frame):
        return ReadResult(np.zeros((10, 10, 3), np.uint8), self.stable.copy(), False,
                          self.stable.copy(), 10)


class FakeAI:
    def __init__(self, moves):
        self.moves = list(moves)

    def get_move(self, grid, last_move=None):
        r, c = self.moves.pop(0)
        return r, c, 0.5, 0.0


def make(moves, placer=True):
    cfg = {'board': {'n': N, 'n_in_row': 5},
           'game': {'verify_robot': True, 'verify_timeout': 5, 'save_logs': False}}
    events = []
    reader = FakeReader()
    pp = None
    if placer:
        corners = {'0,0': [0, 0], '0,7': [0, 70], '7,7': [70, 70], '7,0': [70, 0]}
        pp = PickPlace(MockArm(move_delay=0, verbose=False), BoardToRobot(N, corners))
    ctrl = GameController(reader, FakeAI(moves), pp, cfg, lambda k, d: events.append((k, d)))
    return ctrl, reader, events


FRAME = np.zeros((10, 10, 3), np.uint8)


def logs(events, level=None):
    return [d['msg'] for k, d in events if k == 'log' and (level is None or d['level'] == level)]


def test_human_then_robot_turn():
    ctrl, reader, events = make([(2, 2)])
    ctrl.start(human_first=True)
    assert ctrl.state == GameState.WAIT_EMPTY
    ctrl.step(FRAME)                                    # 빈 판 확인
    assert ctrl.state == GameState.WAIT_HUMAN

    reader.stable[3, 3] = 1                             # 사람이 흑을 둠
    ctrl.step(FRAME)
    assert ctrl.board[3, 3] == 1
    assert ctrl.state == GameState.AI_THINKING

    ctrl.step(FRAME)                                    # AI 계산 + 로봇 이동
    assert ctrl.state == GameState.VERIFY_ROBOT
    assert ctrl.pending_ai_move == (2, 2)

    reader.stable[2, 2] = 2                             # 카메라가 로봇 돌을 확인
    ctrl.step(FRAME)
    assert ctrl.board[2, 2] == 2
    assert ctrl.state == GameState.WAIT_HUMAN
    assert ctrl.move_no == 2


def test_rejects_two_new_stones():
    ctrl, reader, events = make([])
    ctrl.start(True)
    ctrl.step(FRAME)
    reader.stable[1, 1] = 1
    reader.stable[1, 2] = 1
    ctrl.step(FRAME)
    assert ctrl.state == GameState.WAIT_HUMAN
    assert ctrl.move_no == 0
    assert any('2개' in m for m in logs(events, 'warn'))


def test_robot_first_and_wrong_position():
    ctrl, reader, events = make([(4, 4)])
    ctrl.start(human_first=False)                       # 로봇이 흑
    ctrl.step(FRAME)                                    # 빈 판 -> AI 차례
    assert ctrl.state == GameState.AI_THINKING
    ctrl.step(FRAME)
    assert ctrl.state == GameState.VERIFY_ROBOT
    reader.stable[4, 5] = 1                             # 엉뚱한 곳에 놓임
    ctrl.step(FRAME)
    assert ctrl.state == GameState.VERIFY_ROBOT
    ctrl.confirm_robot_move()                           # 수동 확인
    assert ctrl.board[4, 4] == 1
    assert ctrl.state == GameState.WAIT_HUMAN


def test_manual_mode_without_robot():
    ctrl, reader, events = make([(0, 0)], placer=False)
    ctrl.start(human_first=False)
    ctrl.step(FRAME)
    ctrl.step(FRAME)
    assert ctrl.state == GameState.VERIFY_ROBOT
    assert any('놓아 주세요' in m for m in logs(events))
    reader.stable[0, 0] = 1
    ctrl.step(FRAME)
    assert ctrl.state == GameState.WAIT_HUMAN


def test_win_detection():
    ctrl, reader, events = make([(7, 0), (7, 1), (7, 2), (7, 3)])
    ctrl.start(True)
    ctrl.step(FRAME)
    for i in range(5):
        reader.stable[0, i] = 1                         # 사람 흑
        ctrl.step(FRAME)
        if ctrl.state == GameState.GAME_OVER:
            break
        ctrl.step(FRAME)                                # AI
        r, c = ctrl.pending_ai_move
        reader.stable[r, c] = 2
        ctrl.step(FRAME)
    assert ctrl.state == GameState.GAME_OVER
    assert any(k == 'game_over' and d['winner'] == 1 for k, d in events)


def test_referee():
    a = np.zeros((N, N), int)
    b = a.copy(); b[2, 3] = 1
    assert referee.validate_move(a, b, 1) == ((2, 3), None)
    assert referee.validate_move(a, b, 2)[1] is not None          # 색 틀림
    assert referee.validate_move(b, a, 2)[1] is not None          # 돌 사라짐
    assert referee.validate_move(a, a, 1) == (None, None)         # 변화 없음
    g = np.zeros((N, N), int)
    for i in range(5):
        g[i + 1, i + 2] = 2
    assert referee.winner(g) == 2
    assert referee.next_color(a) == 1 and referee.next_color(b) == 2
