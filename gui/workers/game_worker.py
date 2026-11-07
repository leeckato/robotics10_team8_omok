"""
게임 스레드: GameController 를 실행하고 결과를 Qt signal 로 GUI 에 전달

AI 계산(1초 내외)과 로봇 이동(수 초)이 이 스레드에서 실행되므로 GUI 는 멈추지 않습니다.
GUI 에서는 start_game / stop_game / confirm_robot / reload 만 호출하면 됩니다.
"""
import queue
import time

from PySide6.QtCore import QThread, Signal

from ai.omok_ai import OmokAI
from game.controller import GameController
from game.state import GameState
from robot.arm import create_arm
from robot.coords import BoardToRobot
from robot.pick_place import PickPlace
from utils.config import project_path
from vision.board_reader import BoardReader


class GameWorker(QThread):
    state_changed = Signal(str, str)              # state.value, 표시 문자열
    vision_updated = Signal(object)               # ReadResult
    board_updated = Signal(object, object, int)   # grid, last_move, move_no
    ai_move = Signal(int, int, float, float)      # row, col, win_prob, seconds
    log = Signal(str, str)                        # msg, level
    game_over = Signal(int, str)                  # winner, text
    mode_changed = Signal(str)                    # '로봇' / '수동'

    def __init__(self, cfg, get_frame, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.get_frame = get_frame                # 최신 카메라 프레임을 돌려주는 함수
        self._cmd = queue.Queue()
        self._running = False
        self.ctrl = None
        self._arm = None
        self._vision_interval = 1.0 / max(1, cfg['camera'].get('preview_fps', 15))

    # ───────── GUI 스레드에서 호출 (명령만 넣음) ─────────
    def start_game(self, human_first):
        self._cmd.put(('start', human_first))

    def stop_game(self):
        self._cmd.put(('stop', None))

    def confirm_robot(self):
        self._cmd.put(('confirm', None))

    def reload(self):
        """캘리브레이션/설정 변경 후 구성요소 다시 만들기"""
        self._cmd.put(('reload', None))

    def stop(self):
        self._running = False
        self.wait(5000)

    # ───────── 스레드 본체 ─────────
    def run(self):
        self._running = True
        self._build()
        last_vision = 0.0
        while self._running:
            self._handle_commands()
            if self.ctrl is None:
                self.msleep(200)
                continue

            frame = self.get_frame()
            if frame is not None:
                if self.ctrl.state in (GameState.IDLE, GameState.GAME_OVER, GameState.ERROR):
                    # 게임 중이 아니어도 인식 결과는 계속 보여줌 (시작 전 점검용)
                    res = self.ctrl.reader.process(frame)
                    now = time.time()
                    if now - last_vision >= self._vision_interval:
                        last_vision = now
                        self.vision_updated.emit(res)
                else:
                    self.ctrl.step(frame)
            self.msleep(30)

        if self._arm is not None:
            try:
                self._arm.close()
            except Exception:
                pass

    def _handle_commands(self):
        while True:
            try:
                cmd, arg = self._cmd.get_nowait()
            except queue.Empty:
                return
            if cmd == 'reload':
                self._build()
            elif self.ctrl is None:
                self.log.emit('준비되지 않음: 판 캘리브레이션을 먼저 하세요', 'error')
            elif cmd == 'start':
                self.ctrl.start(arg)
            elif cmd == 'stop':
                self.ctrl.stop()
            elif cmd == 'confirm':
                self.ctrl.confirm_robot_move()

    def _build(self):
        """비전/AI/로봇 구성요소 생성. 실패해도 스레드는 살아 있고 reload 로 재시도"""
        self.ctrl = None
        try:
            reader = BoardReader.from_config(self.cfg)
            if not reader.classifier.is_calibrated:
                self.log.emit('돌 판별 캘리브레이션 없음 → 기본 규칙 사용 '
                              '(흰 종이 위 흰 돌은 인식이 어려움)', 'warn')
        except Exception as e:
            self.log.emit(str(e), 'error')
            return
        try:
            ai = OmokAI.from_config(self.cfg)
        except Exception as e:
            self.log.emit(f'AI 모델 로드 실패: {e}', 'error')
            return

        placer = self._build_robot()
        self.mode_changed.emit('로봇' if placer else '수동')
        self.ctrl = GameController(reader, ai, placer, self.cfg, self._on_event,
                                   log_dir=project_path(self.cfg['paths']['log_dir']))
        self.log.emit('준비 완료', 'info')
        self.state_changed.emit(self.ctrl.state.value, '대기 (게임 시작 전)')

    def _build_robot(self):
        try:
            coords = BoardToRobot.from_config(self.cfg)
        except FileNotFoundError as e:
            self.log.emit(f'{e} → 수동 모드로 진행', 'warn')
            return None
        try:
            if self._arm is not None:
                self._arm.close()
            self._arm = create_arm(self.cfg)
            self._arm.connect()
            placer = PickPlace.from_config(self.cfg, self._arm, coords)
            placer.go_home()
            return placer
        except Exception as e:
            self.log.emit(f'로봇 연결 실패: {e} → 수동 모드로 진행', 'warn')
            self._arm = None
            return None

    def _on_event(self, kind, d):
        """GameController 콜백 -> Qt signal (이 스레드에서 호출됨)"""
        if kind == 'state':
            self.state_changed.emit(d['state'].value, d['text'])
        elif kind == 'vision':
            now = time.time()
            if now - getattr(self, '_last_vision_emit', 0.0) >= self._vision_interval:
                self._last_vision_emit = now
                self.vision_updated.emit(d['result'])
        elif kind == 'board':
            self.board_updated.emit(d['grid'], d['last_move'], d['move_no'])
        elif kind == 'ai':
            self.ai_move.emit(d['row'], d['col'], d['win_prob'], d['seconds'])
        elif kind == 'log':
            self.log.emit(d['msg'], d['level'])
        elif kind == 'game_over':
            self.game_over.emit(d['winner'], d['text'])
