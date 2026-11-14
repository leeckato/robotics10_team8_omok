"""Shared object candidates + grid-background residuals + temporal confirmation.
A held display track is never treated as a fresh observation.
"""
from collections import deque
import time
import cv2
import numpy as np


def color_of(image, x, y, radius, colors, background=255.):
    h,w=image.shape[:2];yy,xx=np.ogrid[:h,:w]
    mask=(xx-x)**2+(yy-y)**2<=max(2,radius*.55)**2
    pixels=image[mask]
    if len(pixels)<5:return 'unknown'
    lab=cv2.cvtColor(pixels.reshape(-1,1,3).astype(np.float32)/255,cv2.COLOR_BGR2LAB).reshape(-1,3)
    med=np.median(lab,axis=0)
    anchors=[]
    try:
        black=np.array(colors['black'],float);white=np.array(colors['white'],float)
        if black.shape==(3,) and white.shape==(3,) and np.isfinite([black,white]).all() and black[0]<60 and white[0]>65 and white[0]-black[0]>25:
            anchors=[np.linalg.norm(med-black),np.linalg.norm(med-white)]
    except (KeyError,TypeError,ValueError):pass
    if anchors and min(anchors)<40 and abs(anchors[0]-anchors[1])>10:return 'black' if anchors[0]<anchors[1] else 'white'
    gray=cv2.cvtColor(pixels.reshape(-1,1,3),cv2.COLOR_BGR2GRAY).ravel()
    if np.median(gray)<110 and np.median(gray)/max(background,1)<.65:return 'black'
    if (med[0]>65 or np.median(gray)/max(background,1)>.72) and np.linalg.norm(med[1:])<30:return 'white'
    return 'unknown'


DETECTOR_VERSION = 'white_objects_v4'

