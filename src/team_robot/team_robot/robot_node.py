"""
로봇 노드 (팀원 연결 규격 v0.1 '2. 로봇 담당')

  Action  /robot/place_stone  gomoku_interfaces/action/PlaceStone
          공급 위치에서 돌 집기 -> (row,col) 에 놓기 -> 공급 위치 위(대기 위치) 복귀 -> TCP 실측으로 복귀 확인 후 성공
          feedback stage: PICKING / MOVING / PLACING / RETURNING
  Topic   /robot/status       gomoku_interfaces/msg/RobotStatus 10Hz
          connected  = 두산 드라이버 TCP 조회가 2초 안에 성공
          at_standby = 실측 TCP 가 대기 위치에서 pos_tol(3mm) 이내
          board_revision = 파라미터 (로봇 담당이 격자 좌표를 확인한 비전 revision. 비전 값을 복사하지 않음)
  Service /robot/go_standby   std_srvs/Trigger  (필요하면 수직 상승) -> 준비 자세 -> 공급 위치 위
          /robot/clear_error  std_srvs/Trigger  실제 상태 확인 후 오류 해제

  auto_standby:=true 면 로봇 차례(WAIT_ROBOT)에 대기 위치가 아닐 때 자동으로 이동 (사람 차례에는 움직이지 않음,
  손 노드가 있으면 손 없음일 때만)

모드 (robot_mode)
  real : 두산 드라이버 서비스로 실제 이동 (/<ns>/motion/move_line, move_joint, aux_control/get_current_posx)
  dry  : 로봇을 움직이지 않음. 계획만 로그로 출력하고, PLACING 에서 dry_place_wait_sec 동안 기다림
         -> 그동안 사람이 로봇 대신 그 칸에 돌을 놓으면 비전 확인까지 전체 흐름 시험 가능

그리퍼 (gripper_mode)
  drl   : omok_pick_place.py --gripper real 과 같음. python3 gripper_drl.py open|close <값>
  topic : go8_grip.py / z_grip_z.py 와 같음. std_msgs/Int32 를 /dsr01/gripper/position_cmd 로 발행 (gripper_node mode:=real)
  sim   : /<ns>/gripper/open|close 서비스 (Trigger/Empty/SetBool)
  none  : 그리퍼 동작 없음
"""
import math
import os
import subprocess
import sys
import threading
import time

import rclpy
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import ExternalShutdownException, MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import Int32, String
from std_srvs.srv import Trigger
from gomoku_interfaces.action import PlaceStone
from gomoku_interfaces.msg import GameState, HandState, RobotStatus

from team_robot.motion import DEFAULTS, Planner, load_grid

GRIP_DEFAULTS = dict(gripper_mode='drl', gripper_drl='~/ros2_ws/gripper/gripper_drl.py',
                     gripper_topic='/dsr01/gripper/position_cmd',
                     grip_close=630, grip_open=550, grip_wait_pos=450, grip_wait_sec=-1.0)


class MotionError(RuntimeError):
    pass


def state_qos():
    return QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL, reliability=ReliabilityPolicy.RELIABLE)


