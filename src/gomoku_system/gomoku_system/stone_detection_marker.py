"""Four-marker planar tracking with one-time grid registration. No robot control."""
import argparse
import json
from pathlib import Path
import cv2
import numpy as np

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
    from .vision import Vision
    from .detection_core import DETECTOR_VERSION
    p=argparse.ArgumentParser(description='Shared stone detector / one-time marker registration')
    p.add_argument('--calibrate',action='store_true')
    p.add_argument('--config',type=Path,default=Path.home()/'.config/gomoku/marker_calibration.json')
    p.add_argument('--size',type=int,nargs=2,default=None)
    p.add_argument('--grid-size',type=int,default=8)
    args=p.parse_args();args.config.parent.mkdir(parents=True,exist_ok=True)
    calibration=None if args.calibrate else json.loads(args.config.read_text())
    size=args.size or (calibration['image_size'] if calibration else [640,480])
    if calibration and list(calibration['image_size'])!=list(size):raise ValueError('Image size differs from calibration')
    if args.grid_size<5:raise ValueError('grid-size must be at least 5')
    import pyrealsense2 as rs
    pipeline=rs.pipeline();config=rs.config();config.enable_stream(rs.stream.color,*size,rs.format.bgr8,30)
    dictionary=cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50);params=cv2.aruco.DetectorParameters();params.cornerRefinementMethod=cv2.aruco.CORNER_REFINE_SUBPIX
    detector=cv2.aruco.ArucoDetector(dictionary,params)
    engine=Vision(calibration) if calibration else None
    colors={} if calibration is None else calibration.get('colors',{})
    started=False;frozen=None;clicks=[];mode=None;latest=None;last=None;show_roi=False;reference_armed=False
    def mouse(event,x,y,flags,param):
        nonlocal mode
        if event!=cv2.EVENT_LBUTTONDOWN:return
        if frozen is not None and len(clicks)<4:clicks.append([x,y]);return
        if mode and latest is not None:
            colors[mode]=sample_lab(latest,x,y)
            print('Sampled',mode,colors[mode]);mode=None
            if calibration is not None:
                calibration['colors']=colors;args.config.write_text(json.dumps(calibration,indent=2));engine.reset()
    cv2.namedWindow('Marker Stone Detection');cv2.setMouseCallback('Marker Stone Detection',mouse)
    try:
        pipeline.start(config);started=True
        print('Detector:',DETECTOR_VERSION,'/ Q quit / S diagnostics / E twice: empty capture / R grid ROI')
        print('Calibration: F freeze / TL TR BR BL clicks / S save / C clear')
        if engine:
            print('Empty-board reference:', 'LOADED' if engine.objects.reference is not None else 'NOT SET - remove all stones, wait, press E')
            if engine.reference_error:print('Reference error:',engine.reference_error)
        while True:
            frame=pipeline.wait_for_frames(5000).get_color_frame()
            if not frame:continue
            latest=np.asanyarray(frame.get_data()).copy();image=frozen.copy() if frozen is not None else latest.copy()
            markers,display=marker_points(image,detector)
            if args.calibrate:
                data=dict(valid=False,tracking=False,board=[],offgrid=0,candidates=[],grid=None)
                for j,pt in enumerate(clicks):cv2.circle(display,tuple(pt),4,(0,0,255),-1);cv2.putText(display,str(j),tuple(pt),0,.5,(0,0,255),1)
                status=f'CALIBRATE markers={sorted(markers)} clicks={len(clicks)}'
            else:
                display,data=engine.process(image,colors)
                status=('EMPTY REFERENCE REQUIRED - CLEAR BOARD, PRESS E' if engine.objects.reference is None else 'READY' if data['valid'] else ('TRACKING LOST' if not data['tracking'] else 'VERIFYING - DISPLAY MAY HOLD'))
                if show_roi and data['grid'] is not None:
                    for x,y in data['grid']:cv2.rectangle(display,(round(x-9),round(y-9)),(round(x+9),round(y+9)),(80,120,80),1)
                confirmed=[dict(row=i//engine.n,col=i%engine.n,color='black' if v==1 else 'white') for i,v in enumerate(data['board']) if v in (1,2)] if data['valid'] else []
                summary=json.dumps(dict(status=status,confirmed=confirmed),sort_keys=True)
                if summary!=last:print(summary);last=summary
            cv2.putText(display,status,(8,20),0,.45,(0,120,255),1);cv2.imshow('Marker Stone Detection',display)
            key=cv2.waitKey(1)&255
            if key==ord('q'):break
            if key==ord('r'):show_roi=not show_roi
            if args.calibrate:
                if key==ord('f'):
                    live,_=marker_points(latest,detector)
                    if set(live)==set(IDS):frozen=latest.copy();clicks=[]
                    else:print('All four markers must be visible')
                if key==ord('c'):clicks=[];frozen=None
                if key==ord('s') and frozen is not None and len(clicks)==4:
                    grid=make_grid(clicks,args.grid_size)
                    saved=dict(dictionary='DICT_4X4_50',image_size=size,n=args.grid_size,markers={str(i):markers[i].tolist() for i in IDS},grid=grid.tolist(),colors={})
                    args.config.write_text(json.dumps(saved,indent=2));print('Saved calibration');break
            else:
                if key==ord('e'):
                    if not reference_armed:
                        reference_armed=True
                        print('EMPTY CAPTURE ARMED: remove ALL stones, hands and robot arm from board; press E again to confirm. Q cancels.')
                    else:
                        try:
                            reference_path=engine.save_reference(image,args.config.with_suffix('.empty.npz'))
                            calibration['reference_path']=reference_path
                            args.config.write_text(json.dumps(calibration,indent=2));print('Saved empty-board reference:',reference_path);reference_armed=False
                        except (OSError,ValueError) as exc:print('Reference save failed:',exc)
                if key in (ord('b'),ord('w')):mode='black' if key==ord('b') else 'white';print('Click inside',mode,'stone')
                if key==ord('s'):
                    out=ROOT/'marker_diagnostics';out.mkdir(parents=True,exist_ok=True)
                    cv2.imwrite(str(out/'current.png'),image);cv2.imwrite(str(out/'display.png'),display)
                    payload=dict(detector=DETECTOR_VERSION,status=status,state_valid=data['valid'],tracking_valid=data['tracking'],confirmed=confirmed,candidates=data['candidates'],coordinates=data['grid'],display_tracks=data.get('display_tracks',[]),offgrid=data['offgrid'],robot_coordinates_validated=False,reference_used=data.get('reference_used',False),reference_error=data.get('reference_error',''))
                    (out/'result.json').write_text(json.dumps(payload,indent=2));print('Saved',out)
    except KeyboardInterrupt:pass
    finally:
        if started:pipeline.stop()
        cv2.destroyAllWindows()

if __name__=='__main__':main()
