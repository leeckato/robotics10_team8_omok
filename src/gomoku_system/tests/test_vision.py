import unittest
import numpy as np
import cv2
from gomoku_system.vision import Vision
from gomoku_system.stone_detection_marker import make_grid,sample_lab
class VisionTests(unittest.TestCase):
 def setUp(self):
  self.image=np.full((600,600,3),190,np.uint8)
  d=cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
  for i,(x,y) in enumerate([(15,15),(495,15),(495,495),(15,495)]):
   a=cv2.aruco.generateImageMarker(d,i,85);self.image[y-5:y+90,x-5:x+90]=255;self.image[y:y+85,x:x+85]=cv2.cvtColor(a,cv2.COLOR_GRAY2BGR)
  corners,ids,_=cv2.aruco.ArucoDetector(d).detectMarkers(self.image)
  markers={str(int(i)):c.reshape(4,2).tolist() for c,i in zip(corners,ids.flatten())}
  grid=make_grid([[145,145],[455,145],[455,455],[145,455]],8)
  self.cal=dict(n=8,grid=grid.tolist(),markers=markers,image_size=[600,600])
  for i in range(8):
   t=round(145+310*i/7);cv2.line(self.image,(145,t),(455,t),(45,45,45),1);cv2.line(self.image,(t,145),(t,455),(45,45,45),1)
  self.colors={k:sample_lab(np.full((10,10,3),v,np.uint8),5,5) for k,v in [('black',25),('white',225)]}
 def run_frames(self,image):
  engine=Vision(self.cal)
  for _ in range(18):display,result=engine.process(image,self.colors)
  return result
 def test_empty(self):
  r=self.run_frames(self.image);self.assertTrue(r['valid']);self.assertFalse(any(r['board']));self.assertEqual(r['offgrid'],0)
 def test_stones(self):
  cv2.circle(self.image,(234,234),12,(25,25,25),-1);cv2.circle(self.image,(322,322),12,(135,135,135),1);cv2.circle(self.image,(322,322),11,(225,225,225),-1)
  r=self.run_frames(self.image);self.assertTrue(r['valid']);self.assertEqual(r['board'][2*8+2],1);self.assertEqual(r['board'][4*8+4],2)
 def test_offgrid(self):
  cv2.circle(self.image,(211,211),12,(25,25,25),-1)
  r=self.run_frames(self.image);self.assertGreater(r['offgrid'],0)
 def test_loss(self):
  self.image[:110,:110]=190;r=self.run_frames(self.image);self.assertFalse(r['valid']);self.assertFalse(r['tracking'])
if __name__=='__main__':unittest.main()
