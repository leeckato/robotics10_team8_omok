# team_hand — 손 감지 노드

`gomoku_ros2` 팀원 연결 규격 v0.1 "3. 손 감지 담당"을 구현한 ROS 2 패키지입니다.

```
gomoku_vision (카메라 독점)
   │  /vision/image_raw  sensor_msgs/Image bgr8, sensor_data QoS, 10Hz
   ▼
team_hand/hand_node ──► /vision/hand_state  gomoku_interfaces/HandState, 15Hz
                           stamp        = 원본 영상 header.stamp (그대로)
                           valid        = 정상 검사 여부
                           hand_present = 판 영역에 손이 있으면 true
   ▼
gomoku_controller (use_hand:=true) : 손 진입 → 이탈 → 3초 없음 → 자동 검사
```

## 규격 대응

| 규격 | 구현 |
| --- | --- |
| `/vision/image_raw` 구독, bgr8, `qos_profile_sensor_data` | 그대로 (rgb8 도 변환) |
| 카메라 재오픈 금지 | 토픽만 구독 |
| `/vision/hand_state` 10~30Hz | 15Hz (`publish_hz`) |
| 원본 영상 0.5초 이상 오래됨 / 검사 실패 → `valid=false` | 영상 없음, 보정 파일 없음, 마커 오래 안 보임, 영상 크기 불일치, 예외 모두 `valid=false` |
| 원본 영상 시각을 stamp 에 보존 | 영상 `header.stamp` 복사. 새 영상이 없으면 같은 stamp 로 재발행 → 0.5초 지나면 valid=false |
| 판 영역으로 한정 | 비전 노드와 **같은 보정 파일 + ArUco 마커**로 판 위치를 구해 격자 바깥 0.6칸까지만 검사 |
| 3초 타이머는 게임 제어 담당 | 손 노드는 손 상태만. "손 없음" 확정 대기는 0.3초로 짧게 (`clear_seconds`) |

## 판정 방식

한 영상에서 아래 중 하나라도 해당하면 '감지', 2번 연속이면 손 있음, 0.3초 동안 감지가 없으면 손 없음.

| 방법 | 내용 |
| --- | --- |
| 손 모델 | MediaPipe 손바닥 검출 모델(`models/palm_detection_full.tflite`)을 **OpenCV 로 실행** (MediaPipe 설치 불필요) |
| 기준 대비 변화 | 손 없는 기준 화면 대비 판 영역의 2.5% 이상 변화 (그림자 제외). 돌 하나는 약 0.6% 라 손이 빠진 뒤 돌만 남으면 손 없음 |
| 움직임 | 직전 영상 대비 판 영역의 0.5% 이상 움직임 (그림자 제외) |

`method: model` 이면 손 모델만 사용 (가위 등 물체 무시). 기본 `both` 는 판 위에 무엇이든 올라오면 손 있음 (로봇 팔 포함).

### 검사 영역 (`roi_mode`)

| roi_mode | 동작 |
| --- | --- |
| `marker` (기본) | 비전 노드와 같은 `marker_calibration.json` 과 ArUco 4개(ID 0~3)로 매 영상 판 위치 계산 (`transform_grid` 와 같은 조건). 손이 마커를 가려도 마지막 위치로 계속 검사, `marker_lost_sec`(5초) 넘게 안 보이면 valid=false. 3px 이상 움직이면 영역 갱신 |
| `grid` | 흰 종이 그리드를 영상에서 직접 검출 (마커 없는 판) |
| `full` | 영상 전체 (규격 문서의 "보수적 처리") |
| `polygon` | `roi_polygon: "x1,y1 x2,y2 x3,y3 x4,y4"` 원본 픽셀 |

## 설치 / 빌드

`gomoku_ros2/README_ROBOT_KO.md` 의 설치·빌드를 따르세요 (gomoku_ros2 폴더에서 패키지 5개를 함께 빌드).
OpenCV 는 4.8 이상이어야 손 모델을 읽습니다:

```bash
python3 -c "import cv2; print(cv2.__version__, hasattr(cv2.dnn,'readNetFromTFLite'), hasattr(cv2,'aruco'))"
```

## 실행

