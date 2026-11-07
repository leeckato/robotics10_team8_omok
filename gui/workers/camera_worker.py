"""카메라를 계속 읽는 스레드. GUI 미리보기와 게임 스레드에 최신 프레임 제공"""
import threading
import time

from PySide6.QtCore import QThread, Signal

from vision.camera import Camera


class CameraWorker(QThread):
    frame_ready = Signal(object)     # np.ndarray (BGR) - 미리보기용 (preview_fps 로 제한)
    error = Signal(str)

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self._lock = threading.Lock()
        self._latest = None
        self._running = False

    def run(self):
        try:
            cam = Camera.from_config(self.cfg)
        except Exception as e:
            self.error.emit(f'카메라 열기 실패: {e}')
            return

        self._running = True
        interval = 1.0 / max(1, self.cfg['camera'].get('preview_fps', 15))
        last_emit = 0.0
        while self._running:
            frame = cam.read()
            if frame is None:
                self.msleep(30)
                continue
            with self._lock:
                self._latest = frame
            now = time.time()
            if now - last_emit >= interval:
                last_emit = now
                self.frame_ready.emit(frame)
            if cam.is_static:            # 이미지 파일 모드: 너무 빨리 돌지 않게
                self.msleep(33)
        cam.release()

    def latest_frame(self):
        with self._lock:
            return None if self._latest is None else self._latest.copy()

    def stop(self):
        self._running = False
        self.wait(2000)
