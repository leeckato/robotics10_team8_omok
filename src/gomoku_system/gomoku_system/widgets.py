from PySide6.QtCore import Qt,Signal
from PySide6.QtGui import QColor,QPainter,QPen,QPixmap,QImage
from PySide6.QtWidgets import QWidget,QLabel
class BoardWidget(QWidget):
    clicked=Signal(int,int)
    def __init__(self,n=8):
        super().__init__();self.n=n;self.board=[0]*(n*n);self.last=None;self.preview=None;self.setMinimumSize(360,360)
    def geometry_grid(self):
        size=min(self.width(),self.height())-64;return (self.width()-size)/2,(self.height()-size)/2,size/(self.n-1)
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing);p.fillRect(self.rect(),QColor('#dbc49b'))
        ox,oy,s=self.geometry_grid();p.setPen(QPen(QColor('#6c543a'),1))
        for i in range(self.n):
            p.drawLine(round(ox),round(oy+i*s),round(ox+(self.n-1)*s),round(oy+i*s))
            p.drawLine(round(ox+i*s),round(oy),round(ox+i*s),round(oy+(self.n-1)*s))
            p.drawText(round(ox-22),round(oy+i*s+5),str(i));p.drawText(round(ox+i*s-4),round(oy-15),str(i))
        for i,value in enumerate(self.board):
            if not value:continue
            r,c=divmod(i,self.n);x=ox+c*s;y=oy+r*s;radius=s*.37
            p.setPen(QPen(QColor('#21262e'),1));p.setBrush(QColor('#15181d') if value==1 else QColor('#f7f8fa'))
            p.drawEllipse(round(x-radius),round(y-radius),round(radius*2),round(radius*2))
            if self.last==(r,c):
                p.setPen(QPen(QColor('#19b9a5'),3));p.setBrush(Qt.NoBrush);p.drawEllipse(round(x-5),round(y-5),10,10)
    def mousePressEvent(self,event):
        ox,oy,s=self.geometry_grid();c=round((event.position().x()-ox)/s);r=round((event.position().y()-oy)/s)
        if 0<=r<self.n and 0<=c<self.n:self.clicked.emit(r,c)

class CameraLabel(QLabel):
    picked=Signal(int,int)
    def __init__(self):super().__init__('카메라 연결 전');self.setAlignment(Qt.AlignCenter);self.setMinimumSize(320,240);self.source_size=None;self.render_size=None
    def set_frame(self,bgr):
        import cv2
        rgb=cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB);h,w=rgb.shape[:2];self.source_size=(w,h)
        im=QImage(rgb.data,w,h,rgb.strides[0],QImage.Format_RGB888).copy()
        pm=QPixmap.fromImage(im).scaled(self.size(),Qt.KeepAspectRatio,Qt.SmoothTransformation)
        self.render_size=(pm.width(),pm.height());self.setPixmap(pm)
    def mousePressEvent(self,event):
        if not self.render_size:return
        rw,rh=self.render_size;ox=(self.width()-rw)/2;oy=(self.height()-rh)/2
        x=event.position().x()-ox;y=event.position().y()-oy
        if 0<=x<rw and 0<=y<rh:self.picked.emit(int(x*self.source_size[0]/rw),int(y*self.source_size[1]/rh))
