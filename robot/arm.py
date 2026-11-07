"""
로봇팔 드라이버 래퍼

모든 로봇팔은 BaseArm 인터페이스를 따릅니다. 나머지 코드(pick_place, GUI)는
이 인터페이스만 쓰므로, 로봇팔 기종이 바뀌어도 이 파일만 고치면 됩니다.

  driver: mock   -> MockArm   (실제 로봇 없이 동작 확인, 콘솔 출력 + 대기 시간)
  driver: custom -> CustomArm (여러분 로봇 SDK로 TODO 부분을 채우세요)

좌표 단위는 mm, 로봇 베이스 좌표계 기준.
"""
import time
from abc import ABC, abstractmethod


class BaseArm(ABC):
    @abstractmethod
    def connect(self): ...

    @abstractmethod
    def move_to(self, x, y, z):
        """(x, y, z) mm 로 이동하고 도착할 때까지 기다림"""

    @abstractmethod
    def grip(self, close: bool):
        """True: 집기(그리퍼 닫기 / 흡착 ON), False: 놓기"""

    @abstractmethod
    def get_position(self):
        """현재 (x, y, z) 반환"""

    def home(self, pos):
        self.move_to(*pos)

    def close(self):
        pass


class MockArm(BaseArm):
    """실제 로봇 없이 테스트용. 움직임을 출력하고 이동 시간을 흉내냄"""

    def __init__(self, move_delay=0.3, verbose=True, on_place=None):
        self.pos = [150.0, 0.0, 120.0]
        self.gripping = False
        self.move_delay = move_delay
        self.verbose = verbose
        self.on_place = on_place     # 테스트에서 '돌이 놓였다'를 흉내내기 위한 콜백

    def _log(self, msg):
        if self.verbose:
            print(f'[MockArm] {msg}')

    def connect(self):
        self._log('연결됨 (가짜 로봇)')

    def move_to(self, x, y, z):
        self._log(f'이동 -> ({x:.1f}, {y:.1f}, {z:.1f})')
        time.sleep(self.move_delay)
        self.pos = [x, y, z]

    def grip(self, close):
        self._log('집기' if close else '놓기')
        if not close and self.gripping and self.on_place:
            self.on_place(tuple(self.pos))
        self.gripping = close
        time.sleep(self.move_delay / 2)

    def get_position(self):
        return tuple(self.pos)


class CustomArm(BaseArm):
    """
    ▶ 여기에 실제 로봇팔 SDK 코드를 넣으세요.

    예) myCobot (pymycobot)
        from pymycobot.mycobot import MyCobot
        self.mc = MyCobot(port, 115200)
        move_to: self.mc.send_coords([x, y, z, rx, ry, rz], speed, 1); 도착까지 대기
        grip:    self.mc.set_gripper_state(1 if close else 0, 50) 또는 흡착펌프 제어
    예) Dobot Magician (pydobot)
        from pydobot import Dobot
        self.dev = Dobot(port=port)
        move_to: self.dev.move_to(x, y, z, 0, wait=True)
        grip:    self.dev.suck(close)
    """

    def __init__(self, port='COM3', speed=50):
        self.port, self.speed = port, speed
        self.dev = None

    def connect(self):
        raise NotImplementedError('robot/arm.py 의 CustomArm.connect 를 SDK로 구현하세요')

    def move_to(self, x, y, z):
        raise NotImplementedError('CustomArm.move_to 를 구현하세요')

    def grip(self, close):
        raise NotImplementedError('CustomArm.grip 을 구현하세요')

    def get_position(self):
        raise NotImplementedError('CustomArm.get_position 을 구현하세요')

    def close(self):
        pass


def create_arm(cfg):
    r = cfg['robot']
    driver = r.get('driver', 'mock')
    if driver == 'mock':
        return MockArm()
    if driver == 'custom':
        return CustomArm(r.get('port', 'COM3'), r.get('speed', 50))
    raise ValueError(f'알 수 없는 robot.driver: {driver}')
