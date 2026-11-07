"""
오목 로봇 GUI 실행

    python main.py
    python main.py --config 다른설정.yaml
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import cv2  # noqa: E402,F401  (PySide6 보다 먼저 import)

# opencv-python 이 자기 Qt 플러그인 경로를 설정해 PySide6 와 충돌하는 문제(특히 리눅스) 방지
os.environ.pop('QT_QPA_PLATFORM_PLUGIN_PATH', None)

from PySide6.QtGui import QIcon  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from gui.main_window import MainWindow  # noqa: E402
from utils.config import DEFAULT_PATH, load_config  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', default=DEFAULT_PATH)
    a = ap.parse_args()

    app = QApplication(sys.argv)
    res = os.path.join(ROOT, 'gui', 'resources')
    with open(os.path.join(res, 'style.qss'), encoding='utf-8') as f:
        app.setStyleSheet(f.read())
    app.setWindowIcon(QIcon(os.path.join(res, 'icons', 'app.svg')))

    win = MainWindow(load_config(a.config))
    win.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
