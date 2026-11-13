# 팀원 전달용 ROS 2 연결 규격 v0.1

공통 규격의 실제 원본은 src/gomoku_interfaces 안 msg/srv/action 파일입니다.
팀원은 같은 gomoku_interfaces 소스를 사용하고 본인 패키지 package.xml에 gomoku_interfaces, rclpy 의존성을 선언하세요.
인터페이스를 같은 이름으로 각자 새로 만들거나 std_msgs/String JSON으로 바꾸지 마세요.
노드 이름은 자유지만 아래 절대 토픽/서비스/액션 이름과 타입은 유지합니다.

## 공통 좌표와 메시지
- 보드 8×8 교차점. row/col 각각 0~7. board[row*8+col].
- 0 빈칸, 1 흑, 2 백, -1 판독 불확실. 알고리즘에는 확정된 0/1/2만 전달.
- 선공 흑, 후공 백. 게임 규칙 현재 금수 없음/5개 이상 연속 승리.
- 방향은 마커 최초 등록 기준. 카메라에서 보이는 좌상을 매번 원점으로 바꾸지 않음.
- game_id: 게임 세션 / turn_id: 지금까지 확정한 착수 수 / request_id: 개별 요청.
- stamp: 노드의 get_clock().now().to_msg(). 모든 노드는 같은 시간 기준 사용.
- 게임 제어만 확정 판과 차례를 변경. 비전/GUI/AI/로봇이 각자 턴을 넘기지 않음.

## 1. 알고리즘 담당자가 만들어 올 것
자기 패키지에 /algorithm/next_move 서비스 서버를 제공합니다.
타입: gomoku_interfaces/srv/NextMove.

입력: game_id, turn_id, request_id, int8[64] board, uint8 to_play.
출력: 세 식별자를 그대로 복사, success, row, col, error.
알고리즘이 실패하면 success=false와 error. 빈칸이 아니거나 범위 밖 좌표는 게임 제어가 거절합니다.
로봇 동작/GUI 갱신/게임 턴 변경을 이 서비스에서 하지 마세요.
기존 AI의 좌표가 1부터 시작하거나 x/y면 여기서 row/col 0부터 시작하도록 변환하세요.
초기 응답 제한은 15초입니다. 더 오래 걸리는 AI면 통합 시 제한을 함께 조정해야 합니다.

템플릿: team_templates/algorithm_adapter.py.
call_existing_algorithm()에 현재 AI를 연결하고 entry point로 설치합니다.

## 2. 로봇 담당자가 만들어 올 것
A. /robot/place_stone Action 서버, 타입 gomoku_interfaces/action/PlaceStone.
B. /robot/status Topic, 타입 gomoku_interfaces/msg/RobotStatus, 권장 10Hz.

Goal: game_id, turn_id, request_id, row, col, color, board_revision.
Feedback: stage 문자열 (PICKING/MOVING/PLACING/RETURNING).
Result: success, returned_to_standby, request_id, error.

상태: stamp, connected, busy, at_standby, board_revision, error.
connected는 실제 드라이버 연결 상태, at_standby는 실제 대기 위치 도달 확인 결과여야 합니다.
요청 받았다고 busy=false나 at_standby=true로 바꾸면 안 됩니다.
착수+그리퍼 동작+대기 위치 복귀 확인 후에만 Action 성공을 반환하세요.
게임 제어는 이후 비전으로 요청 위치/색/기존 돌 보존을 다시 확인합니다.

필수 방어:
- busy 상태 새 Goal 거절. 같은 request_id 중복 실행 금지.
- row/col 범위, color, 보드 좌표 revision, 모션 허용 상태 확인.
- 두산 API 호출 완료만으로 돌 집기/놓기 성공을 보장하지 말고 가용한 실제 상태 확인.
- 실패는 abort와 error로 반환. 성공인 척 반환하지 않음.
- 시간 초과 재전송을 기대하지 마세요. 게임 제어는 불확실한 동작을 자동 재시도하지 않습니다.
- 이 템플릿에는 물리적 긴급 정지 구현이 없습니다. 실제 하드웨어 안전 정지와 Action 취소는 별도 설계가 필요합니다.

board_revision 주의:
비전은 실행 시 1로 시작하고 안정된 영상 좌표가 3px 이상 변하면 증가시킵니다.
이 번호는 로봇 보정이 완료됐다는 뜻이 아닙니다. 로봇 담당은 로봇 기준 격자 좌표를 실제 확인한 revision만 발행하세요.
비전 revision을 무조건 구독해 같은 값으로 복사하면 안 됩니다. 카메라만 이동한 경우에도 재확인 정책을 거치세요.
프로세스 재시작은 revision이 초기화되므로 재시작 시에도 물리 보정을 재검증해야 합니다.
로봇에는 픽셀 x/y를 보내지 않습니다. row/col을 기존 로봇 기준 64개 위치/자세로 변환합니다.

