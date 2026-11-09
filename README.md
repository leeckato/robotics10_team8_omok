# 오목 로봇 (카메라 + 로봇팔 + AlphaZero)

카메라로 판을 인식하고, AlphaZero 모델이 수를 정하고, 로봇팔이 돌을 놓는 오목 프로그램입니다.
PySide6 GUI로 게임을 시작하고 진행 상황을 볼 수 있습니다.

## 설치

```bash
pip install -r requirements.txt
```

## 처음 실행 순서

1. **GUI 실행**: `python main.py`
2. **판 캘리브레이션**: 빈 판을 비추고 [캘리브레이션] → ① 판 → [그리드 검출] → 빨간 점이 교차점과 맞으면 [저장]
3. **돌 판별 캘리브레이션** (권장, 흰 종이 위 흰 돌이면 필수):
   ② 돌 판별 → 빈 판에서 [빈 판 기준 저장] → 돌을 놓고 [화면 가져오기] → 틀린 칸 클릭으로 수정 → [샘플 추가] → [학습 + 저장]
4. **로봇 캘리브레이션**: `python tools/calibrate_robot.py` (로봇팔 끝을 판 네 모서리에 맞춤)
   - 이 단계를 안 하면 **수동 모드**: AI가 정한 수를 사람이 대신 놓아 주면 됩니다
5. [▶ 게임 시작]

카메라 없이 화면만 확인하려면 `config.yaml` 의 `camera.source` 를 `tests/images/grid1_Color.png` 로 바꾸세요.

## 폴더 구조

```
main.py              GUI 실행
run_cli.py           GUI 없이 콘솔로 게임 (디버깅용)
config.yaml          모든 설정값
calib/               캘리브레이션 결과 (자동 생성)
vision/              카메라 → 확정된 판 상태
  camera.py            카메라 / 이미지 파일 입력
  board_detect.py      그리드 검출 + 원근 보정
  stone_classifier.py  교차점별 빈칸/흑/백 판별
  hand_detect.py       손 감지
  board_reader.py      위 셋 조합 + 안정화
ai/                  판 상태 → 다음 수
  alphazero/           원본 저장소 파일 (MIT License)
  omok_ai.py           grid → Board → MCTSPlayer → (row, col)
robot/               다음 수 → 돌 놓기
  arm.py               로봇 SDK 래퍼 (MockArm / CustomArm)
  coords.py            (row, col) → 로봇 좌표
  pick_place.py        집기 → 놓기 → 복귀
game/                턴 관리, 승패, 상태머신 (Qt 모름)
gui/                 PySide6 화면
  workers/             카메라 스레드, 게임 스레드
  widgets/ dialogs/    화면 구성 요소
tools/               캘리브레이션 / 로봇 수동 조작 스크립트
tests/               pytest (python -m pytest tests)
logs/                매 수 사진 + 판 상태
```

## 로봇팔 연결하기

`robot/arm.py` 의 `CustomArm` 클래스에서 `connect`, `move_to`, `grip`, `get_position` 4개를 여러분 로봇 SDK로 구현하고,
`config.yaml` 에서 `robot.driver: custom` 으로 바꾸세요. 나머지 코드는 수정할 필요가 없습니다.

## 좌표 규칙
<img width="531" height="533" alt="image" src="https://github.com/user-attachments/assets/a5848fad-3067-4f29-ad6f-59fd9aea3d68" />

- 보정 이미지 기준 `row` = 위→아래, `col` = 왼쪽→오른쪽, 0부터 시작
- 판 상태 배열: `0` 빈칸, `1` 흑(선공), `2` 백
- AlphaZero move 번호 = `row * n + col`

## 테스트

```bash
python -m pytest tests
```
하드웨어 없이 그리드 검출, 돌 판별, AI, 상태머신을 확인합니다.

## 출처

`ai/alphazero/` 의 코드와 모델은 [junxiaosong/AlphaZero_Gomoku](https://github.com/junxiaosong/AlphaZero_Gomoku) (MIT License) 입니다.
