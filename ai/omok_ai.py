"""
AlphaZero_Gomoku 모델 래퍼

grid (n x n, 0=빈칸 1=흑 2=백) + 직전 수 -> AI의 다음 수 (row, col)

원본: https://github.com/junxiaosong/AlphaZero_Gomoku (MIT License)
  - 흑(선공) = player 1, 백 = player 2
  - move = row * n + col  (row/col 방향은 일관되게만 쓰면 됨: 오목은 대칭)
"""
import pickle
import time

import numpy as np

from ai.alphazero.game import Board
from ai.alphazero.mcts_alphaZero import MCTSPlayer
from ai.alphazero.policy_value_net_numpy import PolicyValueNetNumpy
from utils.config import project_path


def load_params(path):
    try:
        with open(path, 'rb') as f:
            return pickle.load(f)
    except UnicodeDecodeError:                  # 파이썬2에서 저장된 pickle
        with open(path, 'rb') as f:
            return pickle.load(f, encoding='bytes')


class OmokAI:
    def __init__(self, model_path, n=8, n_in_row=5, n_playout=400, c_puct=5):
        self.n, self.n_in_row = n, n_in_row
        self.net = PolicyValueNetNumpy(n, n, load_params(model_path))
        self.player = MCTSPlayer(self.net.policy_value_fn, c_puct=c_puct, n_playout=n_playout)

    @classmethod
    def from_config(cls, cfg):
        a, b = cfg['ai'], cfg['board']
        return cls(project_path(a['model']), b['n'], b['n_in_row'], a['n_playout'], a['c_puct'])

    def make_board(self, grid, last_move=None):
        """인식된 grid -> 원본 코드의 Board 객체"""
        grid = np.asarray(grid)
        b = Board(width=self.n, height=self.n, n_in_row=self.n_in_row)
        b.init_board(0)                          # player 1(흑)부터
        for r in range(self.n):
            for c in range(self.n):
                if grid[r, c]:
                    m = r * self.n + c
                    b.states[m] = int(grid[r, c])
                    b.availables.remove(m)
        b.current_player = 1 if len(b.states) % 2 == 0 else 2
        b.last_move = last_move[0] * self.n + last_move[1] if last_move else -1
        return b

    def get_move(self, grid, last_move=None):
        """
        반환: (row, col, win_prob, seconds)
          win_prob: 두기 전 판에 대한 AI(현재 차례) 승리 예상 확률 0~1
        """
        b = self.make_board(grid, last_move)
        if not b.availables:
            raise RuntimeError('둘 곳이 없음 (판이 가득 참)')
        t0 = time.time()
        _, value = self.net.policy_value_fn(b)
        move = self.player.get_action(b)
        r, c = b.move_to_location(move)
        return int(r), int(c), float((value + 1) / 2), time.time() - t0
