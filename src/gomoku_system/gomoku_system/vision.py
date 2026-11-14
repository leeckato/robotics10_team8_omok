"""One shared vision pipeline for both calibrate and the ROS vision node."""
import time,hashlib,json
from pathlib import Path
import cv2
import numpy as np
from .stone_detection_marker import marker_points,transform_grid
from .detection_core import BoardDetector,TemporalBoard

class Vision:
    def __init__(self,calibration):
        self.cal=calibration;self.n=int(calibration['n']);self.previous=None;self.steady=0;self.grid_filter=None;self.last_good=0.;self.signature=None;self.count=0
        d=cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50);p=cv2.aruco.DetectorParameters();p.cornerRefinementMethod=cv2.aruco.CORNER_REFINE_SUBPIX
        self.detector=cv2.aruco.ArucoDetector(d,p);self.objects=BoardDetector(self.n);self.temporal=TemporalBoard(self.n);self.inverse=None;self.reference_error=""
        reference=calibration.get("reference_path")
        if reference:
            try:
                with np.load(Path(reference).expanduser(),allow_pickle=False) as data:
                    if str(data["calibration_key"].item())!=self.calibration_key():raise ValueError("mapping differs")
                    self.objects.reference=data["image"].copy()
            except (OSError,ValueError,KeyError) as exc:self.reference_error=str(exc)
    def calibration_key(self):
        data={k:self.cal[k] for k in ('n','image_size','grid','markers')}
        return hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()
    def save_reference(self,image,path):
        if self.grid_filter is None or self.steady<5 or time.monotonic()-self.last_good>.5:raise ValueError('Board tracking is not stable')
        n=self.n;side=(n-1)*40+49
        corners=self.grid_filter[[0,n-1,n*n-1,n*(n-1)]].astype(np.float32)
        dest=np.float32([[24,24],[side-25,24],[side-25,side-25],[24,side-25]])
        H=cv2.getPerspectiveTransform(corners,dest)
        reference=cv2.warpPerspective(image,H,(side,side))
        path=Path(path).expanduser();path.parent.mkdir(parents=True,exist_ok=True)
        np.savez_compressed(path,image=reference,calibration_key=np.array(self.calibration_key()))
        self.objects.reference=reference;self.temporal.clear();self.reference_error=''
        return str(path.resolve())
    def reset(self):
        self.signature=None;self.count=0;self.steady=0;self.previous=None;self.grid_filter=None;self.temporal.clear()
    def request_fresh(self):
        # Keep visual tracks, but discard vote evidence before a new game request.
        self.temporal.history.clear();self.signature=None;self.count=0
    def paint(self,display,tracks,muted=False):
        if self.inverse is None:return
        for item in tracks:
            x0,y0,x1,y1=item['bbox'];poly=cv2.perspectiveTransform(np.float32([[[x0,y0],[x1,y0],[x1,y1],[x0,y1]]]),self.inverse)[0].astype(int)
            held=muted or item.get('held',False);tint=(110,160,180) if held else (0,0,255) if item['color']=='black' else (255,0,0)
            cv2.polylines(display,[poly],True,tint,2)
            label=f"{item['color']} {item['row']},{item['col']}"+(' HOLD' if held else '')
            cv2.putText(display,label,tuple(poly[0]),cv2.FONT_HERSHEY_SIMPLEX,.35,tint,1)
    def process(self,image,colors,robot_busy=False):
        now=time.monotonic();markers,display=marker_points(image,self.detector);grid=transform_grid(self.cal,markers);n=self.n
        result=dict(valid=False,tracking=False,board=[-1]*(n*n),offgrid=0,reason='마커 확인 중',candidates=[],grid=None)
        tracks=[dict(t,confirmed=True) for k,t in self.temporal.tracks.items() if self.temporal.confirmed.get(k)==t['color']]
        if grid is None:
            if now-self.last_good<.5:self.paint(display,tracks,muted=True)
            else:self.reset()
            result['reason']='마커 가림: 관측 무효';return display,result
        h,w=image.shape[:2]
        if not np.all((grid[:,0]>0)&(grid[:,0]<w-1)&(grid[:,1]>0)&(grid[:,1]<h-1)):
            self.reset();result['reason']='보드 영상 범위 이탈';return display,result
        step=float(np.median(np.linalg.norm(np.diff(grid.reshape(n,n,2),axis=1),axis=2)))
        movement=np.inf if self.previous is None else float(np.max(np.linalg.norm(grid-self.previous,axis=1)))
        moved=self.grid_filter is not None and np.max(np.linalg.norm(grid-self.grid_filter,axis=1))>max(3,step*.2)
        self.steady=self.steady+1 if movement<max(1.5,step*.12) else 0
        if moved:self.temporal.clear();self.grid_filter=grid.copy();self.steady=0
        if self.grid_filter is None:self.grid_filter=grid.copy()
        else:self.grid_filter=.75*self.grid_filter+.25*grid
        self.previous=grid.copy();self.last_good=now;result.update(tracking=True,grid=grid.tolist())
        for x,y in self.grid_filter:cv2.circle(display,(round(x),round(y)),2,(0,180,0),-1)
        if robot_busy or self.steady<5:
            self.paint(display,tracks,muted=True);result['reason']='로봇 동작 중: 관측 무효' if robot_busy else '보드 안정화 중';return display,result
        corners=self.grid_filter[[0,n-1,n*n-1,n*(n-1)]].astype(np.float32);side=(n-1)*40+49
        dest=np.float32([[24,24],[side-25,24],[side-25,side-25],[24,side-25]])
        H=cv2.getPerspectiveTransform(corners,dest);self.inverse=np.linalg.inv(H)
        warped=cv2.warpPerspective(image,H,(side,side))
        # A new marker calibration invalidates the old empty reference. Never
        # publish guessed occupancy as a valid game observation during bootstrap.
        if self.objects.reference is None:
            self.temporal.clear()
            result.update(reason='빈 판 기준 필요: 판을 비우고 calibrate에서 E 두 번',reference_used=False,reference_error=self.reference_error)
            return display,result
        items,outside,unknown=self.objects.detect(warped,colors)
        board,visible,valid=self.temporal.update(items,len(outside),bool(unknown))
        # Off-grid candidate is a valid observed error if its appearance is stable;
        # it must reach game.validate() instead of timing out without an explanation.
        signature=(tuple((v['row'],v['col'],v['color']) for v in sorted(items,key=lambda v:(v['row'],v['col']))),len(outside),len(unknown))
        self.count=self.count+1 if signature==self.signature else 1;self.signature=signature
        if outside and self.count>=5 and not unknown:valid=not any(t.get('held') for t in visible)
        self.paint(display,visible)
        for item in outside:
            poly=cv2.perspectiveTransform(np.float32([[[item['bbox'][0],item['bbox'][1]],[item['bbox'][2],item['bbox'][3]]]]),self.inverse)[0].astype(int)
            cv2.rectangle(display,tuple(poly[0]),tuple(poly[1]),(0,180,255),1)
        reason=('관측 안정 · 백돌 객체 검출 v4' if self.objects.reference is not None else '관측 안정 · 상대 대비') if valid else '관측 재확인 중 (화면 유지와 실제 판정은 별도)'
        result.update(valid=valid,board=board,offgrid=len(outside),reason=reason,candidates=items,display_tracks=visible,unknown_candidates=unknown,reference_used=self.objects.reference is not None,reference_error=self.reference_error)
        return display,result
