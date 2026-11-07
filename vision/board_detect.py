"""
흰 종이 위에 그린 오목 그리드 검출 + 위에서 본 것처럼 보정(warp)

흐름
  1) 흰 종이 영역 찾기 (밝고 채도 낮은 가장 큰 영역)
  2) 종이 안의 어두운 선 추출 (adaptive threshold) -> 가장 큰 덩어리 = 그리드
  3) 가로/세로선 분리 -> 겹치는 곳 = 교차점
  4) 교차점에 (row, col) 번호 붙이고 RANSAC 호모그래피 -> 가려진 점까지 n x n 복원
  5) 교차점이 margin + i*cell 에 오도록 warp
"""
import cv2
import numpy as np


def _kernel(w, h):
    return cv2.getStructuringElement(cv2.MORPH_RECT, (w, h))


def paper_mask(img):
    """밝고 채도 낮은 가장 큰 영역 = 흰 종이"""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    m = ((hsv[..., 2] > 150) & (hsv[..., 1] < 40)).astype(np.uint8) * 255
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, _kernel(15, 15))
    n, lab, st, _ = cv2.connectedComponentsWithStats(m)
    if n < 2:
        return np.full(img.shape[:2], 255, np.uint8)     # 종이를 못 찾으면 전체 사용
    m = (lab == 1 + np.argmax(st[1:, cv2.CC_STAT_AREA])).astype(np.uint8) * 255
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    filled = np.zeros_like(m)
    cv2.drawContours(filled, cnts, -1, 255, -1)          # 종이 위 돌/선 구멍 메우기
    return cv2.erode(filled, _kernel(9, 9))              # 종이 테두리 그림자 제거


def grid_mask(img):
    """종이 안의 어두운 선 중 가장 큰 연결 덩어리 = 그리드"""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    bw = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                               cv2.THRESH_BINARY_INV, 21, 10)
    bw &= paper_mask(img)
    n, lab, st, _ = cv2.connectedComponentsWithStats(bw)
    if n < 2:
        raise RuntimeError('그리드 선을 찾지 못함')
    i = 1 + np.argmax(st[1:, cv2.CC_STAT_AREA])
    return (lab == i).astype(np.uint8) * 255


def intersections(G, line_len=15):
    """가로선/세로선 마스크를 분리해 겹치는 곳 = 교차점"""
    H = cv2.morphologyEx(G, cv2.MORPH_OPEN, _kernel(line_len, 1))
    H = cv2.morphologyEx(H, cv2.MORPH_CLOSE, _kernel(line_len, 1))
    V = cv2.morphologyEx(G, cv2.MORPH_OPEN, _kernel(1, line_len))
    V = cv2.morphologyEx(V, cv2.MORPH_CLOSE, _kernel(1, line_len))
    J = cv2.dilate(H, _kernel(5, 5)) & cv2.dilate(V, _kernel(5, 5))
    _, _, _, cen = cv2.connectedComponentsWithStats(J)
    return cen[1:].astype(np.float32)


def order_corners(p):
    s, d = p.sum(1), np.diff(p, axis=1).ravel()
    return np.float32([p[s.argmin()], p[d.argmin()], p[s.argmax()], p[d.argmax()]])  # 좌상,우상,우하,좌하


def detect_grid(img, n=8):
    """
    반환:
      grid_pts: (n, n, 2) 원본 이미지에서 각 교차점 픽셀 좌표 [row, col] -> (x, y)
      M:        원본 픽셀 -> 격자 좌표(0..n-1) 호모그래피
      found:    실제로 검출된 교차점 수
    """
    pts = intersections(grid_mask(img))
    if len(pts) < 4:
        raise RuntimeError('교차점을 찾지 못함')

    # 1) 바깥 네 점으로 대략적인 변환 -> 각 점에 (row, col) 번호 붙이기
    hull = cv2.convexHull(pts).reshape(-1, 2)
    ideal4 = np.float32([[0, 0], [n - 1, 0], [n - 1, n - 1], [0, n - 1]])
    M0 = cv2.getPerspectiveTransform(order_corners(hull), ideal4)
    q = cv2.perspectiveTransform(pts[None], M0)[0]
    idx = np.round(q)
    ok = (np.abs(q - idx).max(1) < 0.3) & (idx >= 0).all(1) & (idx <= n - 1).all(1)
    if ok.sum() < 4:
        raise RuntimeError('격자 번호를 붙일 수 있는 교차점이 부족함')
    pts_ok, idx_ok = pts[ok], idx[ok]

    # 2) 번호가 붙은 모든 점으로 정밀한 호모그래피 (가린 점/잡음에 강함)
    M, _ = cv2.findHomography(pts_ok, idx_ok, cv2.RANSAC, 0.15)
    if M is None:
        raise RuntimeError('호모그래피 계산 실패')

    # 3) 가려진 교차점까지 포함해 n x n 전체 좌표 복원
    gx, gy = np.meshgrid(np.arange(n), np.arange(n))
    ideal = np.stack([gx, gy], -1).reshape(-1, 2).astype(np.float32)
    grid_pts = cv2.perspectiveTransform(ideal[None], np.linalg.inv(M))[0].reshape(n, n, 2)
    return grid_pts, M, int(ok.sum())


def warp_matrix(M, cell=60, margin=40):
    """격자 좌표 호모그래피 M -> 원본 픽셀에서 보정 이미지 픽셀로 가는 행렬 W"""
    S = np.array([[cell, 0, margin], [0, cell, margin], [0, 0, 1]], np.float64)
    return S @ M


def warp_board(img, M, n=8, cell=60, margin=40):
    """격자 좌표 -> 보정 이미지 픽셀(margin + i*cell)로 펴기"""
    W = warp_matrix(M, cell, margin)
    size = 2 * margin + cell * (n - 1)
    return cv2.warpPerspective(img, W, (size, size)), W


def apply_warp(img, W, size):
    """저장해 둔 행렬 W로 매 프레임 보정"""
    return cv2.warpPerspective(img, W, (size, size))


def draw_grid_overlay(img, grid_pts):
    """원본 이미지 위에 검출된 교차점/외곽선 그리기"""
    vis = img.copy()
    corners = grid_pts[[0, 0, -1, -1], [0, -1, -1, 0]].astype(np.int32)
    cv2.polylines(vis, [corners], True, (0, 255, 0), 2)
    for p in grid_pts.reshape(-1, 2):
        cv2.circle(vis, (int(p[0]), int(p[1])), 4, (0, 0, 255), -1)
    return vis


def draw_warped_points(warped, n=8, cell=60, margin=40):
    """보정 이미지 위에 교차점 위치 표시 (정렬 확인용)"""
    vis = warped.copy()
    for r in range(n):
        for c in range(n):
            cv2.circle(vis, (margin + c * cell, margin + r * cell), 4, (0, 0, 255), -1)
    return vis
