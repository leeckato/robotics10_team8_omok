import numpy as np
import pytest

from ai.omok_ai import OmokAI
from utils.config import project_path


@pytest.fixture(scope='module')
def ai():
    return OmokAI(project_path('ai/alphazero/best_policy_8_8_5.model'), 8, 5, n_playout=400)


def test_first_move_is_valid(ai):
    r, c, p, sec = ai.get_move(np.zeros((8, 8), int))
    assert 0 <= r < 8 and 0 <= c < 8
    assert 0.0 <= p <= 1.0


def test_completes_five(ai):
    g = np.zeros((8, 8), int)
    g[2, 1:5] = 2                          # 백 4개 (AI = 백 차례)
    g[5, [0, 2, 4, 6]] = 1
    g[7, 7] = 1                            # 흑 5개, 백 4개 -> 백 차례
    r, c, _, _ = ai.get_move(g, (7, 7))
    assert (r, c) in [(2, 0), (2, 5)]


def test_blocks_closed_four(ai):
    g = np.zeros((8, 8), int)
    g[3, 1:5] = 1                          # 흑 4개, 왼쪽은 백이 막음
    g[3, 0] = 2
    g[6, 6] = 2
    g[7, 0] = 2                            # 흑 4, 백 3 -> 백 차례
    r, c, _, _ = ai.get_move(g, (3, 4))
    assert (r, c) == (3, 5)
