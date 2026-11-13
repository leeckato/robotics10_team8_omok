"""
AI 핵심 로직 시험 (ROS 불필요)
  python3 -m pytest test/ -v      (패키지에 든 모델 사용, 다른 경로는 ALPHAZERO_PATH=...)
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from team_algorithm.ai_core import AIError, AlphaZeroAI, bundled_alphazero, check_board, find_last_move  # noqa: E402

REPO = os.path.expanduser(os.environ.get('ALPHAZERO_PATH', '') or bundled_alphazero())
need_repo = pytest.mark.skipif(not os.path.isfile(os.path.join(REPO, 'best_policy_8_8_5.model')),
                               reason='AlphaZero_Gomoku 없음 (ALPHAZERO_PATH 지정)')


def B(stones):
    b = [0] * 64
    for (r, c), v in stones.items():
        b[r * 8 + c] = v
    return b


@pytest.fixture(scope='module')
def ai():
    return AlphaZeroAI(REPO, n_playout=400)


def test_check_board():
    check_board([0] * 64, 1)
    with pytest.raises(AIError):
        check_board([0] * 64, 2)                       # 빈 판은 흑 차례
    with pytest.raises(AIError):
        check_board(B({(0, 0): 1, (0, 1): 1}), 2)      # 흑 2개 백 0개
    with pytest.raises(AIError):
        check_board([0] * 63, 1)


def test_find_last_move():
    prev = B({(3, 3): 1})
    now = B({(3, 3): 1, (4, 4): 2})
    assert find_last_move(now, prev, 1) == 4 * 8 + 4
    assert find_last_move(now, None, 1) == 4 * 8 + 4   # 모르면 상대 돌
    assert find_last_move([0] * 64, None, 1) == -1


@need_repo
def test_first_move_legal(ai):
    r, c, dt = ai.next_move([0] * 64, 1, 'g1')
    assert 0 <= r < 8 and 0 <= c < 8
    print(f'첫 수 ({r},{c}) {dt:.2f}s')


@need_repo
def test_completes_five(ai):
    # 백 차례: 백 (5,1)~(5,4) 4개 연결, (5,0)/(5,5) 비어 있음 -> 이기는 수
    b = B({(5, 1): 2, (5, 2): 2, (5, 3): 2, (5, 4): 2,
           (1, 1): 1, (1, 3): 1, (2, 6): 1, (6, 6): 1, (0, 7): 1})
    r, c, _ = ai.next_move(b, 2, 'g2')
    assert (r, c) in ((5, 0), (5, 5))


@need_repo
def test_blocks_four(ai):
    # 흑 차례: 백이 (2,2)~(2,5) 4개 -> 흑은 막아야 함
    b = B({(2, 2): 2, (2, 3): 2, (2, 4): 2, (2, 5): 2,
           (5, 0): 1, (6, 3): 1, (7, 7): 1, (5, 6): 1})
    r, c, _ = ai.next_move(b, 1, 'g3')
    assert (r, c) in ((2, 1), (2, 6))


@need_repo
def test_full_selfplay_legal(ai):
    """AI 끼리 끝까지 두어도 항상 빈칸, 차례 오류 없음"""
    board, turn = [0] * 64, 1
    for _ in range(64):
        r, c, _ = ai.next_move(board, turn, 'self')
        assert board[r * 8 + c] == 0
        board[r * 8 + c] = turn
        turn = 3 - turn
        if 0 not in board:
            break
        # 5목 나오면 종료
        from itertools import product
        done = False
        for rr, cc in product(range(8), range(8)):
            v = board[rr * 8 + cc]
            if v and any(all(0 <= rr + dr * k < 8 and 0 <= cc + dc * k < 8 and board[(rr + dr * k) * 8 + cc + dc * k] == v
                             for k in range(5)) for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1))):
                done = True
        if done:
            break
