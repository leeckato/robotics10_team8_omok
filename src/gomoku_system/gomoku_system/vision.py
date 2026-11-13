"""Board-wide candidate detection in rectified board coordinates."""
import cv2
import numpy as np
from .stone_detection_marker import marker_points, transform_grid, classify_color

class Vision:
    def __init__(self,calibration):
        self.cal=calibration;self.previous=None;self.steady=0;self.signature=None;self.count=0
        d=cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
        p=cv2.aruco.DetectorParameters();p.cornerRefinementMethod=cv2.aruco.CORNER_REFINE_SUBPIX
        self.detector=cv2.aruco.ArucoDetector(d,p)
    def reset(self):self.signature=None;self.count=0;self.steady=0;self.previous=None
    def process(self,image,colors,robot_busy=False):
        markers,display=marker_points(image,self.detector)
        grid=transform_grid(self.cal,markers);n=self.cal['n'];empty=[0]*(n*n)
        result=dict(valid=False,tracking=False,board=empty,offgrid=0,reason='마커 확인 중',candidates=[],grid=None)
        if grid is None:
            self.reset();result['reason']='마커 4개를 모두 확인할 수 없습니다.';return display,result
        h,w=image.shape[:2]
        if not np.all((grid[:,0]>0)&(grid[:,0]<w-1)&(grid[:,1]>0)&(grid[:,1]<h-1)):
            self.reset();result['reason']='보드가 영상 범위를 벗어났습니다.';return display,result
        result.update(tracking=True,grid=grid.tolist())
        step=float(np.median(np.linalg.norm(np.diff(grid.reshape(n,n,2),axis=1),axis=2)))
        motion=np.inf if self.previous is None else np.max(np.linalg.norm(grid-self.previous,axis=1))
        self.previous=grid.copy();self.steady=self.steady+1 if motion<max(.8,.04*step) else 0
        for x,y in grid:cv2.circle(display,(round(x),round(y)),2,(0,180,0),-1)
        if robot_busy or self.steady<10 or not all(k in colors for k in ('black','white')):
            self.count=0;self.signature=None
            result['reason']='로봇 동작 중: 판정 보류' if robot_busy else ('보드 위치 안정화 중' if self.steady<10 else 'B/W 버튼으로 기준 색을 등록하세요.')
            return display,result
        corners=grid[[0,n-1,n*n-1,n*(n-1)]].astype(np.float32)
        scale=40.;margin=24;side=int((n-1)*scale+2*margin+1)
        dest=np.float32([[margin,margin],[side-margin-1,margin],[side-margin-1,side-margin-1],[margin,side-margin-1]])
        H=cv2.getPerspectiveTransform(corners,dest);inv=np.linalg.inv(H)
        warp=cv2.warpPerspective(image,H,(side,side));gray=cv2.cvtColor(warp,cv2.COLOR_BGR2GRAY)
        blur=cv2.GaussianBlur(gray,(5,5),1)
        circles=cv2.HoughCircles(blur,cv2.HOUGH_GRADIENT,1,16,param1=60,param2=18,minRadius=6,maxRadius=18)
        edges=cv2.dilate(cv2.Canny(blur,30,60),np.ones((3,3),np.uint8))
        board=[0]*(n*n);offgrid=0;uncertain=False;candidates=[]
        if circles is not None:
            for x,y,r in circles[0]:
                angle=np.linspace(0,2*np.pi,96,endpoint=False)
                ex=np.rint(x+r*np.cos(angle)).astype(int);ey=np.rint(y+r*np.sin(angle)).astype(int)
                ok=(ex>=0)&(ex<side)&(ey>=0)&(ey<side)
                if ok.mean()<.95 or (edges[ey[ok],ex[ok]]>0).mean()<.55:continue
                c=int(round((x-margin)/scale));row=int(round((y-margin)/scale))
                distance=float(np.hypot(x-(margin+c*scale),y-(margin+row*scale)))
                candidate=dict(center=[float(x),float(y)],radius=float(r),row=row,col=c)
                color=classify_color(warp,candidate,colors);candidate['color']=color
                mapped=0<=row<n and 0<=c<n and distance<=scale*.28
                candidate['mapped']=mapped
                if color=='unknown':uncertain=True
                if not mapped:offgrid+=1
                elif color!='unknown':
                    idx=row*n+c
                    if board[idx]:uncertain=True
                    board[idx]=1 if color=='black' else 2
                pts=np.float32([[[x-r,y-r],[x+r,y-r],[x+r,y+r],[x-r,y+r]]])
                poly=cv2.perspectiveTransform(pts,inv)[0].astype(int)
                tint=(0,0,255) if color=='black' else (255,0,0) if color=='white' else (0,180,255)
                cv2.polylines(display,[poly],True,tint,1)
                cv2.putText(display,f'{color} {row},{c}',tuple(poly[0]),0,.35,tint,1)
                candidates.append(candidate)
        signature=(tuple(board),offgrid,uncertain)
        self.count=self.count+1 if signature==self.signature else 1;self.signature=signature
        result.update(board=board,offgrid=offgrid,candidates=candidates,valid=self.count>=5 and not uncertain,
                      reason='관측 안정' if self.count>=5 and not uncertain else '돌 관측 안정화 중 / 색 불확실')
        return display,result
