"""Publish actual detection here. Default is INVALID, not hand absent."""
import rclpy
from rclpy.node import Node
from gomoku_interfaces.msg import HandState
class HandAdapter(Node):
    def __init__(self):
        super().__init__('team_hand');self.pub=self.create_publisher(HandState,'/vision/hand_state',10);self.create_timer(.1,self.tick)
    def detect_latest_frame(self):
        # Return (valid, present). valid=False on failure or stale camera frame.
        # Subscribe to the SAME camera stream; don't open RealSense a second time.
        return False,False
    def tick(self):
        valid,present=self.detect_latest_frame();msg=HandState();msg.stamp=self.get_clock().now().to_msg();msg.valid=valid;msg.hand_present=present;self.pub.publish(msg)
def main():
    rclpy.init();node=HandAdapter()
    try:rclpy.spin(node)
    except KeyboardInterrupt:pass
    finally:node.destroy_node();rclpy.shutdown()
if __name__=='__main__':main()
