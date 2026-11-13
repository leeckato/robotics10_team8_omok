"""Four-marker planar tracking with one-time grid registration. No robot control."""
import argparse
import json
from pathlib import Path
import cv2
import numpy as np
from .roi_core import detect, draw

ROOT=Path.home()/'.local/share/gomoku'
IDS=(0,1,2,3)

def marker_points(image, detector):
    corners, ids, _=detector.detectMarkers(image)
    result={}
    if ids is not None:
        for c,i in zip(corners,ids.flatten()):
            if int(i) in IDS:
                if int(i) in result: return {}, image.copy()
                result[int(i)]=c.reshape(4,2).astype(np.float32)
    out=image.copy()
    if ids is not None: cv2.aruco.drawDetectedMarkers(out,corners,ids)
    return result,out

def transform_grid(calibration, markers):
    if set(markers)!=set(IDS): return None
    source=np.concatenate([calibration['markers'][str(i)] for i in IDS]).astype(np.float32)
    target=np.concatenate([markers[i] for i in IDS]).astype(np.float32)
    H,inliers=cv2.findHomography(source,target,cv2.RANSAC,2.0)
    if H is None or not np.isfinite(H).all() or inliers is None or inliers.mean()<.875: return None
    projected=cv2.perspectiveTransform(source[None],H)[0]
    if np.max(np.linalg.norm(projected-target,axis=1))>3.0: return None
    grid=cv2.perspectiveTransform(np.array(calibration['grid'],np.float32)[None],H)[0]
    return grid if np.isfinite(grid).all() else None

def make_grid(corners,n):
    quad=np.array(corners,np.float32)
    if not cv2.isContourConvex(quad.astype(np.int32)) or cv2.contourArea(quad)<400:
        raise ValueError('Select a convex grid: top-left, top-right, bottom-right, bottom-left')
    H=cv2.getPerspectiveTransform(np.float32([[0,0],[n-1,0],[n-1,n-1],[0,n-1]]),quad)
    return cv2.perspectiveTransform(np.float32([[[c,r] for r in range(n) for c in range(n)]]),H)[0]

def sample_lab(image,x,y):
    patch=image[max(0,y-2):y+3,max(0,x-2):x+3]
    lab=cv2.cvtColor(patch.astype(np.float32)/255,cv2.COLOR_BGR2LAB)
    return np.median(lab.reshape(-1,3),axis=0).tolist()

