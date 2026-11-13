import unittest
from gomoku_system.game import Game,InvalidMove,winner

class Tests(unittest.TestCase):
 def test_normal(self):
  g=Game();g.start(1,[0]*64);b=g.board.copy();b[9]=1;g.accept(b);self.assertEqual(g.phase,'ROBOT_WAIT');b[10]=2;g.accept(b);self.assertEqual(g.phase,'HUMAN')
 def test_second(self):
  g=Game();g.start(2,[0]*64);self.assertEqual(g.phase,'ROBOT_WAIT')
 def test_errors_preserve(self):
  g=Game();g.start(1,[0]*64)
  for b,off in [([0]*64,0),([1,1]+[0]*62,0),([2]+[0]*63,0),([1]+[0]*63,1)]:
   with self.assertRaises(InvalidMove):g.accept(b,off)
   self.assertEqual(g.board,[0]*64);self.assertEqual(g.turn,1)
 def test_move_existing(self):
  g=Game();g.start(1,[0]*64);b=g.board.copy();b[0]=1;g.accept(b);b[0]=0;b[1]=1;b[2]=2
  with self.assertRaises(InvalidMove):g.accept(b)
  self.assertEqual(g.board[0],1)
 def test_invalid_observation(self):
  g=Game();g.start(1,[0]*64)
  with self.assertRaises(InvalidMove):g.accept([1]+[0]*63,valid=False)
 def test_start(self):
  for valid,b in [(False,[0]*64),(True,[1]+[0]*63)]:
   with self.assertRaises(InvalidMove):Game().start(1,b,valid)
 def test_all_directions(self):
  for dr,dc in [(0,1),(1,0),(1,1),(1,-1)]:
   b=[0]*64;r,c=(0,5) if dc==-1 else (0,0)
   for k in range(5):b[(r+k*dr)*8+c+k*dc]=2
   self.assertEqual(winner(b,8),2)
 def test_draw(self):
  # 4x4 cannot contain five in a row.
  self.assertEqual(winner([1,2]*8,4),3)
 def test_finish(self):
  g=Game();g.phase='HUMAN';g.board[:4]=[1]*4;b=g.board.copy();b[4]=1;g.accept(b);self.assertEqual(g.result,1)
  with self.assertRaises(InvalidMove):g.accept(b)
if __name__=='__main__':unittest.main()
