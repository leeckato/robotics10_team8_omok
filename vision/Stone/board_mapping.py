
import cv2
import numpy as np
import pyrealsense2 as rs
import json

# 격자 교차점 개수 (행, 열)
N = 8
points = []

pipeline = rs.pipeline()
config = rs.config()
config.enable_stream(
    rs.stream.color, 640, 480,
    rs.format.bgr8, 30
)

def mouse_callback(event, x, y, flags, param):
    if event == cv2.EVENT_LBUTTONDOWN and len(points) < 4:
        points.append([x, y])
        print(f"모서리 {len(points)}: ({x}, {y})")

try:
    pipeline.start(config)

    # 초기 자동 노출이 안정되도록 프레임 수신
    for _ in range(30):
        pipeline.wait_for_frames()

    frames = pipeline.wait_for_frames()
    color_frame = frames.get_color_frame()
    image = np.asanyarray(color_frame.get_data()).copy()

    cv2.namedWindow("Board Mapping")
    cv2.setMouseCallback("Board Mapping", mouse_callback)

    print("격자 바깥쪽 4개 교차점을 클릭하세요.")
    print("순서: 좌상 -> 우상 -> 우하 -> 좌하")
    print("R: 초기화 / S: 저장 / Q: 종료")

    while True:
        display = image.copy()

        for i, (x, y) in enumerate(points):
            cv2.circle(display, (x, y), 6, (0, 0, 255), -1)
            cv2.putText(
                display, str(i + 1), (x + 8, y - 8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                (0, 0, 255), 2
            )

        grid = None

        if len(points) == 4:
            src = np.float32(points)
            dst = np.float32([
                [0, 0],
                [N - 1, 0],
                [N - 1, N - 1],
                [0, N - 1]
            ])

            # 격자 좌표 -> 이미지 픽셀 좌표
            H = cv2.getPerspectiveTransform(dst, src)

            grid = []
            for row in range(N):
                for col in range(N):
                    p = np.array(
                        [[[col, row]]], dtype=np.float32
                    )
                    pixel = cv2.perspectiveTransform(p, H)
                    x, y = pixel[0, 0]
                    x, y = int(round(x)), int(round(y))

                    grid.append({
                        "row": row, "col": col,
                        "x": x, "y": y
                    })

                    cv2.circle(
                        display, (x, y), 3,
                        (0, 255, 0), -1
                    )
                    cv2.putText(
                        display, f"{row},{col}",
                        (x + 3, y - 4),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.28, (255, 0, 0), 1
                    )

        cv2.imshow("Board Mapping", display)
        key = cv2.waitKey(30) & 0xFF

        if key == ord('r'):
            points.clear()

        elif key == ord('s') and grid is not None:
            with open("board_coordinates.json", "w") as f:
                json.dump({
                    "grid_size": N,
                    "image_size": [640, 480],
                    "corners": points,
                    "coordinates": grid
                }, f, indent=2)
            print("board_coordinates.json 저장 완료")

        elif key == ord('q'):
            break

finally:
    pipeline.stop()
    cv2.destroyAllWindows()