def classify_color(image,result,colors):
    x,y=result['center'];r=result['radius']*.6
    x0=max(0,int(x-r));y0=max(0,int(y-r));x1=min(image.shape[1],int(x+r)+2);y1=min(image.shape[0],int(y+r)+2)
    patch=image[y0:y1,x0:x1]
    yy,xx=np.ogrid[y0:y1,x0:x1]
    mask=(xx-x)**2+(yy-y)**2<=r*r
    lab=cv2.cvtColor(patch.astype(np.float32)/255,cv2.COLOR_BGR2LAB)
    pixels=lab[mask]
    if len(pixels)<5: return 'unknown'
    value=np.median(pixels,axis=0)
    distances={k:float(np.linalg.norm(value-np.array(colors[k]))) for k in ('black','white')}
    ordered=sorted(distances,key=distances.get)
    result['lab_distances']=distances
    return ordered[0] if distances[ordered[0]]<40 and distances[ordered[1]]-distances[ordered[0]]>10 else 'unknown'

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--calibrate',action='store_true')
    p.add_argument('--config',type=Path,default=Path.home()/'.config/gomoku/marker_calibration.json')
    p.add_argument('--size',type=int,nargs=2,default=[640,480])
    p.add_argument('--grid-size',type=int,default=8)
    args=p.parse_args()
    args.config.parent.mkdir(parents=True,exist_ok=True)
    if args.grid_size<2: p.error('grid-size >= 2')
    if not hasattr(cv2,'aruco'): raise RuntimeError('OpenCV aruco missing; see guide')
    dictionary=cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    params=cv2.aruco.DetectorParameters();params.cornerRefinementMethod=cv2.aruco.CORNER_REFINE_SUBPIX
    detector=cv2.aruco.ArucoDetector(dictionary,params)
    calibration=None if args.calibrate else json.loads(args.config.read_text())
    if calibration and calibration['image_size']!=args.size: raise ValueError('Use original image size or recalibrate')
    import pyrealsense2 as rs
    pipeline=rs.pipeline();config=rs.config();config.enable_stream(rs.stream.color,*args.size,rs.format.bgr8,30)
    started=False; frozen=None; clicks=[]; mode=None; latest=None; colors={} if calibration is None else calibration.get('colors',{})
    history={};previous=None;steady=0;last=None;show_roi=False
    def mouse(event,x,y,flags,param):
        nonlocal mode
        if event!=cv2.EVENT_LBUTTONDOWN: return
        if frozen is not None and len(clicks)<4: clicks.append([x,y]);return
        if mode and latest is not None:
            colors[mode]=sample_lab(latest,x,y); print('Sampled',mode,colors[mode]);mode=None
            if calibration is not None:
                calibration['colors']=colors
                args.config.write_text(json.dumps(calibration,indent=2))
    cv2.namedWindow('Marker Stone Detection');cv2.setMouseCallback('Marker Stone Detection',mouse)
    thresholds=argparse.Namespace(radius_min=.16,radius_max=.43,offset=.35,edge=60,hough=16,support=.55,black_max=95,white_min=125)
    try:
        pipeline.start(config);started=True
        print('Q quit; calibration: F freeze, click grid TL TR BR BL, S save, C clear; tracking: B/W then click stone interior; R ROI; S diagnostics')
        while True:
            frame=pipeline.wait_for_frames(5000).get_color_frame()
            if not frame: continue
            latest=np.asanyarray(frame.get_data()).copy()
            image=frozen.copy() if frozen is not None else latest.copy()
            markers,display=marker_points(image,detector)
            stable={};results=[];grid=None
            if args.calibrate:
                for j,pt in enumerate(clicks):
                    cv2.circle(display,tuple(pt),4,(0,0,255),-1);cv2.putText(display,str(j),tuple(pt),0,.5,(0,0,255),1)
                status=f'CALIBRATE markers={sorted(markers)} clicks={len(clicks)} F freeze'
            else:
                grid=transform_grid(calibration,markers)
                if grid is not None:
                    if not np.all((grid[:,0]>0)&(grid[:,0]<args.size[0]-1)&(grid[:,1]>0)&(grid[:,1]<args.size[1]-1)): grid=None
                if grid is None:
                    history={};steady=0;previous=None;status='TRACKING LOST - results invalid'
                else:
                    step=float(np.median(np.linalg.norm(grid.reshape(calibration['n'],calibration['n'],2)[:,1:]-grid.reshape(calibration['n'],calibration['n'],2)[:,:-1],axis=2)))
                    movement=np.inf if previous is None else float(np.max(np.linalg.norm(grid-previous,axis=1)))
                    steady=steady+1 if movement<max(.8,step*.04) else 0
                    previous=grid.copy()
                    n=calibration['n'];coords=[dict(row=i//n,col=i%n,x=float(v[0]),y=float(v[1])) for i,v in enumerate(grid)]
                    for v in grid: cv2.circle(display,tuple(np.rint(v).astype(int)),2,(0,200,0),-1)
                    ready=steady>=10 and all(k in colors for k in ('black','white'))
                    status='READY' if ready else ('SAMPLE COLORS: B/W then click' if len(colors)<2 else 'BOARD MOVING / SETTLING')
                    if ready:
                        results,rois=detect(image,coords,thresholds)
                        for result in results: result['color']=classify_color(image,result,colors)
                        current={(v['row'],v['col']):v['color'] for v in results if v['color']!='unknown'}
                        history={k:(v,history.get(k,(None,0))[1]+1 if history.get(k,(None,0))[0]==v else 1) for k,v in current.items()}
                        stable={k:v for k,(v,count) in history.items() if count>=5}
                        display=draw(display,coords,results,rois,show_roi,stable)
                    else: history={}
            output={'status':status,'confirmed':[dict(row=k[0],col=k[1],color=v) for k,v in stable.items()]}
            if output!=last: print(output);last=output
            cv2.putText(display,status,(8,20),0,.45,(0,120,255),1)
            cv2.imshow('Marker Stone Detection',display)
            key=cv2.waitKey(1)&255
            if key==ord('q'):break
            if key==ord('r'):show_roi=not show_roi
            if args.calibrate:
                if key==ord('f'):
                    live,_=marker_points(latest,detector)
                    if set(live)==set(IDS): frozen=latest.copy();clicks=[]
                    else: print('All four markers must be visible before freezing')
                if key==ord('c'): clicks=[];frozen=None
                if key==ord('s') and frozen is not None and len(clicks)==4:
                    grid=make_grid(clicks,args.grid_size)
                    calibration={'dictionary':'DICT_4X4_50','image_size':args.size,'n':args.grid_size,
                                 'markers':{str(i):markers[i].tolist() for i in IDS},'grid':grid.tolist(),'colors':{}}
                    args.config.write_text(json.dumps(calibration,indent=2));print('Saved calibration. Restart without --calibrate');break
            else:
                if key in (ord('b'),ord('w')): mode='black' if key==ord('b') else 'white';print('Click inside',mode,'stone (avoid glare)')
                if key==ord('s'):
                    out=ROOT/'marker_diagnostics';out.mkdir(exist_ok=True)
                    cv2.imwrite(str(out/'current.png'),image);cv2.imwrite(str(out/'display.png'),display)
                    payload={**output,'candidates':results,'coordinates':None if grid is None else grid.tolist(),'robot_coordinates_validated':False}
                    (out/'result.json').write_text(json.dumps(payload,indent=2));print('Saved',out)
    finally:
        if started:pipeline.stop()
        cv2.destroyAllWindows()

if __name__=='__main__':main()
