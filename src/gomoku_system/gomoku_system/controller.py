import time,uuid
import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from action_msgs.msg import GoalStatus
from std_srvs.srv import Trigger
from gomoku_interfaces.msg import BoardObservation,GameState,HandState,RobotStatus
from gomoku_interfaces.srv import StartGame,Inspect,NextMove
from gomoku_interfaces.action import PlaceStone
from .game import Game,InvalidMove
from .common import state_qos

class Controller(Node):
    def __init__(self):
        super().__init__('gomoku_controller');self.sim=False
        self.use_hand=bool(self.declare_parameter('use_hand',False).value)
        self.g=Game();self.phase='READY';self.game_id='';self.turn_id=0;self.notice='시작 대기';self.obs=None;self.obs_at=0;self.robot=None;self.robot_at=0
        self.hand=None;self.hand_at=0;self.hand_seen=False;self.clear_since=None;self.rid='';self.wait_since=0;self.expected=None;self.epoch=0;self.goal_handle=None;self.bound_revision=None;self.motion_uncertain=False;self.fix_signature=None;self.fix_since=None
        self.pub=self.create_publisher(GameState,'/game/state',state_qos())
        self.create_subscription(BoardObservation,'/vision/observation',self.observe,10)
        self.create_subscription(HandState,'/vision/hand_state',self.hand_event,10)
        self.create_subscription(RobotStatus,'/robot/status',self.robot_event,10)
        self.create_service(StartGame,'/game/start',self.start)
        self.create_service(Trigger,'/game/end',self.end)
        self.create_service(Trigger,'/game/inspect',self.manual)
        self.create_service(Trigger,'/game/cancel_inspect',self.cancel_inspect)
        self.inspect_client=self.create_client(Inspect,'/vision/inspect');self.ai=self.create_client(NextMove,'/algorithm/next_move');self.arm=ActionClient(self,PlaceStone,'/robot/place_stone')
        self.create_timer(.1,self.tick)
    def set(self,phase,notice):self.phase=phase;self.notice=notice;self.wait_since=time.monotonic()
    def wait_for_correction(self,robot,notice):
        self.rid='';self.hand_seen=False;self.clear_since=None
        self.fix_signature=None;self.fix_since=None
        self.set('FIX_ROBOT' if robot else 'FIX_HUMAN',notice+'\n판을 바로잡고 손을 빼면 3초 후 자동 재검사합니다.')
    def retry_corrected_board(self,now):
        robot=self.phase=='FIX_ROBOT'
        if not self.valid_obs() or not self.hand_clear():
            self.fix_signature=None;self.fix_since=None;return
        if self.obs.board_revision!=self.bound_revision:
            self.set('ERROR','보드 좌표가 변경되었습니다. 로봇 좌표 보정 후 새 게임을 시작하세요.');return
        if self.motion_uncertain or self.goal_handle is not None or (robot and not self.robot_ready()) or (self.robot and time.monotonic()-self.robot_at<2 and self.robot.busy):
            self.fix_signature=None;self.fix_since=None;return
        restored=not robot and not self.obs.off_grid_count and list(self.obs.board)==self.g.board
        try:
            if not restored:
                idx=self.g.validate(list(self.obs.board),self.obs.off_grid_count,True)
                if robot and divmod(idx,8)!=self.expected:raise InvalidMove('로봇 요청 위치와 관측 위치가 다릅니다.')
        except InvalidMove:
            self.fix_signature=None;self.fix_since=None;return
        signature=(tuple(self.obs.board),self.obs.off_grid_count,self.obs.board_revision)
        if signature!=self.fix_signature:
            self.fix_signature=signature;self.fix_since=now;return
        if self.fix_since is None or now-self.fix_since<3:return
        self.fix_signature=None;self.fix_since=None
        if restored:
            self.hand_seen=False;self.clear_since=None
            self.set('HUMAN','판 복원 확인. 사용자 차례입니다. 돌 한 개를 놓으세요.')
        else:self.request_inspect(robot=robot)
    def valid_obs(self):return bool(self.obs and time.monotonic()-self.obs_at<1 and self.obs.tracking_valid and self.obs.state_valid and all(v in (0,1,2) for v in self.obs.board))
    def hand_clear(self):return bool(not self.use_hand or (self.hand and self.hand.valid and not self.hand.hand_present and time.monotonic()-self.hand_at<.5))
    def fresh_stamp(self,stamp,max_age):
        age=(self.get_clock().now().nanoseconds-(stamp.sec*1000000000+stamp.nanosec))/1e9
        return -.2<=age<=max_age
    def robot_event(self,msg):
        if not self.fresh_stamp(msg.stamp,1):return
        self.robot=msg;self.robot_at=time.monotonic()
    def hand_event(self,msg):
        if not self.fresh_stamp(msg.stamp,.5):return
        self.hand=msg;self.hand_at=time.monotonic()
        if self.phase not in ('HUMAN','COUNTDOWN','INSPECT_HUMAN'):return
        if not msg.valid or msg.hand_present:
            if msg.valid and msg.hand_present:self.hand_seen=True
            self.clear_since=None
            if self.phase in ('COUNTDOWN','INSPECT_HUMAN'):self.rid='';self.set('HUMAN','손 감지: 검사 대기 초기화')
        elif self.hand_seen and self.clear_since is None:self.clear_since=time.monotonic()
    def start(self,req,res):
        if self.phase not in ('READY','FINISHED'):res.message='진행 중인 게임을 먼저 종료하세요.';return res
        if req.human_color not in (1,2):res.message='human_color must be 1 or 2';return res
        if not self.valid_obs() or self.obs.off_grid_count:res.message='유효한 빈 판 관측 필요';return res
        if self.use_hand and not self.hand_clear():res.message='유효한 손 없음 상태 필요';return res
        try:self.g=Game();self.g.start(req.human_color,list(self.obs.board))
        except InvalidMove as e:res.message=str(e);return res
        self.epoch+=1;self.game_id=uuid.uuid4().hex;self.turn_id=0;self.expected=None;self.rid='';self.bound_revision=self.obs.board_revision;self.hand_seen=False;self.clear_since=None
        self.set('HUMAN' if self.g.turn==self.g.human else 'WAIT_AI','사용자 차례' if self.g.turn==self.g.human else '알고리즘 연결 대기')
        res.accepted=True;res.message='게임 시작';return res
    def end(self,req,res):
        if self.motion_uncertain or self.goal_handle is not None or self.phase in ('ROBOT','SENDING_ROBOT') or (self.robot and (self.robot.busy or (not self.sim and not self.robot.at_standby))):res.message='로봇 동작 또는 복귀 여부 확인 필요';return res
        self.epoch+=1;self.rid='';self.g=Game();self.expected=None;self.set('READY','게임 종료. 판을 비우고 시작하세요.');res.success=True;return res
    def manual(self,req,res):
        if self.phase not in ('HUMAN','FIX_HUMAN'):res.message='사용자 차례에서만 검사 가능';return res
        if self.use_hand and not self.hand_clear():res.message='손 감지 유효/손 없음 확인 필요';return res
        self.set('COUNTDOWN','손을 빼세요. 3초 후 검사합니다.');res.success=True;return res
    def cancel_inspect(self,req,res):
        if self.phase not in ('COUNTDOWN','INSPECT_HUMAN'):res.message='취소할 사용자 검사 없음';return res
        self.rid='';self.clear_since=None;self.hand_seen=False;self.set('HUMAN','검사 취소');res.success=True;return res
    def request_inspect(self,robot=False):
        if not self.inspect_client.service_is_ready():self.wait_for_correction(robot,'비전 검사 서비스 미연결');return
        self.rid=uuid.uuid4().hex;req=Inspect.Request();req.request_id=self.rid;token=self.epoch;rid=self.rid
        self.set('INSPECT_ROBOT' if robot else 'INSPECT_HUMAN','착수 결과 확인 중')
        future=self.inspect_client.call_async(req)
        def done(f):
            if token!=self.epoch or rid!=self.rid:return
            try:
                if not f.result().accepted:raise RuntimeError(f.result().message)
            except Exception as e:self.wait_for_correction(robot,'검사 요청 실패: '+str(e))
        future.add_done_callback(done)
    def observe(self,msg):
        if not self.fresh_stamp(msg.stamp,1):return
        self.obs=msg;self.obs_at=time.monotonic()
        if self.phase not in ('INSPECT_HUMAN','INSPECT_ROBOT') or not self.rid or msg.request_id!=self.rid:return
        if not self.valid_obs():return
        robot=self.phase=='INSPECT_ROBOT'
        if self.bound_revision!=msg.board_revision:
            self.rid='';self.set('ERROR','보드 좌표가 변경되었습니다. 로봇 좌표 보정 후 새 게임을 시작하세요.');return
        if not self.hand_clear():return
        if not self.sim:
            # User moves may be validated before robot preparation. Actual motion
            # still requires robot_ready() in WAIT_ROBOT.
            robot_fresh = self.robot is not None and time.monotonic()-self.robot_at <= 2
            if robot and (not robot_fresh or not self.robot.connected or self.robot.busy or not self.robot.at_standby):return
            if not robot and robot_fresh and self.robot.busy:return
        try:
            idx=self.g.validate(list(msg.board),msg.off_grid_count,True)
            if robot and divmod(idx,8)!=self.expected:raise InvalidMove('로봇 요청 위치와 관측 위치가 다릅니다.')
            self.g.accept(list(msg.board),msg.off_grid_count,True)
        except InvalidMove as e:
            self.wait_for_correction(robot,str(e));return
        self.rid='';self.expected=None;self.turn_id+=1;self.hand_seen=False;self.clear_since=None
        if self.g.result:self.set('FINISHED','무승부' if self.g.result==3 else '사용자 승리' if self.g.result==self.g.human else '로봇 승리')
        else:self.set('HUMAN' if self.g.turn==self.g.human else 'WAIT_AI','사용자 차례' if self.g.turn==self.g.human else '알고리즘 응답 대기')
    def ask_ai(self):
        req=NextMove.Request();req.game_id=self.game_id;req.turn_id=self.turn_id;req.request_id=uuid.uuid4().hex;req.board=self.g.board;req.to_play=self.g.turn
        token=self.epoch;self.set('AI','다음 착수 계산 중');future=self.ai.call_async(req)
        def done(f):
            if token!=self.epoch or self.phase!='AI':return
            try:
                r=f.result()
                if (r.game_id,r.turn_id,r.request_id)!=(req.game_id,req.turn_id,req.request_id) or not r.success:raise RuntimeError(r.error or '응답 식별자 불일치')
                if not (0<=r.row<8 and 0<=r.col<8) or self.g.board[r.row*8+r.col]:raise RuntimeError('알고리즘 착수 좌표 오류')
                self.expected=(r.row,r.col);self.set('WAIT_ROBOT','로봇 연결·대기 위치 확인 중')
            except Exception as e:self.set('ERROR','알고리즘 오류: '+str(e))
        future.add_done_callback(done)
    def robot_ready(self):
        return bool(self.robot and time.monotonic()-self.robot_at<2 and self.robot.connected and not self.robot.busy and self.robot.at_standby and not self.robot.error and self.robot.board_revision==self.bound_revision)
    def send_robot(self):
        goal=PlaceStone.Goal();goal.game_id=self.game_id;goal.turn_id=self.turn_id;goal.request_id=uuid.uuid4().hex;goal.row,goal.col=self.expected;goal.color=self.g.turn;goal.board_revision=self.bound_revision
        self.motion_uncertain=True
        token=self.epoch;self.set('SENDING_ROBOT','로봇 요청 전송 중. 바둑판에서 떨어져 주세요.')
        future=self.arm.send_goal_async(goal)
        def accepted(f):
            if token!=self.epoch or self.phase!='SENDING_ROBOT':return
            try:
                handle=f.result()
                if not handle.accepted:
                    self.motion_uncertain=False;raise RuntimeError('로봇 요청 거절')
                self.goal_handle=handle;self.set('ROBOT','로봇 동작 중. 바둑판에서 떨어져 주세요.')
                handle.get_result_async().add_done_callback(completed)
            except Exception as e:self.set('ERROR',str(e))
        def completed(f):
            if token!=self.epoch or self.phase!='ROBOT':return
            try:
                wrapped=f.result();result=wrapped.result
                if wrapped.status!=GoalStatus.STATUS_SUCCEEDED or not result.success or not result.returned_to_standby or result.request_id!=goal.request_id:raise RuntimeError(result.error or '착수/복귀 확인 실패')
                self.goal_handle=None;self.motion_uncertain=False;self.set('WAIT_VERIFY','로봇 복귀 후 판 확인 대기')
            except Exception as e:self.set('ERROR','로봇 결과 오류: '+str(e))
        future.add_done_callback(accepted)
    def tick(self):
        now=time.monotonic()
        if self.phase in ('FIX_HUMAN','FIX_ROBOT'):self.retry_corrected_board(now)
        if self.phase in ('HUMAN','COUNTDOWN','INSPECT_HUMAN') and self.use_hand:
            if not self.hand or now-self.hand_at>.5 or not self.hand.valid:
                self.clear_since=None
                if self.phase!='HUMAN':self.rid='';self.set('HUMAN','손 감지 신호 무효: 검사 보류')
            elif self.phase=='HUMAN' and self.hand_seen and self.clear_since and now-self.clear_since>=3:self.request_inspect()
        if self.phase=='COUNTDOWN' and now-self.wait_since>=3:self.request_inspect()
        if self.phase=='WAIT_AI' and self.ai.service_is_ready():self.ask_ai()
        if self.phase=='WAIT_ROBOT' and self.robot_ready() and self.arm.server_is_ready() and self.hand_clear() and self.valid_obs() and self.obs.board_revision==self.bound_revision:self.send_robot()
        if self.phase=='WAIT_VERIFY' and self.robot_ready() and self.hand_clear():self.request_inspect(robot=True)
        if self.phase in ('INSPECT_HUMAN','INSPECT_ROBOT') and now-self.wait_since>8:
            robot=self.phase=='INSPECT_ROBOT';self.wait_for_correction(robot,'판 검사 시간 초과: 추적·손·로봇 상태 확인')
        if self.phase=='WAIT_VERIFY' and now-self.wait_since>15:self.wait_for_correction(True,'로봇 복귀 후 판 확인 대기 중')
        if self.phase in ('AI','SENDING_ROBOT','ROBOT','WAIT_VERIFY') and now-self.wait_since>(120 if self.phase=='ROBOT' else 15):self.set('ERROR','연결/작업 시간 초과. 실제 동작 상태를 확인하세요. 자동 재시도하지 않습니다.')
        msg=GameState();msg.stamp=self.get_clock().now().to_msg();msg.game_id=self.game_id;msg.turn_id=self.turn_id;msg.phase=self.phase;msg.board=self.g.board;msg.human_color=self.g.human;msg.to_play=self.g.turn;msg.winner=self.g.result;msg.last_row,msg.last_col=self.g.last if self.g.last else (-1,-1);msg.simulation=self.sim;msg.notice=self.notice;self.pub.publish(msg)

def main(args=None):
    rclpy.init(args=args);node=Controller()
    try:rclpy.spin(node)
    except KeyboardInterrupt:pass
    finally:
        node.destroy_node()
        if rclpy.ok():rclpy.shutdown()