class RobotNode(Node):
    def __init__(self):
        super().__init__('team_robot')
        self.group = ReentrantCallbackGroup()
        d = lambda name, default: self.declare_parameter(name, default).value   # noqa: E731
        self.mode = str(d('robot_mode', 'dry'))
        if self.mode not in ('real', 'dry'):
            raise ValueError(f'robot_mode 는 real 또는 dry: {self.mode}')
        self.ns = str(d('ns', 'dsr01')).strip('/')
        self.p = {k: d(k, v) for k, v in DEFAULTS.items()}
        self.p['rotation'] = [float(v) for v in self.p['rotation']]
        self.p['home_joint'] = [float(v) for v in self.p['home_joint']]
        self.g = {k: d(k, v) for k, v in GRIP_DEFAULTS.items()}
        self.pos_tol = float(d('pos_tol', 3.0))
        self.declare_parameter('board_revision', 1)      # ros2 param set /team_robot board_revision N (좌표 재확인 후)
        self.auto_standby = bool(d('auto_standby', True))
        self.call_timeout = float(d('call_timeout_sec', 60.0))
        self.dry_step = float(d('dry_step_sec', 0.3))
        self.dry_place_wait = float(d('dry_place_wait_sec', 10.0))
        self.rviz = bool(d('rviz_place_cmd', True))

        self.planner = Planner(load_grid(self.p['grid_json']), self.p)
        self.standby_xyz = self.planner.standby()

        self.lock = threading.Lock()
        self.busy = False
        self.error = ''
        self.ids = set()
        self.tcp = None                   # 마지막 실측 TCP [x,y,z,a,b,c]
        self.tcp_at = 0.0
        self._poll_pending = False
        self.board = [0] * 64             # 게임 제어가 알고 있는 판 (/game/state)
        self._seen_game = None

        if self.mode == 'real':
            from dsr_msgs2.srv import GetCurrentPosx, MoveJoint, MoveLine
            self.MoveLine, self.MoveJoint, self.GetCurrentPosx = MoveLine, MoveJoint, GetCurrentPosx
            self.cli_line = self.create_client(MoveLine, f'/{self.ns}/motion/move_line', callback_group=self.group)
            self.cli_joint = self.create_client(MoveJoint, f'/{self.ns}/motion/move_joint', callback_group=self.group)
            self.cli_pos = self.create_client(GetCurrentPosx, f'/{self.ns}/aux_control/get_current_posx',
                                              callback_group=self.group)
            self.create_timer(0.5, self.poll_tcp, callback_group=self.group)
            if self.g['gripper_mode'] == 'topic':
                self.grip_pub = self.create_publisher(Int32, self.g['gripper_topic'], 10)

        self.status_pub = self.create_publisher(RobotStatus, '/robot/status', 10)
        self.place_pub = self.create_publisher(String, '/omok/place_cmd', 10) if self.rviz else None
        self.create_timer(0.1, self.publish_status, callback_group=self.group)
        self.create_subscription(GameState, '/game/state', self.on_game, state_qos(), callback_group=self.group)
        self._hand = None
        self.create_subscription(HandState, '/vision/hand_state', self.on_hand, 10, callback_group=self.group)
        self.create_service(Trigger, '/robot/go_standby', self.srv_go_standby, callback_group=self.group)
        self.create_service(Trigger, '/robot/clear_error', self.srv_clear_error, callback_group=self.group)
        self.server = ActionServer(self, PlaceStone, '/robot/place_stone', execute_callback=self.execute,
                                   goal_callback=self.on_goal, cancel_callback=lambda _: CancelResponse.REJECT,
                                   callback_group=self.group)

        log = self.get_logger()
        log.info(f'[team_robot] 모드={self.mode}, 그리퍼={self.g["gripper_mode"]}, 좌표={self.p["grid_json"]}')
        log.info(f'[team_robot] 대기 위치(공급 위) = ({self.standby_xyz[0]:.1f}, {self.standby_xyz[1]:.1f}, '
                 f'{self.standby_xyz[2]:.1f}), 자세 {self.p["rotation"]}, board_revision={self.revision()}')
        if self.mode == 'dry':
            log.warn('[team_robot] DRY 모드: 로봇을 움직이지 않습니다. 로봇 차례에 안내된 칸에 사람이 돌을 놓아 시험하세요.')

    # ───────────── 상태 ─────────────
    def revision(self):
        return int(self.get_parameter('board_revision').value)

    def connected(self):
        if self.mode == 'dry':
            return True
        # 대기 중에는 0.5초마다 조회하므로 2초, 동작 중(그리퍼 대기 등)에는 동작 스레드가 단계마다 조회
        limit = self.call_timeout + 10.0 if self.busy else 2.0
        return self.tcp is not None and time.monotonic() - self.tcp_at < limit

    def at_standby(self):
        if self.tcp is None or not self.connected():
            return False
        return math.dist(self.tcp[:3], self.standby_xyz) <= self.pos_tol

    def publish_status(self):
        s = RobotStatus()
        s.stamp = self.get_clock().now().to_msg()
        s.connected = self.connected()
        s.busy = self.busy
        s.at_standby = self.at_standby() and not self.busy
        s.board_revision = self.revision()
        s.error = self.error
        self.status_pub.publish(s)

    def poll_tcp(self):
        """대기 중에도 실측 TCP 갱신 (동작 중에는 동작 스레드가 갱신)"""
        if self.busy or self._poll_pending or not self.cli_pos.service_is_ready():
            return
        self._poll_pending = True
        req = self.GetCurrentPosx.Request()
        req.ref = 0
        fut = self.cli_pos.call_async(req)

        def done(f):
            self._poll_pending = False
            try:
                r = f.result()
                if r is not None and r.success and r.task_pos_info:
                    self.tcp, self.tcp_at = list(r.task_pos_info[0].data[:6]), time.monotonic()
            except Exception:
                pass
        fut.add_done_callback(done)

    def on_hand(self, msg):
        self._hand = (msg.valid, msg.hand_present, time.monotonic())

    def hand_ok(self):
        """손 노드가 없으면 True. 있으면 0.5초 안의 정상 검사에서 손 없음일 때만 True"""
        if self._hand is None:
            return True
        valid, present, at = self._hand
        return valid and not present and time.monotonic() - at < 0.5

    def on_game(self, msg):
        """로봇 차례(WAIT_ROBOT)인데 대기 위치가 아니면 대기 위치로 이동.
        사람 차례에는 움직이지 않음 (게임 시작 직후 사람이 판에 손을 뻗는 중일 수 있음)"""
        self.board = [int(v) for v in msg.board]
        if not self.auto_standby or msg.phase != 'WAIT_ROBOT' or self.busy or self.at_standby():
            return
        key = (msg.game_id, msg.turn_id)
        why = '' if self.hand_ok() else '판 위에 손 감지 (또는 손 감지 무효)'
        if not why:
            ok, why = self.start_standby(f'로봇 차례 turn {msg.turn_id}')
            if ok:
                return
        if key != self._seen_game:                  # 같은 차례에서 같은 경고 반복 안 함
            self._seen_game = key
            self.get_logger().warn(f'[team_robot] 로봇 차례지만 대기 위치 이동 보류: {why}')

    # ───────────── 두산 서비스 호출 ─────────────
    def call(self, client, req, timeout=None):
        if not client.wait_for_service(timeout_sec=3.0):
            raise MotionError(f'서비스 없음: {client.srv_name} (두산 bringup 확인)')
        ev = threading.Event()
        fut = client.call_async(req)
        fut.add_done_callback(lambda _: ev.set())
        if not ev.wait(timeout or self.call_timeout):
            raise MotionError(f'응답 시간 초과: {client.srv_name} (실제 로봇 상태 확인)')
        res = fut.result()
        if res is None or not getattr(res, 'success', True):
            raise MotionError(f'로봇 명령 실패: {client.srv_name}')
        return res

    def read_tcp(self):
        if self.mode == 'dry':
            return self.tcp
        req = self.GetCurrentPosx.Request()
        req.ref = 0
        res = self.call(self.cli_pos, req, timeout=5.0)
        self.tcp, self.tcp_at = list(res.task_pos_info[0].data[:6]), time.monotonic()
        return self.tcp

    def move_line(self, xyz, name=''):
        target = [float(v) for v in xyz] + self.p['rotation']
        if self.mode == 'dry':
            time.sleep(self.dry_step)
            self.tcp, self.tcp_at = target, time.monotonic()
            return
        req = self.MoveLine.Request()
        req.pos = target
        req.vel = [float(self.p['vel']), float(self.p['vel_rot'])]
        req.acc = [float(self.p['acc']), float(self.p['acc_rot'])]
        req.time = 0.0
        req.radius = 0.0
        req.ref = 0            # BASE
        req.mode = 0           # 절대 좌표
        req.blend_type = 0
        req.sync_type = 0      # 이동 끝날 때까지 대기
        self.call(self.cli_line, req)
        actual = self.read_tcp()
        err = math.dist(actual[:3], target[:3])
        if err > self.pos_tol:
            raise MotionError(f'{name} 위치 오차 {err:.1f}mm (> {self.pos_tol}mm). 현재 '
                              f'({actual[0]:.1f}, {actual[1]:.1f}, {actual[2]:.1f})')

    def move_home(self):
        if self.mode == 'dry':
            time.sleep(self.dry_step)
            return
        req = self.MoveJoint.Request()
        req.pos = self.p['home_joint']
        req.vel = float(self.p['joint_vel'])
        req.acc = float(self.p['joint_acc'])
        req.time = 0.0
        req.radius = 0.0
        req.mode = 0
        req.blend_type = 0
        req.sync_type = 0
        self.call(self.cli_joint, req, timeout=120.0)
        self.read_tcp()

    def gripper(self, action):
        """action: close(잡기) / open(놓기) / wait(복귀 후 대기 값)"""
        g, mode = self.g, self.g['gripper_mode']
        if self.mode == 'dry' or mode == 'none':
            return
        value = int({'close': g['grip_close'], 'open': g['grip_open'], 'wait': g['grip_wait_pos']}[action])
        wait = float(g['grip_wait_sec'])
        if mode == 'drl':
            path = os.path.expanduser(g['gripper_drl'])
            if not os.path.isfile(path):
                raise MotionError(f'그리퍼 스크립트 없음: {path}')
            cmd = 'close' if action == 'close' else 'open'          # omok_pick_place.py 와 같은 인자
            try:
                r = subprocess.run([sys.executable, path, cmd, str(value)], timeout=30)
            except subprocess.TimeoutExpired:
                raise MotionError('gripper_drl.py 시간 초과')
            if r.returncode != 0:
                raise MotionError(f'gripper_drl.py 실패 (종료 코드 {r.returncode})')
            time.sleep(1.0 if wait < 0 else wait)
        elif mode == 'topic':
            if self.grip_pub.get_subscription_count() == 0:
                raise MotionError(f'그리퍼 노드가 안 보입니다 ({g["gripper_topic"]} 구독자 없음, gripper_node mode:=real 확인)')
            self.grip_pub.publish(Int32(data=value))
            time.sleep(2.5 if wait < 0 else wait)
        elif mode == 'sim':
            self._sim_gripper('close' if action == 'close' else 'open')
            time.sleep(1.0 if wait < 0 else wait)
        else:
            raise MotionError(f'gripper_mode 오류: {mode}')
        self.get_logger().info(f'[team_robot]   그리퍼 {action} = {value}')

    def _sim_gripper(self, action):
        srv = f'/{self.ns}/gripper/{action}'
        types = dict(self.get_service_names_and_types())
        if srv not in types:
            raise MotionError(f'그리퍼 서비스 없음: {srv}')
        t = types[srv][0]
        if t == 'std_srvs/srv/Trigger':
            from std_srvs.srv import Trigger as C
        elif t == 'std_srvs/srv/Empty':
            from std_srvs.srv import Empty as C
        elif t == 'std_srvs/srv/SetBool':
            from std_srvs.srv import SetBool as C
        else:
            raise MotionError(f'지원하지 않는 그리퍼 서비스 타입: {t}')
        req = C.Request()
        if hasattr(req, 'data'):
            req.data = True
        cli = self.create_client(C, srv, callback_group=self.group)
        try:
            self.call(cli, req, timeout=10.0)
        finally:
            self.destroy_client(cli)

    # ───────────── 대기 위치 ─────────────
    def start_standby(self, why):
        with self.lock:
            if self.busy:
                return False, '로봇 동작 중'
            if self.error:
                return False, f'로봇 오류 상태: {self.error}'
            if not self.connected():
                return False, '로봇 미연결 (두산 bringup / get_current_posx 확인)'
            self.busy = True
        threading.Thread(target=self._go_standby, args=(why,), daemon=True).start()
        return True, '대기 위치로 이동 시작'

    def _go_standby(self, why):
        log = self.get_logger()
        try:
            log.info(f'[team_robot] 대기 위치로 이동 ({why})')
            tcp = self.read_tcp() if self.mode == 'real' else self.tcp
            if tcp is not None and math.dist(tcp[:3], self.standby_xyz) <= self.pos_tol:
                log.info('[team_robot]   이미 대기 위치')
            else:
                if tcp is not None and tcp[2] < self.standby_xyz[2] - 3.0:      # 판 근처에서 바로 관절 이동하지 않음
                    log.info(f'[team_robot]   수직 상승 Z={self.standby_xyz[2]:.1f}')
                    self.move_line([tcp[0], tcp[1], self.standby_xyz[2]], '수직 상승')
                log.info(f'[team_robot]   준비 자세 {self.p["home_joint"]}')
                self.move_home()
                log.info('[team_robot]   공급 위치 위로 이동')
                self.move_line(self.standby_xyz, '공급 위치 위')
            self.gripper('wait')
            if self.mode == 'real':
                self.read_tcp()
            log.info('[team_robot] 대기 위치 도착')
        except Exception as e:
            self.error = f'대기 위치 이동 실패: {e}'
            log.error(f'[team_robot] {self.error}')
        finally:
            self.busy = False

    def srv_go_standby(self, req, res):
        res.success, res.message = self.start_standby('GUI/서비스 요청')
        return res

    def srv_clear_error(self, req, res):
        if self.busy:
            res.success, res.message = False, '로봇 동작 중'
        else:
            old, self.error = self.error, ''
            res.success, res.message = True, ('오류 해제: ' + old) if old else '오류 없음'
            self.get_logger().warn(f'[team_robot] {res.message}')
        return res

    # ───────────── 착수 Action ─────────────
    def on_goal(self, req):
        why = ''
        with self.lock:
            if not self.connected():
                why = '로봇 미연결'
            elif self.busy:
                why = '로봇 동작 중'
            elif self.error:
                why = f'로봇 오류 상태: {self.error}'
            elif not self.at_standby():
                why = '대기 위치 아님'
            elif req.board_revision != self.revision():
                why = f'board_revision 불일치 (요청 {req.board_revision}, 로봇 확인 {self.revision()})'
            elif not req.request_id or req.request_id in self.ids:
                why = 'request_id 없음/중복'
            elif req.row >= 8 or req.col >= 8:
                why = f'범위 밖 ({req.row},{req.col})'
            elif req.color not in (1, 2):
                why = f'color 오류 {req.color}'
            elif self.board[req.row * 8 + req.col]:
                why = f'({req.row},{req.col}) 에 이미 돌이 있음'
            if why:
                self.get_logger().warn(f'[team_robot] 착수 요청 거절: {why}')
                return GoalResponse.REJECT
            self.ids.add(req.request_id)
            self.busy = True
            return GoalResponse.ACCEPT

    def execute(self, handle):
        req = handle.request
        out = PlaceStone.Result()
        out.request_id = req.request_id
        color = '흑' if req.color == 1 else '백'
        log = self.get_logger()
        stage = None
        try:
            steps = self.planner.plan(req.row, req.col)
            log.info(f'[team_robot] 착수 시작: {color} ({req.row},{req.col}) turn {req.turn_id}')
            for i, s in enumerate(steps, 1):
                if s.stage != stage:
                    stage = s.stage
                    fb = PlaceStone.Feedback()
                    fb.stage = stage
                    handle.publish_feedback(fb)
                xyz = '' if s.xyz is None else f' ({s.xyz[0]:.1f}, {s.xyz[1]:.1f}, {s.xyz[2]:.1f})'
                log.info(f'[team_robot]   {i}/{len(steps)} {s.name}{xyz}')
                if s.kind == 'line':
                    self.move_line(s.xyz, s.name)
                else:
                    self.gripper(s.kind)
                if self.mode == 'dry' and s.kind == 'open':
                    log.warn(f'[team_robot]   DRY: 지금 {color}돌을 ({req.row},{req.col}) 에 놓으세요 '
                             f'({self.dry_place_wait:.0f}초 대기)')
                    time.sleep(self.dry_place_wait)
            if self.mode == 'real':
                self.read_tcp()                              # 마지막 그리퍼 대기 뒤 다시 실측
            if not self.at_standby():
                raise MotionError('복귀 후 대기 위치 실측 확인 실패')
            out.success = True
            out.returned_to_standby = True
            log.info(f'[team_robot] 착수 완료: {color} ({req.row},{req.col}), 대기 위치 복귀 확인')
            if self.place_pub is not None:
                self.place_pub.publish(String(data=f'{req.row},{req.col},{"b" if req.color == 1 else "w"},robot'))
            handle.succeed()
        except Exception as e:
            self.error = f'착수 실패 [{stage}]: {e}'
            out.error = self.error
            log.error(f'[team_robot] {self.error}  -> 로봇/돌 상태 확인 후 /robot/clear_error')
            handle.abort()
        finally:
            self.busy = False
        return out


def main(args=None):
    rclpy.init(args=args)
    try:
        node = RobotNode()
    except (OSError, ValueError, ImportError) as e:      # 좌표 파일 없음/격자 오류/dsr_msgs2 없음 등
        rclpy.logging.get_logger('team_robot').fatal(f'[team_robot] 시작 실패: {e}')
        rclpy.shutdown()
        sys.exit(1)
    ex = MultiThreadedExecutor(num_threads=4)
    ex.add_node(node)
    try:
        ex.spin()
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        ex.shutdown()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
