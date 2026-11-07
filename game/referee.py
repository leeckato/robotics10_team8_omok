"""수 검증, 승패 판정"""
import numpy as np

from game.state import COLOR_NAME


def diff(prev, cur):
    """prev -> cur 변화: (추가된 돌 [(r, c, color)], 사라지거나 바뀐 칸 [(r, c)])"""
    prev, cur = np.asarray(prev), np.asarray(cur)
    added = [(int(r), int(c), int(cur[r, c])) for r, c in zip(*np.where((prev == 0) & (cur != 0)))]
    broken = [(int(r), int(c)) for r, c in zip(*np.where((prev != 0) & (cur != prev)))]
    return added, broken


def validate_move(prev, cur, color):
    """
    prev 에서 cur 로 'color 돌 정확히 1개 추가'인지 검사.
    반환: ((row, col), None)  또는  (None, 오류 메시지)
    """
    added, broken = diff(prev, cur)
    if broken:
        return None, f'기존 돌이 사라지거나 바뀜: {broken}'
    if not added:
        return None, None                         # 변화 없음 (오류 아님)
    if len(added) > 1:
        return None, f'돌이 {len(added)}개 추가됨: {[(r, c) for r, c, _ in added]}'
    r, c, col = added[0]
    if col != color:
        return None, f'({r}, {c})에 {COLOR_NAME[col]}돌이 놓임 ({COLOR_NAME[color]} 차례)'
    return (r, c), None


def winner(grid, n_in_row=5):
    """승자 색(1/2) 또는 0"""
    g = np.asarray(grid)
    n = g.shape[0]
    for r in range(n):
        for c in range(n):
            p = g[r, c]
            if not p:
                continue
            for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
                k = 1
                while k < n_in_row:
                    rr, cc = r + dr * k, c + dc * k
                    if not (0 <= rr < n and 0 <= cc < n) or g[rr, cc] != p:
                        break
                    k += 1
                if k == n_in_row:
                    return int(p)
    return 0


def is_full(grid):
    return bool((np.asarray(grid) != 0).all())


def next_color(grid):
    """흑이 선공이므로 돌 개수가 짝수면 흑(1), 홀수면 백(2) 차례"""
    return 1 if int((np.asarray(grid) != 0).sum()) % 2 == 0 else 2
