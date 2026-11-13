# 오목 로봇 전체 — AI · 로봇 · 손 감지 연동

**`gomoku_ros2/` 폴더 자체가 ROS 2 워크스페이스입니다.** 풀고 이 폴더에서 빌드하면 됩니다.

```
gomoku_ros2/                  ← 워크스페이스 (여기서 colcon build)
├── src/
│   ├── gomoku_interfaces/    팀 공용 msg/srv/action (변경 없음)
│   ├── gomoku_system/        팀 비전 · 게임 제어 · GUI (gui.py, game.py 패치 적용됨)
│   ├── team_algorithm/       /algorithm/next_move — AlphaZero 8x8 5목 (모델 포함)
│   ├── team_robot/           /robot/place_stone, /robot/status — omok_pick_place.py 동작
│   └── team_hand/            /vision/hand_state — 손 감지
├── patches/                  gomoku_system 에 적용한 변경 (gui.diff, game.diff)
├── team_templates/           팀 원본 템플릿 (참고용)
├── README_KO.md              팀 원본 README (비전 · 게임 제어 · 보정)
├── TEAM_INTERFACES_KO.md     팀 연결 규격
├── ACCEPTANCE_CHECKLIST_KO.md
└── requirements_pc.txt       opencv-contrib-python 4.8 이상으로 수정
```

> 예전에 `gomoku_system`, `gomoku_interfaces` 를 `~/ros2_ws/src` 에 복사해 두었다면 그 복사본은 지우거나,
> 이 워크스페이스를 **마지막에 source** 하세요. 같은 이름 패키지가 두 워크스페이스에 있으면 나중에 source 한 쪽이 쓰입니다.

## 1. 설치

```bash
unzip gomoku_ros2.zip -d ~/            # ~/gomoku_ros2
source /opt/ros/jazzy/setup.bash

# 파이썬 환경 (팀 README 1장과 같음)
/usr/bin/python3 -m venv --system-site-packages ~/gomoku_ros_env
source ~/gomoku_ros_env/bin/activate
python3 -m pip install -r ~/gomoku_ros2/requirements_pc.txt
python3 -c "import cv2; print(cv2.__version__, hasattr(cv2.dnn,'readNetFromTFLite'), hasattr(cv2.aruco,'ArucoDetector'))"
#   -> 4.8 이상, True, True
```

## 2. 빌드

`team_robot` 은 두산 `dsr_msgs2` 를 씁니다. **두산 드라이버 워크스페이스를 먼저 source** 하세요 (board_control 스크립트를 실행하던 환경).

```bash
source /opt/ros/jazzy/setup.bash
source ~/ros2_ws/install/setup.bash          # 두산 드라이버(dsr_msgs2)가 있는 워크스페이스
source ~/gomoku_ros_env/bin/activate
cd ~/gomoku_ros2
python3 "$(command -v colcon)" build --symlink-install \
    --cmake-args -DPython3_EXECUTABLE="$(command -v python3)"
source install/setup.bash
```

새 터미널마다 같은 순서(ROS → 두산 워크스페이스 → 가상환경 → `~/gomoku_ros2/install/setup.bash`)로 source 합니다.

빌드 확인:
```bash
ros2 pkg list | grep -E "gomoku|team_"      # gomoku_interfaces gomoku_system team_algorithm team_hand team_robot
ros2 interface show dsr_msgs2/srv/MoveLine   # 두산 메시지가 보이는지
```

## 3. 실행

```bash
# 터미널 1: 두산 드라이버 bringup (지금까지 쓰던 명령 그대로)
# 터미널 2: 그리퍼 노드 (gripper_mode:=topic 일 때만, gripper_node mode:=real)

# 터미널 3: 전체 (비전 + 게임 제어 + GUI + 손 + AI + 로봇)
ros2 launch team_robot omok_game.launch.py                    # 로봇 안 움직임 (dry) — 먼저 이것으로 시험
ros2 launch team_robot omok_game.launch.py robot_mode:=real   # 실제 로봇
```

| 인자 | 기본 | 설명 |
| --- | --- | --- |
| `robot_mode` | `dry` | `dry`: 로봇 차례에 로그로 칸을 알려 주고 사람이 대신 놓음 (10초 대기) / `real`: 실제 이동 |
| `gripper_mode` | `drl` | `drl`: `~/ros2_ws/gripper/gripper_drl.py open\|close <값>` (omok_pick_place.py 와 같음) / `topic`: `/dsr01/gripper/position_cmd` / `sim` / `none` |
| `grid_json` | `~/ros2_ws/board_control/grid_robot_coordinates.json` | 로봇 격자 좌표 |
| `use_hand` | `true` | `false` 면 GUI [판 검사 요청 · 3초 대기] 로 사용자 착수 확인 |
| `calibration` | `~/.config/gomoku/marker_calibration.json` | 비전/손 공용 마커 보정 파일 (팀 README 4장의 calibrate 로 생성) |
| `n_playout` | `400` | AI 탐색 횟수 |
| `gui` | `true` | |

