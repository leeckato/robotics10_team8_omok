import json,time,threading
from pathlib import Path
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from gomoku_interfaces.msg import BoardObservation,RobotStatus
from gomoku_interfaces.srv import Inspect
from sensor_msgs.msg import Image

class VisionNode(Node):
    def __init__(self):
        super().__init__('gomoku_vision')
        self.sim=bool(self.declare_parameter('simulation',False).value)
        if self.sim:raise ValueError('Runtime package requires a real camera')
        self.path=Path(self.declare_parameter('calibration',str(Path.home()/'.config/gomoku/marker_calibration.json')).value).expanduser()
        self.pub=self.create_publisher(BoardObservation,'/vision/observation',10)
        self.raw_images=self.create_publisher(Image,'/vision/image_raw',qos_profile_sensor_data)
        self.images=self.create_publisher(Image,'/vision/debug_image',qos_profile_sensor_data)
        self.create_service(Inspect,'/vision/inspect',self.inspect)
        self.create_subscription(RobotStatus,'/robot/status',self.robot,10)
        self.last_request='';self.request='';self.board=[0]*64;self.off=0;self.revision=1;self.stop=threading.Event();self.lock=threading.Lock();self.latest=None;self.robot_busy=False;self.robot_time=0;self.anchor=None;self.thread=None
        if not self.sim:
            self.thread=threading.Thread(target=self.capture,daemon=True);self.thread.start()
        self.create_timer(.1,self.tick)
    def robot(self,msg):self.robot_busy=msg.busy;self.robot_time=time.monotonic()
    def inspect(self,req,res):
        if not req.request_id:res.accepted=False;res.message='request_id required';return res
        self.request=req.request_id;res.accepted=True;res.message='New frames will carry request_id';return res
    def capture(self):
        pipeline=None;started=False
        try:
            import numpy as np,pyrealsense2 as rs
            from .vision import Vision
            from .detection_core import DETECTOR_VERSION
            self.get_logger().info('Detector: '+DETECTOR_VERSION)
            cal=json.loads(self.path.read_text())
            if cal['n']!=8:raise ValueError('Only 8x8 is supported')
            engine=Vision(cal);pipeline=rs.pipeline();cfg=rs.config();w,h=cal['image_size'];cfg.enable_stream(rs.stream.color,w,h,rs.format.bgr8,30);pipeline.start(cfg);started=True
            while not self.stop.is_set():
                frames=pipeline.poll_for_frames()
                if not frames:self.stop.wait(.01);continue
                frame=frames.get_color_frame()
                if not frame:continue
                # Capture request id before processing; old processing cannot satisfy a new request.
                rid=self.request
                captured_at=time.monotonic();captured_stamp=self.get_clock().now().to_msg()
                if rid!=self.last_request:engine.request_fresh();self.last_request=rid
                image=np.asanyarray(frame.get_data()).copy()
                display,result=engine.process(image,cal.get('colors',{}),self.robot_busy)
                if result['valid'] and result['grid'] is not None:
                    grid=np.array(result['grid'])
                    if self.anchor is None:self.anchor=grid.copy()
                    elif np.max(np.linalg.norm(grid-self.anchor,axis=1))>3:
                        self.revision+=1;self.anchor=grid.copy()
                with self.lock:self.latest=(captured_at,rid,result,display.copy(),self.revision,image.copy(),captured_stamp)
        except Exception as e:
            self.get_logger().error('Camera: '+str(e))
            with self.lock:self.latest=None
        finally:
            if started:pipeline.stop()
    def tick(self):
        msg=BoardObservation();msg.stamp=self.get_clock().now().to_msg();msg.board_revision=self.revision;msg.request_id=self.request
        with self.lock:latest=self.latest
        if latest and time.monotonic()-latest[0]<1:
            _,rid,data,frame,revision,raw,captured_stamp=latest;msg.stamp=captured_stamp;msg.request_id=rid;msg.tracking_valid=data['tracking'];msg.state_valid=data['valid'];msg.board=data['board'];msg.off_grid_count=data['offgrid'];msg.detail=data['reason'];msg.board_revision=revision
            out=Image();out.header.stamp=msg.stamp;out.header.frame_id='camera_color_optical_frame';out.height,out.width=frame.shape[:2];out.encoding='bgr8';out.step=out.width*3;out.data=frame.tobytes();self.images.publish(out)
            raw_msg=Image();raw_msg.header=out.header;raw_msg.height,raw_msg.width=raw.shape[:2];raw_msg.encoding='bgr8';raw_msg.step=raw_msg.width*3;raw_msg.data=raw.tobytes();self.raw_images.publish(raw_msg)
        else:msg.board=[-1]*64;msg.detail='No fresh camera frame'
        if self.robot_busy:msg.state_valid=False;msg.detail='Robot busy'
        self.pub.publish(msg)
    def destroy_node(self):
        self.stop.set()
        if self.thread:self.thread.join(2)
        super().destroy_node()

def main(args=None):
    rclpy.init(args=args);node=VisionNode()
    try:rclpy.spin(node)
    except KeyboardInterrupt:pass
    finally:
        node.destroy_node()
        if rclpy.ok():rclpy.shutdown()
