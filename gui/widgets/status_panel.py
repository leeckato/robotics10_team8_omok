"""현재 상태 표시: 진행 상태, 차례, 수, 손 감지, 안정화, AI 승률, 로봇 모드"""
from PySide6.QtWidgets import QFormLayout, QGroupBox, QLabel


class StatusPanel(QGroupBox):
    def __init__(self, stable_frames=10, parent=None):
        super().__init__('현재 상황', parent)
        self.stable_frames = stable_frames
        form = QFormLayout(self)
        self.lbl_state = QLabel('대기')
        self.lbl_state.setObjectName('stateLabel')
        self.lbl_move = QLabel('0')
        self.lbl_last = QLabel('-')
        self.lbl_hand = QLabel('-')
        self.lbl_stable = QLabel('-')
        self.lbl_ai = QLabel('-')
        self.lbl_mode = QLabel('-')
        form.addRow('상태', self.lbl_state)
        form.addRow('수', self.lbl_move)
        form.addRow('마지막 수', self.lbl_last)
        form.addRow('손 감지', self.lbl_hand)
        form.addRow('인식 안정화', self.lbl_stable)
        form.addRow('AI 판단', self.lbl_ai)
        form.addRow('로봇 모드', self.lbl_mode)

    def set_state(self, text, state_value=''):
        self.lbl_state.setText(text)
        color = {'wait_human': '#2e7d32', 'ai_thinking': '#1565c0', 'robot_moving': '#1565c0',
                 'verify_robot': '#6a1b9a', 'game_over': '#c62828', 'error': '#c62828'}
        self.lbl_state.setStyleSheet(f'color:{color.get(state_value, "#333")}; font-weight:bold;')

    def set_board(self, move_no, last_move):
        self.lbl_move.setText(str(move_no))
        self.lbl_last.setText('-' if last_move is None else f'({last_move[0]}, {last_move[1]})')

    def set_vision(self, res):
        self.lbl_hand.setText('있음 ✋' if res.hand else '없음')
        self.lbl_hand.setStyleSheet('color:#c62828;' if res.hand else '')
        k = min(res.stable_count, self.stable_frames)
        self.lbl_stable.setText(f'{k}/{self.stable_frames}' + (' ✔' if res.stable is not None else ''))

    def set_ai(self, row, col, win_prob, seconds):
        self.lbl_ai.setText(f'({row}, {col})  승률 {win_prob * 100:.0f}%  [{seconds:.1f}s]')

    def set_mode(self, mode):
        self.lbl_mode.setText(mode)

    def reset(self):
        self.lbl_move.setText('0')
        self.lbl_last.setText('-')
        self.lbl_ai.setText('-')
