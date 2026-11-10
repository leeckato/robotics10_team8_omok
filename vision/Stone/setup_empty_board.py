"""빈 판 기준을 미리 저장합니다. 인식 프로그램과 동시에 실행하지 마세요."""
from pathlib import Path
import hashlib
import json
import os

import cv2
import numpy as np
import pyrealsense2 as rs

ROOT = Path(__file__).resolve().parent
CAPTURE_FRAMES = 30


def main():
    board = json.loads((ROOT / 'board_coordinates.json').read_text())
    width, height = board['image_size']
    board_hash = hashlib.sha256(
        json.dumps(board, sort_keys=True).encode('utf-8')
    ).hexdigest()
    pipeline, config = rs.pipeline(), rs.config()
    config.enable_stream(rs.stream.color, width, height, rs.format.bgr8, 30)
    started = False
    samples = []
    capturing = False
    try:
        pipeline.start(config)
        started = True
        for _ in range(60):
            pipeline.wait_for_frames()
        print('판에서 모든 돌과 손을 치우세요.')
        print('S: 30프레임 촬영 후 저장 / Q: 종료')
        print('촬영 중에는 카메라와 판을 움직이지 마세요.')
        while True:
            color = pipeline.wait_for_frames().get_color_frame()
            if not color:
                continue
            image = np.asanyarray(color.get_data()).copy()
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            if capturing:
                samples.append(gray.copy())
                if len(samples) >= CAPTURE_FRAMES:
                    reference = np.median(np.stack(samples), axis=0).astype(np.uint8)
                    target = ROOT / 'empty_board_reference.npz'
                    temporary = ROOT / 'empty_board_reference.tmp.npz'
                    with temporary.open('wb') as file:
                        np.savez_compressed(file, gray=reference, board_hash=np.array(board_hash))
                    os.replace(temporary, target)
                    cv2.imwrite(str(ROOT / 'empty_board_reference.png'), reference)
                    print('저장 완료:', target)
                    print('PNG에 돌과 손이 없는지 확인하세요. Q로 종료 후 stone_detection.py 실행.')
                    samples.clear()
                    capturing = False
            display = image.copy()
            for p in board['coordinates']:
                cv2.circle(display, (p['x'], p['y']), 3, (0, 255, 0), -1)
            message = (f'Capturing {len(samples)}/{CAPTURE_FRAMES}' if capturing
                       else 'Clear board | S: save reference | Q: quit')
            cv2.putText(display, message, (8, 24), cv2.FONT_HERSHEY_SIMPLEX,
                        .45, (0, 0, 255), 1)
            cv2.imshow('Empty Board Setup', display)
            key = cv2.waitKey(1) & 0xff
            if key == ord('q'):
                break
            if key == ord('s') and not capturing:
                samples.clear()
                capturing = True
    except KeyboardInterrupt:
        pass
    finally:
        if started:
            pipeline.stop()
        cv2.destroyAllWindows()


if __name__ == '__main__':
    main()
