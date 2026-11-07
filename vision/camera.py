"""카메라 열기/프레임 읽기

source 가 숫자면 실제 카메라, 문자열(파일 경로)이면 그 이미지를 계속 돌려주는
가짜 카메라로 동작합니다. 카메라 없이 GUI/로직을 테스트할 때 유용합니다.
"""
import os

import cv2

from utils.config import project_path


class Camera:
    def __init__(self, source=0, width=1280, height=720):
        self.source = source
        self._image = None
        self._cap = None

        if isinstance(source, str) and not source.isdigit():
            path = project_path(source)
            self._image = cv2.imread(path)
            if self._image is None:
                raise RuntimeError(f'이미지를 열 수 없음: {path}')
        else:
            idx = int(source)
            # 윈도우에서는 CAP_DSHOW 가 여는 속도가 빠름
            backend = cv2.CAP_DSHOW if os.name == 'nt' else cv2.CAP_ANY
            self._cap = cv2.VideoCapture(idx, backend)
            if not self._cap.isOpened():
                raise RuntimeError(f'카메라 {idx}번을 열 수 없음')
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

    @classmethod
    def from_config(cls, cfg):
        c = cfg['camera']
        return cls(c['source'], c.get('width', 1280), c.get('height', 720))

    @property
    def is_static(self):
        return self._image is not None

    def read(self):
        """BGR numpy 배열 (H, W, 3) 반환. 실패하면 None"""
        if self._image is not None:
            return self._image.copy()
        ok, frame = self._cap.read()
        return frame if ok else None

    def release(self):
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.release()