템플릿: team_templates/robot_adapter.py.
기본 connected=false라 동작 요청을 모두 거절합니다. place_and_return()과 실제 상태 갱신을 채우세요.
실제 두산 드라이버는 담당자가 이미 검증한 패키지/모델/IP/명령으로 실행합니다.

## 3. 손 감지 담당자가 만들어 올 것
/vision/image_raw 구독: sensor_msgs/msg/Image, bgr8.
QoS: BEST_EFFORT / VOLATILE, rclpy.qos.qos_profile_sensor_data 사용.
카메라는 비전 노드가 독점합니다. 손 감지 노드에서 RealSense를 다시 열지 마세요.

/vision/hand_state 발행: gomoku_interfaces/msg/HandState, 권장 10~30Hz.
필드: stamp, valid, hand_present.
판 영역에 손이 있으면 true, 정상 검사에서 없으면 false.
원본 영상이 0.5초 이상 오래됐거나 검사 실패면 valid=false. 실패를 손 없음으로 처리하지 않습니다.
원본 영상 시각을 stamp에 보존하세요. 오래된 결과를 새 시각으로 포장하지 마세요.

현재 image_raw는 판 영역 좌표를 따로 제공하지 않습니다.
최초 구현은 전체 원본 영상에서 손이 발견되면 present=true로 보수적으로 처리할 수 있습니다.
판 영역으로 한정하려면 추후 교차점/보드 경계를 전달하는 인터페이스를 추가 협의하세요.

3초 타이머/사용자 차례 판정/검사 요청은 게임 제어가 담당합니다.
손 노드는 손 상태만 보냅니다. 사람 손의 작업 순서가 진입 → 이탈 → 3초 없음일 때 자동 검사.
use_hand:=true인데 신호가 없거나 0.5초 넘게 끊기면 검사하지 않습니다.
손 검출은 게임 진행용이며 로봇 안전 센서가 아닙니다.
템플릿: team_templates/hand_adapter.py. 기본 valid=false입니다.

## 4. 이 패키지가 제공하는 노드
| 노드 | 입력 | 출력 |
|---|---|---|
| gomoku_vision | /vision/inspect, /robot/status | /vision/observation, /vision/image_raw, /vision/debug_image |
| gomoku_controller | 관측/손/로봇 상태, GUI 서비스 요청 | /game/state, AI 서비스 요청, 로봇 Action 요청 |
| gomoku_gui | /game/state, 관측/영상/로봇 상태 | /game/start, /game/end, /game/inspect, /game/cancel_inspect 요청 |

/game/state는 GameState 타입, RELIABLE/TRANSIENT_LOCAL/depth1. 구독도 같은 QoS로 맞추면 실행 직후 마지막 상태를 받습니다.
다른 상태/관측 Topic은 RELIABLE/VOLATILE/depth10입니다. 영상은 sensor_data QoS입니다.
GUI 경고 문구는 GameState.notice에 통합했습니다. 별도 /game/notice 토픽은 만들지 않았습니다.

/vision/inspect: Inspect 서비스. accepted는 검사 접수만 의미하며 결과가 아닙니다.
이후 새 프레임의 /vision/observation에 같은 request_id가 포함됩니다.
추적/판독 유효하고 오래되지 않은 결과만 처리합니다.

/game/start: StartGame 서비스. human_color 1 또는 2.
/game/end: std_srvs/Trigger. 물리 동작이 불명확한 동안 종료 거절.
/game/inspect: std_srvs/Trigger. 수동 3초 검사 요청.
/game/cancel_inspect: std_srvs/Trigger. 사용자 검사 취소.
/vision/set_simulation: SetSimulation 서비스. simulation=true일 때만 허용.

## 5. 팀원 패키지 형태
각자 ament_python 패키지를 생성하고 템플릿 노드를 복사합니다.
setup.py entry_points.console_scripts에 실행 함수를 등록하세요.
package.xml에 rclpy, gomoku_interfaces, 실제 사용하는 드라이버/영상 의존성만 추가하세요.

예시 (패키지/실행파일 이름은 팀원이 정해 공유):
ros2 run team_algorithm algorithm_node
ros2 run team_robot robot_node
ros2 run team_hand hand_node

본 패키지에는 위 이름의 팀원 패키지가 없습니다. 템플릿을 단순 실행해도 실제 AI/로봇/손 감지가 생기지 않습니다.

## 6. 통합 순서
1. 이 패키지 mock_peers=true로 가짜 상대와 전체 턴 진행 확인.
2. mock_peers=false로 바꾸고 실제 알고리즘 서비스만 확인.
3. 로봇 드라이버/착수 Action 서버/상태를 연결. 처음에는 모션 없는 담당자 시험 모드에서 식별자와 좌표 확인.
4. 손 노드 연결 후 use_hand=true.
5. 실제 로봇 좌표 확인 후 제한된 시험부터 진행.

팀원은 노드 소스와 함께 실제 실행 명령, 파라미터, 사용 Python/ROS 버전, 완료·실패 조건을 공유하세요.
