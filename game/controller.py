"""
게임 진행 상태머신 (Qt 를 모르는 순수 파이썬)

GUI(game_worker)와 콘솔(run_cli)이 같은 컨트롤러를 씁니다.
진행 상황은 on_event(kind, data) 콜백으로 알립니다.

  kind        data
  'state'     {'state': GameState, 'text': str}
  'vision'    {'result': ReadResult}             매 프레임
  'board'     {'grid': ndarray, 'last_move': (r, c) | None, 'move_no': int}
  'ai'        {'row', 'col', 'win_prob', 'seconds'}
  'log'       {'msg': str, 'level': 'info' | 'warn' | 'error'}
  'game_over' {'winner': 0 | 1 | 2, 'text': str}

로봇(placer)이 None 이면 '수동 모드': 사람이 AI 대신 돌을 놓아 주면 됩니다.
"""
import os
import time
from datetime import datetime

import cv2
import numpy as np

from game import referee
from game.state import COLOR_NAME, STATE_TEXT, GameState


class GameController:
    def __init__(self, reader, ai, placer=None, cfg=None, on_event=None, log_dir=None):
        cfg = cfg or {}
        g = cfg.get('game', {})
        self.reader, self.ai, self.placer = reader, ai, placer
        self.n = cfg.get('board', {}).get('n', 8)
        self.n_in_row = cfg.get('board', {}).get('n_in_row', 5)
        self.verify_robot = g.get('verify_robot', True)
        self.verify_timeout = g.get('verify_timeout', 20)
        self.on_event = on_event or (lambda kind, data: None)
        self.log_dir = log_dir if g.get('save_logs', True) else None

        self.state = GameState.IDLE
        self.board = np.zeros((self.n, self.n), int)
        self.human_color, self.ai_color = 1, 2
        self.last_move = None
        self.pending_ai_move = None
        self._last_warned = None
        self._verify_start = 0.0
        self._timeout_warned = False
        self._session_dir = None
        self._last_warped = None
        self.last_result = None        # 마지막 ReadResult (화면 표시용)

    # ───────── 외부에서 호출 ─────────
    def start(self, human_first=True):
        self.board[:] = 0
        self.last_move = None
        self.pending_ai_move = None
        self._last_warned = None
        self.human_color, self.ai_color = (1, 2) if human_first else (2, 1)
        self.reader.reset()
        if self.log_dir:
            self._session_dir = os.path.join(self.log_dir, datetime.now().strftime('%Y%m%d_%H%M%S'))
            os.makedirs(self._session_dir, exist_ok=True)
        self._log(f'게임 시작: 사람={COLOR_NAME[self.human_color]}, 로봇={COLOR_NAME[self.ai_color]}'
                  + ('' if self.placer else '  [수동 모드: 로봇 대신 사람이 AI 수를 놓아 주세요]'))
        self._emit_board()
        self._set_state(GameState.WAIT_EMPTY)

    def stop(self):
        self._set_state(GameState.IDLE)
        self._log('게임 중지')

    def confirm_robot_move(self):
        """로봇 돌 확인이 계속 실패할 때 GUI에서 '수동 확인' 버튼으로 강제 진행"""
        if self.state == GameState.VERIFY_ROBOT and self.pending_ai_move:
            self._log('로봇 수를 수동으로 확인 처리', 'warn')
            self._accept_move(self.pending_ai_move, self.ai_color, by_ai=True)

    @property
    def move_no(self):
        return int((self.board != 0).sum())

    # ───────── 매 프레임 호출 ─────────
    def step(self, frame):
        if frame is None:
            return
        res = self.reader.process(frame)
        self.last_result = res
        self._last_warped = res.warped
        self.on_event('vision', {'result': res})

        s = self.state
        if s == GameState.WAIT_EMPTY:
            self._on_wait_empty(res)
        elif s == GameState.WAIT_HUMAN:
            self._on_wait_human(res)
        elif s == GameState.AI_THINKING:
            self._do_ai_turn()
        elif s == GameState.VERIFY_ROBOT:
            self._on_verify_robot(res)

    # ───────── 상태별 처리 ─────────
    def _on_wait_empty(self, res):
        if res.stable is None:
            return
        if (res.stable != 0).any():
            self._warn_once(res.stable, '판 위에 돌이 있습니다. 판을 비워 주세요')
            return
        self._log('빈 판 확인 완료')
        self._next_turn()

    def _on_wait_human(self, res):
        if res.stable is None or np.array_equal(res.stable, self.board):
            return
        move, err = referee.validate_move(self.board, res.stable, self.human_color)
        if err:
            self._warn_once(res.stable, f'인식 확인 필요: {err}')
            return
        if move:
            self._accept_move(move, self.human_color)

    def _do_ai_turn(self):
        try:
            r, c, p, sec = self.ai.get_move(self.board, self.last_move)
        except Exception as e:
            self._error(f'AI 오류: {e}')
            return
        self.pending_ai_move = (r, c)
        self.on_event('ai', {'row': r, 'col': c, 'win_prob': p, 'seconds': sec})
        self._log(f'AI 결정: ({r}, {c})  승률 예상 {p * 100:.0f}%  ({sec:.1f}초)')

        if self.placer is None:
            self._log(f'▶ ({r}, {c}) 에 {COLOR_NAME[self.ai_color]}돌을 놓아 주세요 (수동 모드)', 'warn')
        else:
            self._set_state(GameState.ROBOT_MOVING)
            try:
                self.placer.place(r, c, on_step=lambda s: self._log(f'로봇: {s}'))
            except Exception as e:
                self._error(f'로봇 오류: {e}')
                return

        if self.verify_robot or self.placer is None:
            self._verify_start = time.time()
            self._timeout_warned = False
            self._set_state(GameState.VERIFY_ROBOT)
        else:
            self._accept_move((r, c), self.ai_color, by_ai=True)

    def _on_verify_robot(self, res):
        if self.placer and not self._timeout_warned and \
                time.time() - self._verify_start > self.verify_timeout:
            self._timeout_warned = True
            self._log('로봇 돌이 인식되지 않음. 돌 위치를 확인하거나 [수동 확인]을 누르세요', 'warn')
        if res.stable is None or np.array_equal(res.stable, self.board):
            return
        move, err = referee.validate_move(self.board, res.stable, self.ai_color)
        if err:
            self._warn_once(res.stable, f'로봇 수 확인 실패: {err}')
            return
        if move and move != self.pending_ai_move:
            self._warn_once(res.stable, f'AI 수는 {self.pending_ai_move} 인데 {move} 에 놓임')
            return
        if move:
            self._accept_move(move, self.ai_color, by_ai=True)

    # ───────── 공통 ─────────
    def _accept_move(self, move, color, by_ai=False):
        r, c = move
        self.board[r, c] = color
        self.last_move = (r, c)
        self.pending_ai_move = None
        self._last_warned = None
        who = '로봇' if by_ai else '사람'
        self._log(f'{self.move_no}수: {who}({COLOR_NAME[color]}) ({r}, {c})')
        self._emit_board()
        self._save_snapshot()

        w = referee.winner(self.board, self.n_in_row)
        if w:
            text = f'{"로봇" if w == self.ai_color else "사람"}({COLOR_NAME[w]}) 승리!'
            self._finish(w, text)
        elif referee.is_full(self.board):
            self._finish(0, '무승부')
        else:
            self._next_turn()

    def _next_turn(self):
        color = referee.next_color(self.board)
        self._set_state(GameState.WAIT_HUMAN if color == self.human_color else GameState.AI_THINKING)

    def _finish(self, winner, text):
        self._set_state(GameState.GAME_OVER)
        self._log(text)
        self.on_event('game_over', {'winner': winner, 'text': text})

    def _set_state(self, s):
        self.state = s
        self.on_event('state', {'state': s, 'text': STATE_TEXT[s]})

    def _emit_board(self):
        self.on_event('board', {'grid': self.board.copy(), 'last_move': self.last_move,
                                'move_no': self.move_no})

    def _log(self, msg, level='info'):
        self.on_event('log', {'msg': msg, 'level': level})

    def _warn_once(self, grid, msg):
        """같은 판 상태에 대해 경고를 한 번만"""
        if self._last_warned is None or not np.array_equal(self._last_warned, grid):
            self._last_warned = grid.copy()
            self._log(msg, 'warn')

    def _error(self, msg):
        self._log(msg, 'error')
        self._set_state(GameState.ERROR)

    def _save_snapshot(self):
        if not self._session_dir or self._last_warped is None:
            return
        base = os.path.join(self._session_dir, f'move_{self.move_no:02d}')
        cv2.imwrite(base + '.png', self._last_warped)
        np.savetxt(base + '.txt', self.board, fmt='%d')