마커 등록(`ros2 run gomoku_system calibrate --calibrate ...`)이 끝나 보정 파일이 있어야 합니다.

```bash
# 터미널 1: 게임 (실제 카메라, 손 사용)
ros2 launch gomoku_system gomoku.launch.py simulation:=false mock_peers:=false use_hand:=true
# 터미널 2: 손 노드 (보정 파일 기본값은 gomoku.launch.py 와 같은 ~/.config/gomoku/marker_calibration.json)
ros2 launch team_hand hand.launch.py
ros2 launch team_hand hand.launch.py calibration:=/다른/경로/marker_calibration.json

# 판정 화면 (/hand/debug_image 2Hz)
ros2 launch team_hand hand.launch.py debug_image:=true
ros2 run rqt_image_view rqt_image_view /hand/debug_image

# 확인
ros2 topic echo /vision/hand_state
ros2 topic hz /vision/hand_state
```

주의
- `simulation:=true` 에서는 비전 노드가 `/vision/image_raw` 를 내지 않아 손 노드는 계속 valid=false 입니다.
- `mock_peers:=true` 는 가짜 `HandState` 를 직접 발행합니다. **손 노드와 동시에 켜지 마세요** (발행자 두 개).

## 카메라 없이 시험

mp4 를 `/vision/image_raw` 로 내보내는 시험용 노드 (실제 비전 노드와 동시에 켜지 마세요). 영상 크기는 보정 파일의 `image_size` 와 같아야 합니다.

```bash
ros2 run team_hand video_pub --ros-args -p video:=/경로/test.mp4 -p loop:=true
ros2 launch team_hand hand.launch.py calibration:=/경로/marker_calibration.json
```

ROS 없이 판정 로직만: `python3 -m pytest test/ -v` (패키지 폴더에서, 14개)

## 처리 구조

- 영상 콜백은 직렬화된 바이트만 보관 (`raw=True`), 검사 스레드가 최신 영상만 풀어서 검사 → 검사가 느려도 수신/발행이 밀리지 않음
- 발행 타이머는 마지막 결과를 15Hz 로 발행, 결과의 원본 영상이 0.5초보다 오래되면 valid=false
- `cv_threads: 1` (OpenCV 스레드 제한, 같은 PC 의 비전 노드 몫 보장), `max_process_hz: 15`

## 확인된 것 / 아닌 것

- Ubuntu 24.04 + ROS 2 Jazzy(conda RoboStack) + Python 3.12 에서, 덤프의 실제 `gomoku_interfaces` 와 `gomoku_system`
  (`vision_node` 모의 + `game_controller use_hand:=true`) 를 함께 띄워 확인:
  게임 시작 수락 → 손 진입(present=true) → 이탈 → **3.0초 뒤 controller 가 INSPECT_HUMAN 진입**, 영상 끊기면 0.5초 뒤 valid=false.
  (영상은 640x480 합성 마커 판 + 합성 손, 10Hz)
- 판정 로직 시험 14개 통과: OpenCV 5.0 과 opencv-contrib 4.14 모두.
- 검사 시간 (1코어, 1280x720 시험 영상 기준): `both` 중앙값 약 50ms, `model` 약 37ms.
- **시험 안 한 것**: 실제 RealSense 영상, 실제 손, 실제 로봇 팔, apt 로 설치한 ROS. 실제 카메라에서는 `palm_score` 조정이 필요할 수 있습니다.

## 알아둘 점

- 로봇 팔이 판 위에 오면 `both` 에서 손 있음입니다. 게임 제어는 WAIT_ROBOT / WAIT_VERIFY 에서 손 없음을 요구하므로,
  로봇 대기 위치가 판 영역(격자 바깥 0.6칸) 밖이어야 합니다.
- 게임 제어는 `valid=false` 한 번에도 3초 대기를 처음부터 다시 셉니다. 마커가 5초 넘게 가려지면 valid=false 가 됩니다.
- 손 감지는 게임 진행용이며 로봇 안전 센서가 아닙니다.
- `models/palm_detection_full.tflite` 는 Google MediaPipe 모델(Apache 2.0)입니다. `models/NOTICE.md` 참고.