class BoardDetector:
    """Input is a perspective-rectified 8x8 board, 40 px/cell, 24 px margin."""
    def __init__(self,n=8,step=40,margin=24):self.n=n;self.step=step;self.margin=margin;self.template=None;self.reference=None
    def detect(self,image,colors):
        n,s,m=self.n,self.step,self.margin;g=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
        candidates=[];offgrid=[];unknown=[]
        def add(x,y,r,method,score,bbox=None):
            col=int(round((x-m)/s));row=int(round((y-m)/s));distance=np.hypot(x-(m+col*s),y-(m+row*s))
            x0=max(0,int(x-20));x1=min(g.shape[1],int(x+21));y0=max(0,int(y-20));y1=min(g.shape[0],int(y+21))
            bg=float(np.percentile(g[y0:y1,x0:x1],85))
            color=color_of(image,x,y,r,colors,bg)
            item=dict(row=row,col=col,color=color,center=[float(x),float(y)],radius=float(r),method=method,score=float(score),bbox=bbox or [float(x-r),float(y-r),float(x+r),float(y+r)])
            if not(0<=row<n and 0<=col<n and distance<=s*.38):offgrid.append(item)
            elif color=='unknown':unknown.append(item)
            else:candidates.append(item)
        blur=cv2.GaussianBlur(g,(5,5),1)
        circles=cv2.HoughCircles(blur,cv2.HOUGH_GRADIENT,1,17,param1=60,param2=18,minRadius=6,maxRadius=18)
        edges=cv2.dilate(cv2.Canny(blur,30,60),np.ones((3,3),np.uint8))
        if circles is not None:
            for x,y,r in circles[0]:
                a=np.linspace(0,2*np.pi,96,endpoint=False);ex=np.rint(x+r*np.cos(a)).astype(int);ey=np.rint(y+r*np.sin(a)).astype(int)
                valid=(ex>=0)&(ey>=0)&(ex<g.shape[1])&(ey<g.shape[0])
                support=float(np.mean(edges[ey[valid],ex[valid]]>0)) if valid.any() else 0
                if valid.mean()>.95 and support>.55:add(float(x),float(y),float(r),'contour',support)
        if self.reference is not None:
            return self.reference_candidates(image,colors,candidates,offgrid,unknown)
        # Estimate the repeated printed-grid background from many intersections.
        # No empty-board file and no requirement that a stone be a perfect circle.
        radius=18;patches=[];normalized=[]
        for row in range(n):
            for col in range(n):
                x,y=m+col*s,m+row*s;p=g[y-radius:y+radius+1,x-radius:x+radius+1].astype(float)
                patches.append(p);normalized.append(p/max(30,float(np.percentile(p,85))))
        if not patches or any(p.shape!=(37,37) for p in patches):return candidates,offgrid,unknown
        values=np.array(normalized).reshape(n,n,37,37)
        if self.template is None:self.template=np.median(values[1:-1,1:-1],axis=(0,1))
        template=self.template
        yy,xx=np.mgrid[-18:19,-18:19];disk=xx**2+yy**2<14**2;core=xx**2+yy**2<8**2
        line=(np.abs(xx)<=2)|(np.abs(yy)<=2)
        for idx,(p,norm) in enumerate(zip(patches,normalized)):
            row,col=divmod(idx,n);x,y=m+col*s,m+row*s;diff=norm-template
            erased=int(np.sum((diff>.08)&line&disk))
            shadow=(diff<-.07)&(~line)&disk
            changed=int(shadow.sum());dark=float(np.mean(p[core]<100));ratio=float(np.median(norm[core]))
            black=dark>.5 and ratio<.65
            # White-on-white: require both a missing part of a printed line AND
            # a local off-line surface/rim/shadow change. Bright paper alone fails.
            flat=(np.percentile(p[core],90)-np.percentile(p[core],10))/max(30,np.percentile(p,85)) < .08
            flat_axis=[]
            for dx,dy in ((0,-8),(0,-4),(0,0),(0,4),(0,8),(-8,0),(-4,0),(4,0),(8,0)):
                sample=p[18+dy-3:18+dy+4,18+dx-3:18+dx+4]
                flat_axis.append((np.percentile(sample,90)-np.percentile(sample,10))/max(30,np.percentile(p,85)))
            structured_surface=flat or (ratio<.94 and min(flat_axis)<.06)
            white=(erased>=16 and changed>=55 and ratio>.62 and structured_surface)
            if not(black or white):continue
            evidence=shadow.copy() if white else ((p<110)&disk)
            ey,ex=np.where(evidence)
            if len(ex)<8:continue
            if white:
                # The visible shadow can sit below a raised stone. Keep its
                # intersection association; box includes the nearby stone surface.
                bx0,by0,bx1,by1=x-15,y-18,x+15,y+18
                cx,cy=x,y-3
            else:
                cx=x+float(np.median(ex))-18;cy=y+float(np.median(ey))-18
                bx0,by0,bx1,by1=x+int(ex.min())-20,y+int(ey.min())-20,x+int(ex.max())-16,y+int(ey.max())-16
            before=len(candidates)
            add(cx,cy,12,'grid_residual',min(.95,.6+changed/1000),[float(bx0),float(by0),float(bx1),float(by1)])
            # For a bright raised white object, color samples are taken on its
            # upper surface instead of the darker cast shadow below it.
            if len(candidates)==before and white and ratio>.72:
                unknown=[u for u in unknown if (u['row'],u['col'])!=(row,col)]
                candidates.append(dict(row=row,col=col,color='white',center=[float(cx),float(cy)],radius=12.,bbox=[float(bx0),float(by0),float(bx1),float(by1)],method='grid_residual',score=.7))
        selected={}
        for item in candidates:
            key=(item['row'],item['col'])
            if key not in selected or item['score']>selected[key]['score']:selected[key]=item
        # Deduplicate off-grid circles and candidates already matched to a cell.
        out=[]
        for item in offgrid:
            if any(np.linalg.norm(np.array(item['center'])-other['center'])<12 for other in list(selected.values())+out):continue
            out.append(item)
        unresolved=[u for u in unknown if (u['row'],u['col']) not in selected]
        return list(selected.values()),out,unresolved


    def reference_candidates(self,image,colors,candidates,offgrid,unknown):
        """Black occupancy is retained; white occupancy comes only from objects."""
        gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY).astype(np.float32)
        if self.reference.shape!=image.shape:raise ValueError('Reference image size differs')
        selected={(v['row'],v['col']):v for v in candidates if v['color']=='black'}
        yy,xx=np.mgrid[-18:19,-18:19];core=xx*xx+yy*yy<8**2
        for row in range(self.n):
            for col in range(self.n):
                x,y=self.margin+col*self.step,self.margin+row*self.step
                patch=gray[y-18:y+19,x-18:x+19]
                if patch.shape!=(37,37):continue
                bg=max(30.,float(np.percentile(patch,85)))
                if np.mean(patch[core]<bg*.55)>.5:
                    selected[(row,col)]=dict(row=row,col=col,color='black',center=[float(x),float(y)],radius=13.,bbox=[float(x-16),float(y-18),float(x+16),float(y+18)],method='black_occupancy',score=.95)
        for item in self.white_object_candidates(image,self.reference,selected):
            key=(item['row'],item['col'])
            if key not in selected:selected[key]=item
        unresolved=[u for u in unknown if (u['row'],u['col']) not in selected]
        return list(selected.values()),offgrid,unresolved

    def white_object_candidates(self,image,reference,selected):
        """Locate raised bright caps across the image, then associate to a grid.

        A reference-normalized top-hat removes slow lighting variation. Small
        closing removes thin printed grid strokes in both images. A disk filter
        and local peak suppression separate touching caps without requiring any
        printed line to be covered. Black masks are excluded before association.
        """
        gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY).astype(np.float32)
        ref=cv2.cvtColor(reference,cv2.COLOR_BGR2GRAY).astype(np.float32)
        small=np.ones((5,5),np.uint8)
        paper=cv2.morphologyEx(ref,cv2.MORPH_CLOSE,np.ones((9,9),np.uint8))
        ratio=np.clip(gray/np.maximum(ref,30),.4,1.8)
        gain=cv2.medianBlur((ratio*128).astype(np.uint8),45).astype(np.float32)/128
        normalized=gray/np.maximum(gain,.4)
        black=(normalized<paper*.55).astype(np.uint8)
        black=cv2.morphologyEx(black,cv2.MORPH_OPEN,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(5,5)))
        black=cv2.dilate(black,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(19,19)))>0
        clean=cv2.morphologyEx(normalized,cv2.MORPH_CLOSE,small)
        base=cv2.morphologyEx(ref,cv2.MORPH_CLOSE,small)
        cap_kernel=cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(31,31))
        cap=cv2.morphologyEx(clean,cv2.MORPH_TOPHAT,cap_kernel)
        base_cap=cv2.morphologyEx(base,cv2.MORPH_TOPHAT,cap_kernel)
        # Compare against a neighborhood envelope to tolerate subpixel marker
        # warp shifts, rather than interpreting a shifted paper texture as a cap.
        base_cap=cv2.dilate(base_cap,np.ones((5,5),np.uint8))
        evidence=np.maximum(cap-base_cap,0)
        yy,xx=np.mgrid[-6:7,-6:7];disk=(xx*xx+yy*yy<=36).astype(np.float32);disk/=disk.sum()
        score=cv2.filter2D(evidence,-1,disk)
        score[black]=0
        peaks=(score>=cv2.dilate(score,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(25,25)))-1e-5)&(score>6.)
        # Reference envelopes tolerate tiny registration shifts without counting
        # the two sides of an unchanged printed line as a new object.
        lower=cv2.erode(ref,small);upper=cv2.dilate(ref,small)
        novelty=np.maximum(normalized-upper,lower-normalized)>6.
        yy,xx=np.mgrid[:gray.shape[0],:gray.shape[1]]
        objects=[]
        for cy,cx in zip(*np.where(peaks)):
            cx,cy=int(cx),int(cy)
            region=(xx-cx)**2+(yy-cy)**2
            core=region<=8**2;body=region<=14**2
            if np.count_nonzero(novelty&body)<(90 if score[cy,cx]<8. else 35):continue
            if np.mean(black[core])>.32:continue
            if np.mean(evidence[core]>4.)<.40:continue
            objects.append((float(score[cy,cx]),cx,cy))
        # Association happens only after image-wide object localization.
        found=[];used=set(selected)
        for confidence,cx,cy in sorted(objects,reverse=True):
            col=int(round((cx-self.margin)/self.step));row=int(round((cy-self.margin)/self.step))
            if not(0<=row<self.n and 0<=col<self.n) or (row,col) in used:continue
            offset=float(np.hypot(cx-(self.margin+col*self.step),cy-(self.margin+row*self.step)))
            limit=self.step*(.45 if row in (0,self.n-1) or col in (0,self.n-1) else .38)
            if offset>limit:continue
            if any(np.hypot(cx-v['center'][0],cy-v['center'][1])<18 for v in found):continue
            used.add((row,col))
            found.append(dict(row=row,col=col,color='white',center=[float(cx),float(cy)],radius=13.,bbox=[float(cx-16),float(cy-16),float(cx+16),float(cy+16)],method='white_objects_v4',score=min(.99,confidence/25.),object_contrast=confidence,grid_offset=offset))
        return found



