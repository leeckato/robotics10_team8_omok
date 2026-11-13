"""Controller logic with lightweight doubles, NOT a ROS/DDS integration test."""
import ast,time,uuid,unittest
from pathlib import Path
from types import SimpleNamespace as NS
from concurrent.futures import Future
from gomoku_system.game import Game,InvalidMove

class Msg:
 def __init__(self,**kw):self.__dict__.update(kw)
class Endpoint:
 def __init__(self):self.ready=False;self.calls=[]
 def service_is_ready(self):return self.ready
 def server_is_ready(self):return self.ready
 def call_async(self,req):f=Future();self.calls.append((req,f));return f
 def send_goal_async(self,req):return self.call_async(req)
class Node:
 def __init__(self,*a):pass
 def declare_parameter(self,name,default):return NS(value=default)
 def create_publisher(self,*a):return NS(publish=lambda msg:None)
 def create_subscription(self,*a):pass
 def create_service(self,*a):pass
 def create_timer(self,*a):pass
 def create_client(self,*a):return Endpoint()
 def get_clock(self):
  now=lambda:NS(nanoseconds=time.time_ns(),to_msg=lambda:NS(sec=int(time.time()),nanosec=0))
  return NS(now=now)
source=Path(__file__).parents[1]/'gomoku_system/controller.py'
tree=ast.parse(source.read_text());cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Controller')
namespace=dict(time=time,uuid=uuid,Node=Node,Game=Game,InvalidMove=InvalidMove,state_qos=lambda:None,ActionClient=lambda *a:Endpoint(),GoalStatus=NS(STATUS_SUCCEEDED=4))
for name in ('BoardObservation','GameState','HandState','RobotStatus','StartGame','Inspect','NextMove','PlaceStone','Trigger'):namespace[name]=type(name,(),dict(Request=Msg,Goal=Msg)) if name not in ('GameState',) else Msg
exec(compile(ast.Module(body=[cls],type_ignores=[]),str(source),'exec'),namespace)
Controller=namespace['Controller']
def stamp():
 t=time.time_ns();return NS(sec=t//10**9,nanosec=t%10**9)
def observation(board,rid='',revision=1):return NS(stamp=stamp(),request_id=rid,board=board,board_revision=revision,off_grid_count=0,tracking_valid=True,state_valid=True)
class ControllerTests(unittest.TestCase):
 def setup_game(self):
  c=Controller();c.observe(observation([0]*64));res=c.start(NS(human_color=1),Msg(accepted=False));self.assertTrue(res.accepted);return c
 def test_user_confirm(self):
  c=self.setup_game();c.inspect_client.ready=True;c.manual(None,Msg());c.wait_since-=4;c.tick();self.assertEqual(c.phase,'INSPECT_HUMAN')
  b=[0]*64;b[9]=1;c.observe(observation(b,'old-request'));self.assertEqual(c.turn_id,0)
  c.observe(observation(b,c.rid));self.assertEqual(c.phase,'WAIT_AI');self.assertEqual(c.turn_id,1)
 def test_invalid_stays(self):
  c=self.setup_game();c.inspect_client.ready=True;c.request_inspect();b=[1,1]+[0]*62;c.observe(observation(b,c.rid));self.assertEqual(c.phase,'HUMAN');self.assertEqual(c.g.board,[0]*64)
 def test_board_revision(self):
  c=self.setup_game();c.inspect_client.ready=True;c.request_inspect();c.observe(observation([1]+[0]*63,c.rid,2));self.assertEqual(c.phase,'ERROR')
 def test_hand_absence_does_not_trigger_without_entry(self):
  c=self.setup_game();c.use_hand=True;c.hand_event(NS(stamp=stamp(),valid=True,hand_present=False));c.tick();self.assertEqual(c.phase,'HUMAN');self.assertIsNone(c.clear_since)
 def test_hand_reentry_cancels(self):
  c=self.setup_game();c.use_hand=True;c.hand_event(NS(stamp=stamp(),valid=True,hand_present=True));c.hand_event(NS(stamp=stamp(),valid=True,hand_present=False));self.assertIsNotNone(c.clear_since);c.manual(None,Msg());c.hand_event(NS(stamp=stamp(),valid=True,hand_present=True));self.assertEqual(c.phase,'HUMAN')
 def test_uncertain_motion_cannot_reset(self):
  c=self.setup_game();c.motion_uncertain=True;r=c.end(None,Msg(success=False));self.assertFalse(r.success)
 def test_ai_correlation(self):
  c=self.setup_game();c.phase='WAIT_AI';c.ai.ready=True;c.tick();req,f=c.ai.calls[-1];f.set_result(NS(game_id='wrong',turn_id=req.turn_id,request_id=req.request_id,success=True,row=0,col=0,error=''));self.assertEqual(c.phase,'ERROR')
 def test_old_stamp_rejected(self):
  c=self.setup_game();old=c.obs;msg=observation([1]+[0]*63);msg.stamp.sec-=5;c.observe(msg);self.assertIs(c.obs,old)
if __name__=='__main__':unittest.main()
