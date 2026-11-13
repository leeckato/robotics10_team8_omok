# 오목 ROS 2 패키지 / Ubuntu 24.04 + ROS 2 Jazzy 목표

## 제공 범위와 검증 상태
GUI/비전/게임 제어를 실제 rclpy 노드로 분리한 소스 패키지입니다.
같은 공통 메시지를 사용하는 팀원 연결 템플릿과 모의 노드를 제공합니다.
이 제작 환경에는 ROS 2가 설치돼 있지 않아 colcon 빌드나 DDS/액션 실행은 검증하지 못했습니다.
Python 구문/패키지 메타데이터와 테스트 21개를 확인했습니다. 게임·합성 영상 13개, 가짜 ROS 의존성으로 제어 클래스 로직을 실행한 테스트 8개입니다. 후자는 실제 ROS 통신 시험이 아닙니다.
Ubuntu PC에서 아래 빌드 및 모의 통합 시험을 먼저 수행해야 합니다.
기존 팀 AI/두산 드라이버/손 검출기는 들어 있지 않습니다. mock_peers는 통신 시험만 위한 가짜 상대입니다.

## 구성
src/gomoku_interfaces : 팀 전체가 공유할 msg/srv/action 정의 (ament_cmake).
src/gomoku_system : GUI, 비전, 게임 제어, 관리자 CLI, 모의 상대 (ament_python).
team_templates : 팀원 패키지로 복사해 실제 기능을 연결할 예제.
TEAM_INTERFACES_KO.md : 담당별 통신 규격과 필수 동작.

8×8 교차점, row/col=0~7, 64개 행 우선 배열, 0 빈칸 /1 흑 /2 백 /-1 불확실.
마커 ID와 최초 등록 방향으로 좌표를 유지합니다.
승패는 금수 없음/5개 이상 연속 승리입니다. 기존 AI와 규칙을 맞춰야 합니다.

## 1. PC에 복사하고 환경 준비
압축 안 gomoku_ros2 폴더를 ~/ros2_ws 와 별개 경로에 두거나 src 안의 두 패키지만 기존 ~/ros2_ws/src 에 복사하세요.
아래는 두 패키지를 기존 워크스페이스에 넣은 기준입니다.
중복된 동일 이름 패키지를 다른 하위 폴더에 다시 넣지 마세요.

```bash
source /opt/ros/jazzy/setup.bash
cd ~/ros2_ws
rosdep install --from-paths src --ignore-src -r -y --rosdistro jazzy
```

ROS의 rclpy와 같은 시스템 Python(일반적인 Jazzy Ubuntu 24.04는 Python 3.12)을 사용하세요.
기존 vision 가상환경에 rclpy가 없으면 그대로 사용하지 마세요.
GUI/카메라 의존성은 system-site-packages 가상환경으로 설치하는 방법을 제공합니다:

```bash
/usr/bin/python3 -m venv --system-site-packages ~/gomoku_ros_env
source ~/gomoku_ros_env/bin/activate
python3 -m pip install -r /실제/압축을푼경로/gomoku_ros2/requirements_pc.txt
python3 -c "import rclpy,cv2,PySide6,pyrealsense2; print(cv2.__version__); assert hasattr(cv2.aruco,'ArucoDetector')"
```

venv가 없으면 Ubuntu python3-venv 패키지가 필요합니다. 모의 실행만 할 때는 pyrealsense2 없이 PySide6만으로 GUI를 시험할 수 있고, 비전 테스트는 numpy/OpenCV도 필요합니다.
여러 pip OpenCV 변종을 함께 설치하지 마세요. Ubuntu OpenCV와 pip 버전이 다르면 이 전용 환경에서 실제 import 버전을 확인하세요.

## 2. 빌드
현재 환경에 colcon이 없다면 python3-colcon-common-extensions가 필요합니다.
실행 파일이 ROS를 볼 수 있는 Python으로 생성되도록 아래처럼 Python을 명시합니다.

```bash
source /opt/ros/jazzy/setup.bash
source ~/gomoku_ros_env/bin/activate
cd ~/ros2_ws
python3 "$(command -v colcon)" build --symlink-install --packages-up-to gomoku_system --cmake-args -DPython3_EXECUTABLE="$(command -v python3)"
source install/setup.bash
```

별도 터미널에서도 ROS → 가상환경 → 워크스페이스를 같은 순서로 source 하세요.

## 3. 카메라/로봇 없는 전체 모의 실행
```bash
ros2 launch gomoku_system gomoku.launch.py simulation:=true mock_peers:=true
```

GUI에서 사용자 선후공 선택 → 시작.
사용자 차례: 모의 편집 색 선택 → 중앙 판 클릭 → 검사 요청 → 3초 대기.
정상 착수 후 mock 알고리즘은 첫 빈칸을 선택하고 mock 로봇은 약 1초 후 모의 관측 판을 갱신합니다.
게임 제어가 결과를 재검사한 뒤 GUI에 반영하고 사용자 턴으로 돌아갑니다.
이 가짜 알고리즘은 기존 오목 AI가 아니며 성능 비교 대상도 아닙니다.
두 돌/다른 색/기존 돌 제거/격자 밖 후보를 시험하면 확정 판을 유지하고 경고해야 합니다.
기존 돌은 모의 지우기 후 원위치에 복원하세요. mock 노드와 실제 팀 노드를 동시에 켜면 안 됩니다.

기본 mock_peers:=false이므로 팀원이 없어도 GUI/비전은 켜지지만 로봇 턴에서 연결을 기다립니다.

