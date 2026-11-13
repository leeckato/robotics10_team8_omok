"""SIMULATION ONLY. First empty cell is a plumbing test, not the team's AI."""
import threading,time
import rclpy
from rclpy.node import Node
from rclpy.executors import MultiThreadedExecutor
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.action import ActionServer,GoalResponse
from gomoku_interfaces.msg import BoardObservation,RobotStatus,HandState
from gomoku_interfaces.srv import NextMove,SetSimulation
from gomoku_interfaces.action import PlaceStone

class MockPeers(Node):
    def __init__(self):
        super().__init__('gomoku_mock_peers');self.group=ReentrantCallbackGroup();self.lock=threading.Lock();self.busy=False;self.board=[0]*64;self.revision=1;self.done_ids=set()
        if not self.declare_parameter('simulation',False).value:raise RuntimeError('Mocks require simulation:=true')
        self.create_subscription(BoardObservation,'/vision/observation',self.observe,10,callback_group=self.group)
        self.status=self.create_publisher(RobotStatus,'/robot/status',10);self.hands=self.create_publisher(HandState,'/vision/hand_state',10)
        self.create_timer(.1,self.tick,callback_group=self.group)
        self.create_service(NextMove,'/algorithm/next_move',self.ai,callback_group=self.group)
        self.setter=self.create_client(SetSimulation,'/vision/set_simulation',callback_group=self.group)
        self.server=ActionServer(self,PlaceStone,'/robot/place_stone',execute_callback=self.execute,goal_callback=self.goal,callback_group=self.group)
    def observe(self,msg):
        if msg.state_valid:self.board=list(msg.board)
        self.revision=msg.board_revision
    def tick(self):
        s=RobotStatus();s.stamp=self.get_clock().now().to_msg();s.connected=True;s.busy=self.busy;s.at_standby=not self.busy;s.board_revision=self.revision;self.status.publish(s)
        h=HandState();h.stamp=s.stamp;h.valid=True;h.hand_present=False;self.hands.publish(h)
    def ai(self,req,res):
        res.game_id=req.game_id;res.turn_id=req.turn_id;res.request_id=req.request_id
        empty=[i for i,v in enumerate(req.board) if v==0];res.success=bool(empty)
        if empty:res.row,res.col=divmod(empty[0],8)
        else:res.error='Board full'
        return res
    def goal(self,req):
        with self.lock:
            if self.busy or req.request_id in self.done_ids or req.board_revision!=self.revision or req.row>=8 or req.col>=8 or req.color not in (1,2) or self.board[req.row*8+req.col]:return GoalResponse.REJECT
            self.busy=True;return GoalResponse.ACCEPT
    def execute(self,handle):
        req=handle.request;result=PlaceStone.Result();result.request_id=req.request_id
        try:
            for stage in ('PICKING','PLACING','RETURNING'):
                feedback=PlaceStone.Feedback();feedback.stage=stage;handle.publish_feedback(feedback);time.sleep(.3)
            if not self.setter.service_is_ready():raise RuntimeError('Simulation service missing')
            msg=SetSimulation.Request();msg.board=self.board.copy();msg.board[req.row*8+req.col]=req.color
            future=self.setter.call_async(msg);end=time.monotonic()+3
            while not future.done() and time.monotonic()<end:time.sleep(.01)
            if not future.done() or not future.result().accepted:raise RuntimeError('Simulation update failed')
            result.success=True;result.returned_to_standby=True;self.done_ids.add(req.request_id);handle.succeed()
        except Exception as e:result.error=str(e);handle.abort()
        finally:self.busy=False
        return result

def main(args=None):
    rclpy.init(args=args);node=MockPeers();executor=MultiThreadedExecutor(num_threads=4);executor.add_node(node)
    try:executor.spin()
    except KeyboardInterrupt:pass
    finally:
        executor.shutdown();node.destroy_node()
        if rclpy.ok():rclpy.shutdown()
