"""
AlphaZero_Gomoku (junxiaosong) 8x8 5목 모델로 다음 수 계산. ROS 없이 동작.

팀 규격 보드  : int8[64], index = row*8 + col, 0 빈칸 / 1 흑 / 2 백, to_play 1|2
AlphaZero Board: move = h*width + w (h=row, w=col), players [1, 2], 흑(1) 선공
  -> 색 번호와 칸 번호가 그대로 같음 (omok_game.py 와 같은 대응)

AlphaZero 입력 4장 중 3번째는 '직전 수' 위치. 팀 요청에는 직전 수가 없으므로
같은 게임의 이전 요청 보드와 비교해서 찾고, 모르면 상대 돌 하나를 직전 수로 둠
(last_move=-1 로 두면 AlphaZero 가 (7,7) 쪽 칸을 직전 수로 잘못 표시함).
"""
import os
import pickle
import sys
import time

N = 8
N_IN_ROW = 5


class AIError(RuntimeError):
    pass


def bundled_alphazero():
    """패키지에 들어 있는 AlphaZero_Gomoku 복사본 (설치: share/team_algorithm/alphazero, 소스: ../alphazero)"""
    try:
        from ament_index_python.packages import get_package_share_directory
        d = os.path.join(get_package_share_directory('team_algorithm'), 'alphazero')
        if os.path.isfile(os.path.join(d, 'game.py')):
            return d
    except Exception:
        pass
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'alphazero')


def load_alphazero(repo='', model_file='best_policy_8_8_5.model'):
    """(Board 클래스, PolicyValueNetNumpy 객체, MCTSPlayer 클래스). repo 가 비어 있으면 패키지에 든 복사본"""
    repo = os.path.abspath(os.path.expanduser(repo or bundled_alphazero()))
    if not os.path.isfile(os.path.join(repo, 'game.py')):
        raise AIError(f'AlphaZero_Gomoku 없음: {repo}\n'
                      f'  git clone https://github.com/junxiaosong/AlphaZero_Gomoku.git {repo}')
    model = model_file if os.path.isabs(os.path.expanduser(model_file)) else os.path.join(repo, model_file)
    model = os.path.expanduser(model)
    if not os.path.isfile(model):
        raise AIError(f'모델 파일 없음: {model}')
    if repo not in sys.path:
        sys.path.insert(0, repo)
    from game import Board                                   # noqa: E402  (AlphaZero 저장소)
    from mcts_alphaZero import MCTSPlayer                    # noqa: E402
    from policy_value_net_numpy import PolicyValueNetNumpy   # noqa: E402
    with open(model, 'rb') as f:
        try:
            params = pickle.load(f)
        except Exception:
            f.seek(0)
            params = pickle.load(f, encoding='bytes')       # Python 2 로 저장된 모델
    return Board, PolicyValueNetNumpy(N, N, params), MCTSPlayer


def find_last_move(board, prev_board, to_play):
    """직전 수(상대가 마지막에 둔 칸) index. 모르면 상대 돌 중 하나, 돌이 없으면 -1"""
    opp = 3 - to_play
    if prev_board is not None and len(prev_board) == len(board):
        added = [i for i, (a, b) in enumerate(zip(prev_board, board)) if a == 0 and b == opp]
        if len(added) == 1:
            return added[0]
    opp_stones = [i for i, v in enumerate(board) if v == opp]
    if opp_stones:
        return opp_stones[-1]
    any_stones = [i for i, v in enumerate(board) if v]
    return any_stones[-1] if any_stones else -1


def check_board(board, to_play):
    if len(board) != N * N:
        raise AIError(f'보드 칸 수가 {len(board)} (64 필요)')
    if any(v not in (0, 1, 2) for v in board):
        raise AIError('보드 값은 0/1/2 만 가능')
    if to_play not in (1, 2):
        raise AIError(f'to_play 는 1(흑) 또는 2(백): {to_play}')
    nb, nw = board.count(1), board.count(2)
    expect = 1 if nb == nw else 2 if nb == nw + 1 else None
    if expect is None:
        raise AIError(f'돌 수가 맞지 않음 (흑 {nb}, 백 {nw})')
    if expect != to_play:
        raise AIError(f'차례가 맞지 않음: 흑 {nb}, 백 {nw} 이면 {"흑" if expect == 1 else "백"} 차례인데 to_play={to_play}')
    if 0 not in board:
        raise AIError('빈칸 없음')


class AlphaZeroAI:
    def __init__(self, repo='', model_file='best_policy_8_8_5.model', n_playout=400, c_puct=5.0):
        self.repo = os.path.abspath(os.path.expanduser(repo or bundled_alphazero()))
        self.Board, self.net, MCTSPlayer = load_alphazero(self.repo, model_file)
        self.player = MCTSPlayer(self.net.policy_value_fn, c_puct=c_puct, n_playout=int(n_playout))
        self.n_playout = int(n_playout)
        self._prev = {}          # game_id -> 마지막 요청 보드

    def make_board(self, board, to_play, last_move):
        b = self.Board(width=N, height=N, n_in_row=N_IN_ROW)
        b.init_board(start_player=0)
        b.states = {i: int(v) for i, v in enumerate(board) if v}
        b.availables = [i for i, v in enumerate(board) if not v]
        b.current_player = int(to_play)
        b.last_move = int(last_move)
        return b

    def next_move(self, board, to_play, game_id=''):
        """(row, col, 걸린 초)"""
        board = [int(v) for v in board]
        check_board(board, to_play)
        last = find_last_move(board, self._prev.get(game_id), to_play)
        b = self.make_board(board, to_play, last)
        t0 = time.monotonic()
        self.player.reset_player()
        move = int(self.player.get_action(b))
        dt = time.monotonic() - t0
        if not 0 <= move < N * N or board[move]:
            raise AIError(f'AI 가 둘 수 없는 칸을 고름: {move}')
        nxt = board.copy()
        nxt[move] = to_play
        if game_id:
            self._prev = {game_id: nxt}          # 게임은 하나씩만 진행
        row, col = divmod(move, N)
        return row, col, dt
