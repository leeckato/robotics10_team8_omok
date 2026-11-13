"""
손 감지 노드 (팀원 연결 규격 v0.1 '3. 손 감지 담당')

  구독  /vision/image_raw   sensor_msgs/Image (bgr8), qos_profile_sensor_data
  발행  /vision/hand_state  gomoku_interfaces/HandState (stamp, valid, hand_present), 기본 15Hz
  (선택) /hand/debug_image  판정 화면 (debug_image:=true 일 때, 2Hz)

구조 (검사가 느려도 영상 수신/발행이 밀리지 않도록 분리)
  영상 콜백   : 최신 영상을 직렬화된 바이트 그대로 보관 (2.7MB 영상을 매번 Python 객체로 바꾸지 않음)
  검사 스레드 : 새 영상이 오면 판정 -> 결과(원본 stamp, valid, present) 보관
  발행 타이머 : publish_hz 로 마지막 결과 발행. 결과의 원본 영상이 stale_sec 보다 오래됐으면 valid=false

규칙
  - 카메라를 직접 열지 않음 (비전 노드가 독점)
  - stamp = 원본 영상의 header.stamp (새 시각으로 바꾸지 않음)
  - 영상 없음 / 0.5초 이상 오래됨 / 판 영역 못 찾음 / 형식 오류 / 검사 예외 -> valid=false
  - 3초 대기/차례 판단은 게임 제어 담당. 이 노드는 손 상태만 보냄
"""
import threading
import time

import cv2
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from rclpy.serialization import deserialize_message
from sensor_msgs.msg import Image
from gomoku_interfaces.msg import HandState

from team_hand.processor import DEFAULTS, HandProcessor, fill_image_msg, image_msg_to_bgr


def stamp_to_sec(stamp):
    return float(stamp.sec) + float(stamp.nanosec) * 1e-9


class HandNode(Node):
    def __init__(self):
        super().__init__('team_hand')
        params = {name: self.declare_parameter(name, default).value for name, default in DEFAULTS.items()}
        self.publish_hz = float(self.declare_parameter('publish_hz', 15.0).value)
        self.stale_sec = float(self.declare_parameter('stale_sec', 0.5).value)
        self.debug_enabled = bool(self.declare_parameter('debug_image', False).value)
        self.image_topic = str(self.declare_parameter('image_topic', '/vision/image_raw').value)
        # 같은 PC 의 비전 노드/GUI 가 CPU 를 쓸 수 있도록: OpenCV 스레드 수와 초당 검사 횟수 제한
        cv_threads = int(self.declare_parameter('cv_threads', 1).value)
        self.max_process_hz = float(self.declare_parameter('max_process_hz', 15.0).value)
        if cv_threads > 0:
            cv2.setNumThreads(cv_threads)

        self.proc = HandProcessor(params, log=self.get_logger().info)

        self._lock = threading.Lock()
        self._new_image = threading.Event()
        self._running = True
        self._latest = None              # 마지막으로 받은 Image (직렬화 바이트)
        self._result = None              # (stamp_msg, valid, present, reason) — 마지막 검사 결과
        self._last_reason = ''
        self._last_debug = 0.0

        self.sub = self.create_subscription(Image, self.image_topic, self.on_image, qos_profile_sensor_data,
                                            raw=True)   # 검사할 영상만 역직렬화
        self.pub = self.create_publisher(HandState, '/vision/hand_state', 10)
        self.debug_pub = self.create_publisher(Image, '/hand/debug_image', qos_profile_sensor_data) \
            if self.debug_enabled else None
        self.create_timer(1.0 / max(1.0, self.publish_hz), self.tick)
        self._worker = threading.Thread(target=self._work, daemon=True)
        self._worker.start()
        self.get_logger().info(f'[team_hand] {self.image_topic} -> /vision/hand_state @ {self.publish_hz:g}Hz, '
                               f'stale {self.stale_sec}s')

    # ───────── 영상 수신 (가볍게) ─────────
    def on_image(self, raw):
        with self._lock:
            self._latest = raw
        self._new_image.set()

    # ───────── 검사 스레드 ─────────
    def _work(self):
        done_stamp = None
        min_gap = 1.0 / self.max_process_hz if self.max_process_hz > 0 else 0.0
        last_start = 0.0
        while self._running:
            if not self._new_image.wait(timeout=0.2):
                continue
            wait = min_gap - (time.monotonic() - last_start)
            if wait > 0:                                      # 검사 횟수 상한 (그동안 온 영상 중 최신만 검사)
                time.sleep(wait)
            last_start = time.monotonic()
            self._new_image.clear()
            with self._lock:
                raw = self._latest
            if raw is None:
                continue
            try:
                msg = deserialize_message(raw, Image)
            except Exception as e:
                self._set_result(self.get_clock().now().to_msg(), False, False, f'영상 메시지 해석 실패: {e}')
                continue
            st = stamp_to_sec(msg.header.stamp)
            if st == done_stamp:
                continue
            done_stamp = st
            if self.now_sec() - st > self.stale_sec:          # 이미 오래된 영상은 검사하지 않음
                continue
            try:
                bgr = image_msg_to_bgr(msg)
            except Exception as e:
                self._set_result(msg.header.stamp, False, False, str(e))
                continue
            want_debug = self.debug_pub is not None and st - self._last_debug >= 0.5
            r = self.proc.process(bgr, st, want_debug=want_debug)
            self._set_result(msg.header.stamp, r.valid, r.present, r.reason)
            if want_debug and r.debug is not None:
                self._last_debug = st
                self.debug_pub.publish(fill_image_msg(Image(), r.debug, msg.header))

    def _set_result(self, stamp, valid, present, reason):
        with self._lock:
            self._result = (stamp, bool(valid), bool(present), reason)

    # ───────── 발행 타이머 ─────────
    def now_sec(self):
        return self.get_clock().now().nanoseconds * 1e-9

    def tick(self):
        with self._lock:
            res, latest = self._result, self._latest
        if res is None:                                   # 아직 검사한 영상이 없음 (결과가 없으니 현재 시각)
            reason = '영상 없음 (/vision/image_raw 미수신)' if latest is None else '첫 검사 대기'
            return self._publish(self.get_clock().now().to_msg(), False, False, reason)
        stamp, valid, present, reason = res
        age = self.now_sec() - stamp_to_sec(stamp)
        if age > self.stale_sec:
            return self._publish(stamp, False, False, f'영상이 오래됨 ({self.stale_sec}s 넘게 새 영상 없음)')
        self._publish(stamp, valid, present, reason)

    def _publish(self, stamp, valid, present, reason=''):
        m = HandState()
        m.stamp = stamp                                   # 원본 영상 시각 그대로
        m.valid = bool(valid)
        m.hand_present = bool(present) if valid else False
        self.pub.publish(m)
        if not valid and reason != self._last_reason:
            self.get_logger().warn(f'[team_hand] valid=false: {reason}')
        elif valid and self._last_reason:
            self.get_logger().info('[team_hand] 정상 검사 재개')
        self._last_reason = '' if valid else reason

    def destroy_node(self):
        self._running = False
        self._new_image.set()
        self._worker.join(timeout=2.0)
        self.proc.close()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = HandNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
