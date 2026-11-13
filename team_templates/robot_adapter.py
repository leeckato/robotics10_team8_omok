"""Integration template. Defaults to disconnected and refuses every motion."""
import threading
import rclpy
from rclpy.node import Node
from rclpy.action import ActionServer,GoalResponse
from rclpy.executors import MultiThreadedExecutor
from rclpy.callback_groups import ReentrantCallbackGroup
from gomoku_interfaces.action import PlaceStone
from gomoku_interfaces.msg import RobotStatus

class RobotAdapter(Node):
    def __init__(self):
        super().__init__('team_robot');self.group=ReentrantCallbackGroup();self.lock=threading.Lock()
        self.connected=False;self.busy=False;self.at_standby=False;self.board_revision=0;self.error='Hardware adapter not implemented';self.ids=set()
        self.pub=self.create_publisher(RobotStatus,'/robot/status',10)
        self.create_timer(.1,self.publish_status,callback_group=self.group)
        self.server=ActionServer(self,PlaceStone,'/robot/place_stone',goal_callback=self.goal,execute_callback=self.execute,callback_group=self.group)
    def publish_status(self):
        # Replace these flags using actual controller state, not requested state.
        s=RobotStatus();s.stamp=self.get_clock().now().to_msg();s.connected=self.connected;s.busy=self.busy;s.at_standby=self.at_standby;s.board_revision=self.board_revision;s.error=self.error;self.pub.publish(s)
    def goal(self,req):
        with self.lock:
            if not self.connected or self.busy or not self.at_standby or self.error or req.board_revision!=self.board_revision or not req.request_id or req.request_id in self.ids or req.row>=8 or req.col>=8 or req.color not in (1,2):return GoalResponse.REJECT
            self.ids.add(req.request_id);self.busy=True;self.at_standby=False;return GoalResponse.ACCEPT
    def place_and_return(self,row,col,color,feedback):
        # Call your tested Doosan/ gripper functions here.
        # Resolve row,col using robot-base poses, never camera pixels.
        # Confirm placement AND return to standby before returning.
        raise NotImplementedError('Implement hardware execution and verification')
    def execute(self,handle):
        req=handle.request;out=PlaceStone.Result();out.request_id=req.request_id
        def feedback(stage):
            msg=PlaceStone.Feedback();msg.stage=stage;handle.publish_feedback(msg)
        try:
            self.place_and_return(req.row,req.col,req.color,feedback)
            if not self.at_standby:raise RuntimeError('Standby has not been measured')
            out.success=True;out.returned_to_standby=True;handle.succeed()
        except Exception as e:self.error=str(e);out.error=self.error;handle.abort()
        finally:self.busy=False
        return out

def main():
    rclpy.init();node=RobotAdapter();executor=MultiThreadedExecutor(num_threads=4);executor.add_node(node)
    try:executor.spin()
    except KeyboardInterrupt:pass
    finally:executor.shutdown();node.destroy_node();rclpy.shutdown()
if __name__=='__main__':main()
