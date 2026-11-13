import sys,time
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QComboBox,QCheckBox
from sensor_msgs.msg import Image
from std_srvs.srv import Trigger
from gomoku_interfaces.msg import GameState,BoardObservation,RobotStatus
from gomoku_interfaces.srv import StartGame,SetSimulation
from .common import state_qos
from .widgets import BoardWidget,CameraLabel

class Gui(QMainWindow):
    def __init__(self,node):
        super().__init__();self.node=node;self.sim=bool(node.declare_parameter('simulation',True).value);self.state=None;self.observed=[0]*64;self.obs_time=0;self.robot_time=0;self.robot=None
        self.setWindowTitle('오목 · ROS 2');self.resize(1140,820)
        root=QWidget();self.setCentralWidget(root);outer=QVBoxLayout(root);outer.setContentsMargins(24,20,24,20)
        header=QHBoxLayout();header.addWidget(QLabel('오목 / ROS 2'));header.addStretch();self.links=QLabel('노드 연결 대기');header.addWidget(self.links);outer.addLayout(header)
        content=QHBoxLayout();outer.addLayout(content,1);self.board=BoardWidget();content.addWidget(self.board,3)
        panel=QWidget();panel.setMaximumWidth(330);side=QVBoxLayout(panel);self.turn=QLabel('시작 대기');self.turn.setStyleSheet('font-size:24px;font-weight:bold');side.addWidget(self.turn)
        self.notice=QLabel('비전에서 빈 판을 확인한 뒤 시작하세요.');self.notice.setWordWrap(True);side.addWidget(self.notice);self.command_feedback=QLabel('');self.command_feedback.setWordWrap(True);side.addWidget(self.command_feedback)
        self.color=QComboBox();self.color.addItems(['사용자 선공 · 흑','사용자 후공 · 백']);side.addWidget(self.color)
        self.start_button=self.button('게임 시작',self.start,side);self.button('게임 종료',lambda:self.trigger('/game/end'),side)
        self.robot_info=QLabel('로봇: 연결 대기');self.robot_info.setWordWrap(True);side.addWidget(self.robot_info)  # team_robot
        robot_row=QHBoxLayout();self.button('로봇 대기 위치로',lambda:self.trigger('/robot/go_standby'),robot_row);self.button('로봇 오류 해제',lambda:self.trigger('/robot/clear_error'),robot_row);side.addLayout(robot_row)  # team_robot
        side.addStretch();self.camera=CameraLabel();self.camera.setMinimumSize(250,180);self.camera.setMaximumHeight(210);side.addWidget(self.camera)
        self.button('판 검사 요청 · 3초 대기',lambda:self.trigger('/game/inspect'),side);self.button('검사 취소',lambda:self.trigger('/game/cancel_inspect'),side)
        if self.sim:
            side.addWidget(QLabel('모의 실행 · 실제 로봇을 움직이지 않습니다.'))
            self.edit=QComboBox();self.edit.addItems(['흑돌 배치','백돌 배치','지우기']);side.addWidget(self.edit)
            self.off=QCheckBox('격자 밖 후보 시험');side.addWidget(self.off);self.off.toggled.connect(self.push_sim)
            self.board.clicked.connect(self.edit_sim)
        content.addWidget(panel,1)
        self.setStyleSheet('QMainWindow{background:#111923}QWidget{color:#e3eaf2;font-size:14px}QLabel{padding:6px}QPushButton{background:#284252;padding:10px;border-radius:6px;margin:3px}QPushButton:disabled{color:#82909c}QComboBox{background:#223646;padding:8px}')
        self.start_client=node.create_client(StartGame,'/game/start');self.triggers={n:node.create_client(Trigger,n) for n in ('/game/end','/game/inspect','/game/cancel_inspect','/robot/go_standby','/robot/clear_error')};self.sim_client=node.create_client(SetSimulation,'/vision/set_simulation')
        node.create_subscription(GameState,'/game/state',self.on_state,state_qos());node.create_subscription(BoardObservation,'/vision/observation',self.on_obs,10)
        node.create_subscription(RobotStatus,'/robot/status',self.on_robot,10);node.create_subscription(Image,'/vision/debug_image',self.on_image,qos_profile_sensor_data)
        self.last_state=0;self.timer=QTimer(self);self.timer.timeout.connect(self.spin);self.timer.start(20)
    def button(self,text,fn,layout):b=QPushButton(text);b.clicked.connect(fn);layout.addWidget(b);return b
    def spin(self):
        if not rclpy.ok():self.close();return
        for _ in range(5):rclpy.spin_once(self.node,timeout_sec=0)
        now=time.monotonic();v=now-self.obs_time<2;r=now-self.robot_time<2 and self.robot and self.robot.connected
        self.links.setText(('모의 | ' if self.sim else '')+f'비전 {"●" if v else "○"}  로봇 {"●" if r else "○"}')
        self.robot_info.setText(self.robot_text(r))  # team_robot
        if self.last_state and now-self.last_state>2:self.notice.setText('게임 제어 연결이 끊겼습니다.');self.start_button.setEnabled(False)
    def on_state(self,msg):
        self.state=msg;self.last_state=time.monotonic();self.board.board=list(msg.board);self.board.last=(msg.last_row,msg.last_col) if msg.last_row>=0 else None;self.board.update()
        label={'READY':'시작 대기','HUMAN':'사용자 차례','COUNTDOWN':'착수 확인 대기','INSPECT_HUMAN':'착수 확인 중','WAIT_AI':'로봇 차례','AI':'다음 수 계산 중','WAIT_ROBOT':'로봇 연결 대기','SENDING_ROBOT':'로봇 요청 중','ROBOT':'로봇 동작 중','WAIT_VERIFY':'로봇 착수 확인','INSPECT_ROBOT':'로봇 착수 확인','ERROR':'확인 필요','FINISHED':'게임 종료'}.get(msg.phase,msg.phase)
        if msg.winner:label='무승부' if msg.winner==3 else '사용자 승리' if msg.winner==msg.human_color else '로봇 승리'
        self.turn.setText(label);self.notice.setText(msg.notice);idle=msg.phase in ('READY','FINISHED');self.color.setEnabled(idle);self.start_button.setEnabled(idle)
    def on_obs(self,msg):self.observed=list(msg.board);self.obs_time=time.monotonic()
    def on_robot(self,msg):self.robot=msg;self.robot_time=time.monotonic()
    def robot_text(self,alive):  # team_robot: /robot/status 요약
        if not alive:return '로봇: 미연결 (두산 bringup · team_robot 확인)'
        s=self.robot
        if s.error:return '로봇 오류: '+s.error
        return '로봇: '+('동작 중' if s.busy else '대기 위치' if s.at_standby else '대기 위치 아님 → [로봇 대기 위치로]')+f' · 좌표 rev {s.board_revision}'
    def on_image(self,msg):
        try:
            import numpy as np
            if msg.encoding!='bgr8' or msg.step<msg.width*3:return
            frame=np.frombuffer(bytes(msg.data),np.uint8).reshape(msg.height,msg.step)[:,:msg.width*3].reshape(msg.height,msg.width,3)
            self.camera.set_frame(frame)
        except (ValueError,ImportError):pass
    def reply(self,f,accepted_field):
        try:
            res=f.result()
            self.command_feedback.setText(res.message or ('요청 수락' if getattr(res,accepted_field) else '요청 거절'))
        except Exception as e:self.command_feedback.setText('요청 실패: '+str(e))
    def start(self):
        if not self.start_client.service_is_ready():self.notice.setText('게임 제어 미연결');return
        req=StartGame.Request();req.human_color=self.color.currentIndex()+1;self.start_client.call_async(req).add_done_callback(lambda f:self.reply(f,'accepted'))
    def trigger(self,name):
        client=self.triggers[name]
        if not client.service_is_ready():self.notice.setText('서비스 미연결');return
        client.call_async(Trigger.Request()).add_done_callback(lambda f:self.reply(f,'success'))
    def edit_sim(self,r,c):
        if self.state and self.state.phase not in ('READY','HUMAN','FINISHED'):self.notice.setText('현재 차례에는 편집할 수 없습니다.');return
        board=self.observed.copy()
        if any(v not in (0,1,2) for v in board):return
        board[r*8+c]=[1,2,0][self.edit.currentIndex()];self.push_sim(board=board)
    def push_sim(self,checked=False,board=None):
        if not self.sim_client.service_is_ready():self.notice.setText('모의 비전 미연결');return
        req=SetSimulation.Request();req.board=self.observed if board is None else board;req.off_grid_count=int(self.off.isChecked());self.sim_client.call_async(req).add_done_callback(lambda f:self.reply(f,'accepted'))

def main(args=None):
    rclpy.init(args=args);app=QApplication(sys.argv[:1]);node=Node('gomoku_gui');window=Gui(node);window.show()
    try:app.exec()
    finally:
        node.destroy_node()
        if rclpy.ok():rclpy.shutdown()
