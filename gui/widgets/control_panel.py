"""게임 시작/중지, 선공 선택, 캘리브레이션/설정, 수동 확인 버튼"""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QButtonGroup, QHBoxLayout, QLabel, QPushButton,
                               QRadioButton, QWidget)


class ControlPanel(QWidget):
    start_clicked = Signal(bool)       # human_first
    stop_clicked = Signal()
    confirm_clicked = Signal()
    calibrate_clicked = Signal()
    settings_clicked = Signal()

    def __init__(self, human_first=True, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        self.btn_start = QPushButton('▶ 게임 시작')
        self.btn_start.setObjectName('startButton')
        self.btn_stop = QPushButton('■ 중지')
        self.btn_confirm = QPushButton('수동 확인')
        self.btn_confirm.setToolTip('로봇이 놓은 돌이 인식되지 않을 때 강제로 다음 차례로 진행')

        self.rb_human = QRadioButton('사람')
        self.rb_robot = QRadioButton('로봇')
        (self.rb_human if human_first else self.rb_robot).setChecked(True)
        grp = QButtonGroup(self)
        grp.addButton(self.rb_human)
        grp.addButton(self.rb_robot)

        self.btn_calib = QPushButton('캘리브레이션')
        self.btn_settings = QPushButton('설정')

        for w in (self.btn_start, self.btn_stop, self.btn_confirm):
            lay.addWidget(w)
        lay.addSpacing(16)
        lay.addWidget(QLabel('선공(흑):'))
        lay.addWidget(self.rb_human)
        lay.addWidget(self.rb_robot)
        lay.addStretch(1)
        lay.addWidget(self.btn_calib)
        lay.addWidget(self.btn_settings)

        self.btn_start.clicked.connect(lambda: self.start_clicked.emit(self.rb_human.isChecked()))
        self.btn_stop.clicked.connect(self.stop_clicked)
        self.btn_confirm.clicked.connect(self.confirm_clicked)
        self.btn_calib.clicked.connect(self.calibrate_clicked)
        self.btn_settings.clicked.connect(self.settings_clicked)
        self.set_running(False)

    def set_running(self, running):
        self.btn_start.setEnabled(not running)
        self.btn_stop.setEnabled(running)
        self.rb_human.setEnabled(not running)
        self.rb_robot.setEnabled(not running)
        self.btn_calib.setEnabled(not running)
        self.btn_settings.setEnabled(not running)
        if not running:
            self.btn_confirm.setEnabled(False)

    def set_confirm_enabled(self, on):
        self.btn_confirm.setEnabled(on)
