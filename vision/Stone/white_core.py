"""백돌: 고정 밝기 대신 주변 밝기로 정규화한 중심 격자선 대비 비교."""
import numpy as np

CORE_RADIUS = 3
SEARCH_RADIUS = 1  # 중심에서 상하좌우 및 대각선으로 1픽셀 탐색
MIN_REFERENCE_CONTRAST = 0.06
MAX_CURRENT_CONTRAST = 0.12
MAX_REMAINING_RATIO = 0.50
MAX_CORE_SPREAD = 0.12
MIN_SURFACE_RATIO = 0.70
MIN_BACKGROUND_LEVEL = 40
CONFIRM_FRAMES = 5


def grid_features(patch, dx=0, dy=0):
    if patch is None or patch.shape != (15, 15):
        return None
    values = patch.astype(float)
    background = float(np.percentile(values, 80))
    if background < MIN_BACKGROUND_LEVEL:
        return None
    core = values[7+dy-CORE_RADIUS:8+dy+CORE_RADIUS,
                  7+dx-CORE_RADIUS:8+dx+CORE_RADIUS]
    # 중심 주변에서 가장 어두운 행·열을 찾아 약간의 좌표 차이를 허용합니다.
    horizontal = max(0.0, (background - float(np.min(core.mean(axis=1)))) / background)
    vertical = max(0.0, (background - float(np.min(core.mean(axis=0)))) / background)
    spread = float(np.percentile(core, 90)-np.percentile(core, 10)) / background
    surface = float(np.median(core)) / background
    return dict(background=background, horizontal=horizontal, vertical=vertical,
                spread=spread, surface=surface)


def is_white_stone(patch, reference_patch):
    reference = grid_features(reference_patch)
    if reference is None:
        return False
    if any(reference[d] < MIN_REFERENCE_CONTRAST
           for d in ('horizontal', 'vertical')):
        return False
    # 원래 교차점에 연결하되, 백돌 표면 확인 위치만 최대 1픽셀 이동합니다.
    for dy in range(-SEARCH_RADIUS, SEARCH_RADIUS+1):
        for dx in range(-SEARCH_RADIUS, SEARCH_RADIUS+1):
            current = grid_features(patch, dx, dy)
            if current is None:
                continue
            if any(current[d] > MAX_CURRENT_CONTRAST
                   or current[d] > reference[d] * MAX_REMAINING_RATIO
                   for d in ('horizontal', 'vertical')):
                continue
            if (current['spread'] <= MAX_CORE_SPREAD
                    and current['surface'] >= MIN_SURFACE_RATIO):
                return True
    return False


def confirm_white(counts, key, candidate):
    counts[key] = min(counts.get(key, 0)+1, CONFIRM_FRAMES) if candidate else 0
    return counts[key] >= CONFIRM_FRAMES
