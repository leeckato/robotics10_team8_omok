"""Experimental ROI stone detector. Coordinates stay unchanged; no robot commands."""
import argparse
import json
from pathlib import Path
import cv2
import numpy as np


def detect(image, coords, args):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    points = np.array([[p['x'], p['y']] for p in coords], dtype=float)
    distances = np.linalg.norm(points[:, None] - points[None, :], axis=2)
    np.fill_diagonal(distances, np.inf)
    spacing = distances.min(axis=1)
    found = []
    rois = []
    for i, p in enumerate(coords):
        x, y = points[i]
        step = spacing[i]
        half = int(np.ceil(step * .70))
        x0, y0 = max(0, int(x)-half), max(0, int(y)-half)
        x1, y1 = min(gray.shape[1], int(x)+half+1), min(gray.shape[0], int(y)+half+1)
        rois.append((x0, y0, x1, y1))
        patch = gray[y0:y1, x0:x1]
        if min(patch.shape) < 9:
            continue
        # Upsampling improves parameter granularity, not original image detail.
        scale = 3
        up = cv2.resize(patch, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        blur = cv2.GaussianBlur(up, (5, 5), .8)
        rmin = max(2, int(step * args.radius_min * scale))
        rmax = max(rmin+1, int(step * args.radius_max * scale))
        circles = cv2.HoughCircles(blur, cv2.HOUGH_GRADIENT, 1, max(4, step*scale*.35),
                                   param1=args.edge, param2=args.hough,
                                   minRadius=rmin, maxRadius=rmax)
        if circles is None:
            continue
        edges = cv2.Canny(blur, args.edge/2, args.edge)
        near_edges = cv2.dilate(edges, np.ones((3, 3), np.uint8))
        candidates = []
        for cx, cy, radius in circles[0]:
            gx, gy, rr = x0+cx/scale, y0+cy/scale, radius/scale
            d = np.linalg.norm(points - [gx, gy], axis=1)
            if np.argmin(d) != i or d[i] > step*args.offset:
                continue
            # Require edges around the circumference; a grid cross alone should fail.
            theta = np.linspace(0, 2*np.pi, 96, endpoint=False)
            ex = np.rint(cx+radius*np.cos(theta)).astype(int)
            ey = np.rint(cy+radius*np.sin(theta)).astype(int)
            valid = (ex>=0)&(ey>=0)&(ex<up.shape[1])&(ey<up.shape[0])
            if valid.mean() < .95:
                continue
            support = float(np.mean(near_edges[ey[valid], ex[valid]] > 0))
            if support < args.support:
                continue
            yy, xx = np.ogrid[:patch.shape[0], :patch.shape[1]]
            mask = (xx-(gx-x0))**2+(yy-(gy-y0))**2 <= (rr*.60)**2
            pixels = patch[mask]
            if pixels.size < 5:
                continue
            median = float(np.median(pixels))
            if median <= args.black_max:
                color = 'black'
            elif median >= args.white_min and np.percentile(pixels, 20) >= args.white_min-30:
                color = 'white'
            else:
                color = 'unknown'
            candidates.append({'row':int(p['row']), 'col':int(p['col']), 'color':color,
                               'center':[float(gx),float(gy)], 'radius':float(rr),
                               'median':median, 'edge_support':support,
                               'score':support-.25*float(d[i]/step)})
        if candidates:
            found.append(max(candidates, key=lambda c:c['score']))
    # Overlapping ROIs must never assign one physical circle twice.
    kept = []
    for candidate in sorted(found, key=lambda c:c['score'], reverse=True):
        if all(np.linalg.norm(np.array(candidate['center'])-other['center']) >
               .8*min(candidate['radius'], other['radius']) for other in kept):
            kept.append(candidate)
    return kept, rois


def draw(image, coords, results, rois, show_roi, stable):
    output = image.copy()
    for p in coords:
        cv2.circle(output, (int(p['x']),int(p['y'])), 2, (0,180,0), -1)
    if show_roi:
        for x0,y0,x1,y1 in rois:
            cv2.rectangle(output,(x0,y0),(x1-1,y1-1),(60,100,60),1)
    for result in results:
        cx,cy = result['center']; r=result['radius']
        color = {'black':(0,0,255),'white':(255,0,0),'unknown':(0,180,255)}[result['color']]
        cv2.rectangle(output,(round(cx-r),round(cy-r)),(round(cx+r),round(cy+r)),color,1)
        key = (result['row'],result['col'])
        label = f"{result['color']} {key[0]},{key[1]} L={result['median']:.0f}"
        if key not in stable:
            label += ' ?'
        cv2.putText(output,label,(round(cx+r),round(cy-r)),cv2.FONT_HERSHEY_SIMPLEX,.32,color,1)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--board', type=Path, default=Path(__file__).resolve().parent/'board_coordinates.json')
    parser.add_argument('--image', type=Path, help='Offline image instead of RealSense')
    parser.add_argument('--output-dir', type=Path, default=Path(__file__).resolve().parent/'roi_diagnostics')
    parser.add_argument('--radius-min',type=float,default=.16,help='Minimum radius / local grid spacing')
    parser.add_argument('--radius-max',type=float,default=.43,help='Maximum radius / local grid spacing')
    parser.add_argument('--offset',type=float,default=.35,help='Maximum center offset / local spacing')
    parser.add_argument('--black-max',type=float,default=95)
    parser.add_argument('--white-min',type=float,default=125)
    parser.add_argument('--edge',type=float,default=60)
    parser.add_argument('--hough',type=float,default=16)
    parser.add_argument('--support',type=float,default=.55)
    parser.add_argument('--confirm',type=int,default=5)
    parser.add_argument('--no-gui',action='store_true')
    args = parser.parse_args()
    if not (0 < args.radius_min < args.radius_max < .65 and 0 < args.offset < .5
            and 0 < args.support <= 1 and args.confirm >= 1 and args.edge > 0
            and args.hough > 0 and 0 <= args.black_max < args.white_min <= 255):
        parser.error('Invalid detector thresholds')
    board=json.loads(args.board.read_text(encoding='utf-8'))
    coords=board['coordinates']; width,height=map(int,board['image_size'])
    keys=[(p['row'],p['col']) for p in coords]
    if len(coords)<2 or len(set(keys))!=len(keys):
        raise ValueError('Mapping needs unique grid indices and at least two points')
    points=[(p['x'],p['y']) for p in coords]
    if len(set(points))!=len(points) or any(not(0<=x<width and 0<=y<height) for x,y in points):
        raise ValueError('Invalid pixel coordinates')
    pipeline=None; started=False; show_roi=False; history={}; last=None
    def save(image, display, results, stable):
        args.output_dir.mkdir(parents=True,exist_ok=True)
        cv2.imwrite(str(args.output_dir/'roi_current.png'),image)
        cv2.imwrite(str(args.output_dir/'roi_display.png'),display)
        payload={'index_base':'unchanged from board_coordinates.json', 'candidates':results,
                 'confirmed':[{'row':k[0],'col':k[1],'color':v} for k,v in stable.items()],
                 'note':'No circle does not prove empty. No robot control.',
                 'parameters':{k:str(v) if isinstance(v,Path) else v for k,v in vars(args).items()}}
        (args.output_dir/'roi_result.json').write_text(json.dumps(payload,indent=2),encoding='utf-8')
        print('Saved diagnostics:',args.output_dir)
    try:
        if args.image:
            offline=cv2.imread(str(args.image))
            if offline is None:
                raise ValueError('Cannot read image')
        else:
            import pyrealsense2 as rs
            pipeline=rs.pipeline(); config=rs.config()
            config.enable_stream(rs.stream.color,width,height,rs.format.bgr8,30)
            pipeline.start(config); started=True
        print('Q: quit / R: show ROI / S: save diagnostics. No robot commands.')
        while True:
            if args.image:
                image=offline.copy()
            else:
                frames=pipeline.wait_for_frames(timeout_ms=5000)
                frame=frames.get_color_frame()
                if not frame:
                    continue
                image=np.asanyarray(frame.get_data()).copy()
            if image.shape[:2] != (height,width):
                raise ValueError(f'Image size {image.shape[:2]} != mapping {(height,width)}; do not resize coordinates implicitly')
            results,rois=detect(image,coords,args)
            current={(r['row'],r['col']):r['color'] for r in results if r['color']!='unknown'}
            history={k:(v,history.get(k,(None,0))[1]+1 if history.get(k,(None,0))[0]==v else 1)
                     for k,v in current.items()}
            stable={k:v for k,(v,n) in history.items() if n>=args.confirm}
            if stable != last:
                print('Confirmed black:', sorted(k for k,v in stable.items() if v=='black'))
                print('Confirmed white:', sorted(k for k,v in stable.items() if v=='white'))
                last=stable.copy()
            display=draw(image,coords,results,rois,show_roi,stable)
            if args.image:
                # One still image cannot satisfy temporal confirmation.
                save(image,display,results,{})
                if not args.no_gui:
                    cv2.imshow('ROI Stone Detection',display); cv2.waitKey(0)
                break
            if not args.no_gui:
                cv2.imshow('ROI Stone Detection',display)
                key=cv2.waitKey(1)&255
                if key==ord('q'): break
                if key==ord('r'): show_roi=not show_roi
                if key==ord('s'): save(image,display,results,stable)
    except KeyboardInterrupt:
        pass
    finally:
        if started: pipeline.stop()
        if not args.no_gui: cv2.destroyAllWindows()


if __name__=='__main__':
    main()