마커 보정(`ros2 run gomoku_system calibrate ...`)은 팀 `README_KO.md` 4장대로 먼저 해 두어야 비전과 손 감지가 동작합니다.

## 게임 흐름

GUI 에서 돌 색을 고르고 **[게임 시작]**:

- **로봇 선공** (사용자 후공·백): AI 계산 → 로봇이 대기 위치로 → 돌 집기 → 놓기 → 복귀 → 비전이 그 칸의 돌 확인 → 사용자 차례
- **사용자 선공** (사용자 선공·흑): 사용자가 돌을 놓음 → 손이 판에서 빠지고 3초 → 비전 확인 → AI → 로봇 착수 → …
- 로봇은 **로봇 차례에만** 움직이고, 판 위에 손이 보이면 출발하지 않습니다.
- 5목이 되면 GUI 에 "사용자 승리 / 로봇 승리".

GUI 에 추가된 것: 로봇 상태 줄, **[로봇 대기 위치로]**, **[로봇 오류 해제]**.

## 로봇 동작 (`omok_pick_place.py` 와 같음)

| 단계 | 동작 |
| --- | --- |
| PICKING | 공급 위 (273.4, -81.6, 193.3) → 집기 Z 140 → 그리퍼 630 → 공급 위 |
| MOVING | 목표 칸 위 (격자 Z + 30) |
| PLACING | 놓기 Z 145 → 그리퍼 550 → 상승 |
| RETURNING | 공급 위(대기 위치) → 그리퍼 450 → TCP 실측으로 대기 위치 확인 후 성공 |

자세 `[4.9588, 179.5272, 94.7379]`, 직선 90/54, 관절 36, 준비 자세 `[0,0,90,0,90,90]`.
값은 `src/team_robot/config/robot_params.yaml` 에서 바꿉니다 (`--symlink-install` 빌드면 다시 빌드할 필요 없음, 노드만 재시작).
이동마다 `get_current_posx` 로 실측해 3mm 넘게 벗어나면 그 자리에서 멈추고 실패를 알립니다.

## 오류가 났을 때

1. GUI "확인 필요" + 로봇 상태 줄에 이유 → 로봇과 돌(그리퍼에 돌이 남았는지) 직접 확인
2. **[로봇 오류 해제]** → **[로봇 대기 위치로]**
3. **[게임 종료]** → 판 비우고 새 게임 (게임 제어는 자동 재시도하지 않음)

## 팀 코드에 적용한 수정 (`patches/`)

- `game.py` (버그 수정): 5목이 완성되면 `game_controller` 가 `Assertion 'PyLong_Check(field)' failed` 로 종료되던 문제.
  ROS `int8[64]` 보드 값이 `numpy.int8` 이라 `GameState.winner` 에 그대로 들어가서 생김. 보드를 `int` 로 바꾸는 2줄.
- `gui.py`: 로봇 상태 줄과 버튼 2개 추가.
- `requirements_pc.txt`: `opencv-contrib-python>=4.8` (4.7 은 손 모델을 못 읽음).

## 시험

```bash
cd ~/gomoku_ros2/src/team_algorithm && python3 -m pytest test/ -q   # 6개
cd ~/gomoku_ros2/src/team_robot && python3 -m pytest test/ -q       # 6개
cd ~/gomoku_ros2/src/team_hand && python3 -m pytest test/ -q        # 14개
```

이 zip 을 빈 폴더에 풀어 Ubuntu 24.04 + ROS 2 Jazzy 에서 빌드하고, 가짜 두산 드라이버와 팀 비전(모의)·게임 제어로 게임을 끝까지 진행해 확인했습니다.
실제 두산 E0509 · 그리퍼 · RealSense 로는 시험하지 않았습니다. 연결 순서와 확인 항목은 "오목 로봇 연결·시험 체크리스트" 문서를 따르세요.

## AI 모델

`src/team_algorithm/alphazero/` 에 [AlphaZero_Gomoku](https://github.com/junxiaosong/AlphaZero_Gomoku) (MIT, `LICENSE`)의
`best_policy_8_8_5.model` 과 실행에 필요한 파일 3개가 들어 있습니다. 다른 복사본을 쓰려면 `alphazero_path` 파라미터에 경로를 넣으세요.
