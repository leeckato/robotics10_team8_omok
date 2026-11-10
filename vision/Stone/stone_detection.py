
import cv2
import json
from pathlib import Path
import hashlib
import numpy as np
import pyrealsense2 as rs
from white_core import is_white_stone, confirm_white

with open("board_coordinates.json") as f:
    board = json.load(f)

coords = board["coordinates"]
width, height = board["image_size"]

pipeline = rs.pipeline()
config = rs.config()
config.enable_stream(
    rs.stream.color, width, height,
    rs.format.bgr8, 30
)

started = False
last_detected = None
last_white_detected = None

white_counts = {}

REFERENCE_PATH = Path(__file__).resolve().parent / "empty_board_reference.npz"
reference_gray = None
board_hash = hashlib.sha256(
    json.dumps(board, sort_keys=True).encode("utf-8")
).hexdigest()
try:
    with np.load(REFERENCE_PATH, allow_pickle=False) as data:
        candidate = data["gray"]
        if (candidate.shape != (height, width) or candidate.dtype != np.uint8
                or str(data["board_hash"].item()) != board_hash):
            raise ValueError("기준 영상과 현재 매핑이 다릅니다.")
        reference_gray = candidate.copy()
    print("저장된 빈 판 기준 로드 완료 — 격자선 가림 방식으로 백돌 검사")
except (OSError, ValueError, KeyError) as exc:
    print(f"빈 판 기준을 사용할 수 없습니다: {exc}")
    print("백돌 검출은 비활성화됩니다. setup_empty_board.py를 실행하세요.")


try:
    pipeline.start(config)
    started = True

    print("검은 돌 인식 시작")
    print("Q: 종료 / S: 진단 영상 저장")

    while True:
        frames = pipeline.wait_for_frames()
        color = frames.get_color_frame()
        if not color:
            continue

        image = np.asanyarray(color.get_data()).copy()
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        detections = []
        white_detections = []

        for p in coords:
            row, col = p["row"], p["col"]
            x, y = p["x"], p["y"]

            # 교차점 주변 7픽셀 반경 검사
            radius = 7
            if (x - radius < 0 or y - radius < 0 or
                x + radius >= width or y + radius >= height):
                continue

            patch = gray[
                y-radius:y+radius+1,
                x-radius:x+radius+1
            ]

            reference_patch = (
                reference_gray[y-radius:y+radius+1, x-radius:x+radius+1]
                if reference_gray is not None else None
            )

            # 백돌만 연속 프레임 확인. 흑돌 조건은 기존과 동일합니다.
            white_confirmed = confirm_white(
                white_counts, (row, col), is_white_stone(patch, reference_patch)
            )

            # 어두운 픽셀 비율
            dark_ratio = np.mean(patch < 75)

            if dark_ratio > 0.55:
                detections.append((row, col))
                cv2.circle(
                    image, (x, y), 10,
                    (0, 0, 255), 2
                )
                cv2.putText(
                    image, f"BLACK {row},{col}",
                    (x+10, y-10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.4, (0, 0, 255), 1
                )
            elif white_confirmed:
                # 추가: 기존 흑돌 조건에 해당하지 않는 경우에만 백돌 검사
                white_detections.append((row, col))
                cv2.circle(
                    image, (x, y), 10,
                    (255, 0, 0), 2
                )
                cv2.putText(
                    image, f"WHITE {row},{col}",
                    (x+10, y-10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.4, (255, 0, 0), 1
                )
            else:
                cv2.circle(
                    image, (x, y), 3,
                    (0, 255, 0), -1
                )

        detected = tuple(sorted(detections))

        if detected != last_detected:
            print("Detected black stones:", detected)
            last_detected = detected

        # 추가: 백돌 위치가 바뀌었을 때만 출력
        white_detected = tuple(sorted(white_detections))
        if white_detected != last_white_detected:
            print("Detected white stones:", white_detected)
            last_white_detected = white_detected

        cv2.imshow("Stone Detection", image)

        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        if key == ord("s"):
            output = Path(__file__).resolve().parent
            cv2.imwrite(str(output / "diagnostic_current.png"), gray)
            if reference_gray is not None:
                cv2.imwrite(str(output / "diagnostic_reference.png"), reference_gray)
            cv2.imwrite(str(output / "diagnostic_display.png"), image)
            print("진단 영상 저장: diagnostic_current/reference/display.png")

except KeyboardInterrupt:
    pass

finally:
    if started:
        pipeline.stop()
    cv2.destroyAllWindows()
