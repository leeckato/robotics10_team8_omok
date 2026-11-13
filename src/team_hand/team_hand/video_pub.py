"""
(시험용) mp4 영상을 /vision/image_raw 로 발행 — 카메라/비전 노드 없이 손 노드만 시험할 때

  ros2 run team_hand video_pub --ros-args -p video:=/경로/test.mp4 -p loop:=true

※ gomoku_vision(실제 비전 노드)과 동시에 켜지 마세요. 같은 토픽에 영상이 두 군데서 들어갑니다.
"""
import cv2
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image

from team_hand.processor import fill_image_msg


class VideoPublisher(Node):
    def __init__(self):
        super().__init__('team_hand_video_pub')
        self.path = str(self.declare_parameter('video', '').value)
        self.loop = bool(self.declare_parameter('loop', True).value)
        self.topic = str(self.declare_parameter('topic', '/vision/image_raw').value)
        self.cap = cv2.VideoCapture(self.path)
        if not self.path or not self.cap.isOpened():
            raise RuntimeError(f'영상을 열 수 없음: video:="{self.path}"')
        fps = float(self.declare_parameter('fps', 0.0).value) or self.cap.get(cv2.CAP_PROP_FPS) or 30.0
        self.pub = self.create_publisher(Image, self.topic, qos_profile_sensor_data)
        self.create_timer(1.0 / fps, self.tick)
        self.count = 0
        self.get_logger().info(f'{self.path} -> {self.topic} @ {fps:g}fps (loop={self.loop})')

    def tick(self):
        ok, frame = self.cap.read()
        if not ok:
            if not self.loop:
                self.get_logger().info('영상 끝')
                raise SystemExit
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = self.cap.read()
            if not ok:
                return
        msg = Image()
        msg.header.stamp = self.get_clock().now().to_msg()     # 발행 시각 = 영상 시각
        msg.header.frame_id = 'camera'
        self.pub.publish(fill_image_msg(msg, frame, msg.header))
        self.count += 1


def main(args=None):
    rclpy.init(args=args)
    node = VideoPublisher()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, SystemExit, ExternalShutdownException):
        pass
    finally:
        node.cap.release()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