class TemporalBoard:
    """Recent white votes tolerate one dropout; removals still need a streak."""
    def __init__(self,n=8):
        self.n=n;self.history=deque(maxlen=7);self.tracks={};self.confirmed={};self.streaks={};self.last_time=None
    def reset_evidence(self):
        self.history.clear();self.streaks.clear()
    def clear(self):
        self.reset_evidence();self.tracks.clear();self.confirmed.clear()
    def update(self,items,offgrid=0,uncertain=False):
        now=time.monotonic();current={(x['row'],x['col']):x for x in items}
        # The existing request_fresh() clears history. Reset consecutive evidence too.
        if not self.history:self.streaks.clear()
        self.history.append({k:v['color'] for k,v in current.items()})
        pending=bool(uncertain or offgrid)
        for key in set(current)|set(self.tracks)|set(self.confirmed)|set(self.streaks):
            observed=current.get(key);color=observed['color'] if observed else 'empty'
            previous,length=self.streaks.get(key,(None,0))
            run=length+1 if previous==color else 1
            self.streaks[key]=(color,run)
            old=self.confirmed.get(key,'empty')
            required=6 if color=='white' else 3 if old=='empty' and color=='black' else 5
            recent_white=(color=='white' and len(self.history)==7 and run>=2 and sum(frame.get(key)=='white' for frame in self.history)>=5)
            if color!=old:
                if run>=required or recent_white:self.confirmed[key]=color
                else:pending=True
            if observed and key in self.tracks and self.tracks[key]['color']!=color and self.confirmed.get(key)!=color:
                self.tracks[key]['held']=True;pending=True
                continue
            if observed:
                if key in self.tracks and self.tracks[key]['color']==color:
                    prev=np.array(self.tracks[key]['bbox']);observed=dict(observed,bbox=(.65*prev+.35*np.array(observed['bbox'])).tolist())
                self.tracks[key]=dict(observed,missed=0,seen_at=now,held=False)
            elif key in self.tracks:
                if key not in self.confirmed:
                    # A rejected provisional candidate must not linger as a display hold.
                    self.tracks.pop(key)
                else:
                    self.tracks[key]['missed']+=1;self.tracks[key]['held']=True
                    if self.tracks[key]['missed']>=5 or now-self.tracks[key]['seen_at']>.5:self.tracks.pop(key)
            if self.confirmed.get(key)=='empty':self.confirmed.pop(key,None)
            if color=='empty' and key not in self.tracks and key not in self.confirmed:self.streaks.pop(key,None)
        if any(t['held'] for t in self.tracks.values()):pending=True
        board=[0]*(self.n*self.n)
        for (r,c),color in self.confirmed.items():board[r*self.n+c]=1 if color=='black' else 2
        display=[dict(t,confirmed=True) for k,t in self.tracks.items() if self.confirmed.get(k)==t['color']]
        return board,display,len(self.history)>=5 and not pending

