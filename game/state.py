"""게임 상태 정의"""
from enum import Enum


class GameState(Enum):
    IDLE = 'idle'                    # 게임 시작 전 / 중지됨
    WAIT_EMPTY = 'wait_empty'        # 시작 직후: 판이 비어 있는지 확인
    WAIT_HUMAN = 'wait_human'        # 사람 차례
    AI_THINKING = 'ai_thinking'      # AI 계산 중
    ROBOT_MOVING = 'robot_moving'    # 로봇팔이 돌 놓는 중
    VERIFY_ROBOT = 'verify_robot'    # 로봇이 놓은 돌을 카메라로 확인 중
    GAME_OVER = 'game_over'
    ERROR = 'error'


STATE_TEXT = {
    GameState.IDLE: '대기 (게임 시작 전)',
    GameState.WAIT_EMPTY: '판이 비어 있는지 확인 중',
    GameState.WAIT_HUMAN: '사람 차례',
    GameState.AI_THINKING: 'AI 생각 중',
    GameState.ROBOT_MOVING: '로봇이 돌을 놓는 중',
    GameState.VERIFY_ROBOT: '로봇이 놓은 돌 확인 중',
    GameState.GAME_OVER: '게임 종료',
    GameState.ERROR: '오류',
}

COLOR_NAME = {1: '흑', 2: '백'}