## 4. 마커 최초 등록과 기준 색 (카메라 독점)
게임 launch를 먼저 종료하세요. 카메라는 한 프로그램만 열어야 합니다.
인쇄물은 src/gomoku_system/tools/PRINT_MARKERS.html. 100%로 인쇄해 흰 여백 포함 부착.
ID0 좌상, ID1 우상, ID2 우하, ID3 좌하, 보드 바깥의 같은 평면에 보드와 함께 고정하세요.

```bash
mkdir -p ~/.config/gomoku
ros2 run gomoku_system calibrate --calibrate --config "$HOME/.config/gomoku/marker_calibration.json"
```
F 고정 → 격자의 좌상/우상/우하/좌하 교차점 클릭 → S 저장.
그 다음 기준 색 등록:
```bash
ros2 run gomoku_system calibrate --config "$HOME/.config/gomoku/marker_calibration.json"
```
실제 흑돌과 백돌을 놓고 B → 흑돌 내부 클릭, W → 백돌 내부 클릭. 색은 즉시 설정에 저장됩니다. Q 종료.
한 번 등록 후에는 평소 이 도구를 실행할 필요 없습니다.
관리자 GUI를 ROS 안에 중복 구현하지 않고 이 별도 등록 창으로 분리했습니다.

## 5. 실제 카메라 실행 (로봇 자동 연결 안 함)
```bash
ros2 launch gomoku_system gomoku.launch.py simulation:=false mock_peers:=false use_hand:=false
```
비전 노드가 카메라를 열고 GUI는 영상 토픽을 구독합니다. app.py를 추가 실행하지 마세요.
빈 판 확인 → 게임 시작 → 사용자 착수 → 수동 검사 요청.
로봇 턴에서는 실제 알고리즘/로봇 노드가 없으면 대기합니다.
use_hand:=false는 수동 검사 모드이며 자동 손 이탈 검출이 아닙니다.
손 담당 노드가 붙으면 use_hand:=true 로 실행하세요. 유효한 손 진입/이탈 신호와 3초 연속 없음이 필요합니다.

GUI 없이 검출만 실행:
```bash
ros2 launch gomoku_system gomoku.launch.py simulation:=false gui:=false
ros2 topic echo /vision/observation
```

## 6. 실제 팀원 연결
각 팀원은 gomoku_interfaces를 같은 버전으로 빌드합니다.
알고리즘: /algorithm/next_move 서비스 서버.
로봇: /robot/place_stone 액션 서버 + /robot/status 발행.
손: /vision/image_raw 구독 → /vision/hand_state 발행.
GUI/비전/게임 제어는 이 패키지 launch로 실행. 팀원 노드는 각자 패키지에서 실행하거나 최종 launch에 추가.
두산 드라이버는 로봇 담당자가 기존에 검증한 명령으로 별도 실행합니다. 모델/IP/드라이버 버전을 임의 지정하지 않았습니다.
다른 PC로 나눌 경우 동일 ROS_DOMAIN_ID와 DDS 네트워크/시간 동기화가 필요합니다. 우선 같은 PC에서 통합하세요.

## 7. 동작 보류와 복구
- 유효하지 않은 관측/마커 누락/오래된 영상은 착수 확정에 사용하지 않습니다.
- 이전 게임/턴/요청 응답은 거부합니다.
- 동작 요청 후 120초, 알고리즘/요청 응답 15초, 판 확인 8초를 초기 시간 제한으로 사용합니다.
- 오류 시 자동 재착수하지 않습니다. 실제 판/로봇 상태를 확인해야 합니다.
- 동작 여부가 불명확한 액션 핸들이 남아 있으면 게임 종료도 거부합니다. 로봇 담당이 실제 상태 확인 후 노드를 재기동해 복구하세요.
- ERROR에서 로봇이 대기 상태로 확인되고 미완료 핸들이 없으면 게임 종료 → 빈 판 → 새 게임.
- 보드 좌표 revision이 바뀌면 로봇 좌표 재확인이 필요합니다. 실제 로봇 노드는 관측 revision을 무조건 복사하면 안 됩니다.
- revision은 프로세스 실행 내 번호입니다. 재기동 시 초기화되므로 로봇 좌표 검증도 다시 수행해야 합니다.

## 8. 검출의 현실적 제한
실제 카메라/돌은 아직 미검증입니다. 원 후보 미검출은 진짜 빈칸과 완벽히 구분되지 않습니다.
연속 5프레임 일치는 일관성 검사이며 검출 정확도 보장은 아닙니다.
격자 바깥 약 0.6칸 여백까지만 검사합니다. 판 전체 공간의 모든 물체를 찾는 기능은 아닙니다.
마커 하나 누락/큰 보드 이동 중 검사 보류. 심한 원근/반사/흰 바닥과 백돌 경계 소실/돌 겹침은 놓칠 수 있습니다.
렌즈 왜곡 보정은 없습니다. 손 검출은 게임 트리거용이며 실제 로봇 안전 정지를 대신하지 않습니다.

## 9. 확인 명령과 테스트
```bash
ros2 node list
ros2 topic list -t
ros2 service list -t
ros2 action list -t
ros2 interface show gomoku_interfaces/action/PlaceStone
ros2 topic echo /game/state
```

ROS 없는 순수 로직 테스트(소스 경로에서):
```bash
PYTHONPATH=src/gomoku_system python3 -m unittest discover -s src/gomoku_system/tests -v
```
실제 빌드/실행 확인 후 전체 ROS 통합 검증까지 완료된 것으로 판단하세요.
