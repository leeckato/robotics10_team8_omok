"""메인 창: 위젯 배치와 signal 연결만 담당 (로직은 workers / game 에)"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QMainWindow, QMessageBox, QSplitter, QVBoxLayout, QWidget)

from gui.dialogs.calibration_dialog import CalibrationDialog
from gui.dialogs.settings_dialog import SettingsDialog
from gui.widgets.board_view import BoardView
from gui.widgets.camera_view import CameraView
from gui.widgets.control_panel import ControlPanel
from gui.widgets.log_view import LogView
from gui.widgets.status_panel import StatusPanel
from gui.workers.camera_worker import CameraWorker
from gui.workers.game_worker import GameWorker
from utils.config import board_geometry

RUNNING_STATES = {'wait_empty', 'wait_human', 'ai_thinking', 'robot_moving', 'verify_robot'}


class MainWindow(QMainWindow):
    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.setWindowTitle('오목 로봇')
        self.resize(1280, 800)
        n, cell, margin = board_geometry(cfg)

        # ── 위젯 ──
        self.controls = ControlPanel(cfg['game']['human_first'])
        self.camera_view = CameraView(n, cell, margin)
        self.status = StatusPanel(cfg['vision']['stable_frames'])
        self.board_view = BoardView(n)
        self.log_view = LogView()

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(self.status)
        rl.addWidget(self.board_view, 1)

        top = QSplitter(Qt.Horizontal)
        top.addWidget(self.camera_view)
        top.addWidget(right)
        top.setStretchFactor(0, 3)
        top.setStretchFactor(1, 2)

        main = QSplitter(Qt.Vertical)
        main.addWidget(top)
        main.addWidget(self.log_view)
        main.setStretchFactor(0, 4)
        main.setStretchFactor(1, 1)

        central = QWidget()
        cl = QVBoxLayout(central)
        cl.addWidget(self.controls)
        cl.addWidget(main, 1)
        self.setCentralWidget(central)

        # ── 버튼 ──
        self.controls.start_clicked.connect(self._start)
        self.controls.stop_clicked.connect(lambda: self.game.stop_game())
        self.controls.confirm_clicked.connect(lambda: self.game.confirm_robot())
        self.controls.calibrate_clicked.connect(self._open_calibration)
        self.controls.settings_clicked.connect(self._open_settings)

        self._start_workers()

    # ───────── 워커 ─────────
    def _start_workers(self):
        self.camera = CameraWorker(self.cfg)
        self.camera.frame_ready.connect(self.camera_view.show_frame)
        self.camera.error.connect(lambda m: self._log(m, 'error'))
        self.camera.start()

        self.game = GameWorker(self.cfg, self._latest_frame)
        self.game.state_changed.connect(self._on_state)
        self.game.vision_updated.connect(self._on_vision)
        self.game.board_updated.connect(self._on_board)
        self.game.ai_move.connect(self._on_ai)
        self.game.log.connect(self._log)
        self.game.game_over.connect(self._on_game_over)
        self.game.mode_changed.connect(self.status.set_mode)
        self.game.start()

    def _stop_workers(self):
        self.game.stop()
        self.camera.stop()

    def _latest_frame(self):
        return self.camera.latest_frame()

    # ───────── 버튼 동작 ─────────
    def _start(self, human_first):
        self.board_view.clear()
        self.status.reset()
        self.game.start_game(human_first)

    def _open_calibration(self):
        dlg = CalibrationDialog(self.cfg, self._latest_frame, self)
        dlg.calibration_changed.connect(lambda: (self._log('캘리브레이션 변경 → 다시 불러옴'),
                                                 self.game.reload()))
        dlg.exec()

    def _open_settings(self):
        if SettingsDialog(self.cfg, self).exec():
            self._log('설정 저장 → 카메라/게임 재시작')
            self._stop_workers()
            self.status.stable_frames = self.cfg['vision']['stable_frames']
            self._start_workers()

    # ───────── 워커 signal 처리 ─────────
    def _on_state(self, value, text):
        self.status.set_state(text, value)
        self.controls.set_running(value in RUNNING_STATES)
        self.controls.set_confirm_enabled(value == 'verify_robot')

    def _on_vision(self, res):
        self.camera_view.show_result(res)
        self.status.set_vision(res)

    def _on_board(self, grid, last_move, move_no):
        self.board_view.set_board(grid, last_move)
        self.status.set_board(move_no, last_move)

    def _on_ai(self, r, c, p, sec):
        self.board_view.set_ai_target(r, c)
        self.status.set_ai(r, c, p, sec)

    def _on_game_over(self, winner, text):
        QMessageBox.information(self, '게임 종료', text)

    def _log(self, msg, level='info'):
        self.log_view.add(msg, level)

    def closeEvent(self, e):
        self._stop_workers()
        super().closeEvent(e)
