"""
시험지 손글씨 마킹(동그라미/사선/형광펜) 자동 감지 — best effort.

Google Vision으로 추출한 문제번호 위치(bounding box) 주변에
컬러 펜 마킹이 집중되어 있으면 '틀린 문제'로 추정한다.

한계: 인쇄 원문자/밑줄 형광펜과 손 마킹 구분이 완벽하지 않으므로
      수동 입력(틀린 번호 직접 입력)을 우선 사용하는 것을 권장.
"""
import numpy as np


def detect_marked_numbers(
    image_bytes: bytes,
    num_positions: list[tuple[int, int, int]],
    radius: int = 90,
    color_ratio_threshold: float = 0.12,
) -> list[int]:
    """
    num_positions: [(문제번호, cx, cy), ...]  — Vision bbox 중심 좌표(원본 픽셀)
    반환: 컬러 마킹이 감지된 문제 번호 리스트
    """
    if not num_positions:
        return []

    try:
        import cv2
    except ImportError:
        return []

    img = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return []

    h, w = img.shape[:2]
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    sat = hsv[:, :, 1]
    val = hsv[:, :, 2]

    # 컬러 펜 마킹 = 채도 높고 너무 어둡지 않은 픽셀 (인쇄 흑백은 채도 낮음)
    # 노란 형광펜(밑줄)은 제외하기 위해 H 20~35(노랑) 대역은 약하게 가중
    h_ch = hsv[:, :, 0]
    is_color = (sat > 90) & (val > 60)
    is_yellow = (h_ch >= 18) & (h_ch <= 38)
    # 노랑(형광펜 밑줄)은 절반 가중치
    color_score = is_color.astype(np.float32)
    color_score[is_yellow & is_color] *= 0.4
    color_score = (color_score > 0.5).astype(np.uint8)

    marked: list[int] = []
    for num, cx, cy in num_positions:
        y0, y1 = max(0, cy - radius), min(h, cy + radius)
        x0, x1 = max(0, cx - radius), min(w, cx + radius)
        if y1 <= y0 or x1 <= x0:
            continue
        region = color_score[y0:y1, x0:x1]
        ratio = float(region.mean()) if region.size else 0.0
        if ratio >= color_ratio_threshold:
            marked.append(num)

    return sorted(set(marked))


def extract_number_positions(text_annotations) -> list[tuple[int, int, int]]:
    """
    Vision text_annotations에서 문제번호(1~80) 블록의 중심 좌표 추출.
    반환: [(번호, cx, cy), ...]
    """
    import re
    num_re = re.compile(r'^(\d{1,3})[.\)]?$')
    positions: list[tuple[int, int, int]] = []
    if not text_annotations:
        return positions

    for ann in text_annotations[1:]:
        m = num_re.match(ann.description.strip())
        if not m:
            continue
        num = int(m.group(1))
        if not (1 <= num <= 80):
            continue
        verts = ann.bounding_poly.vertices
        if not verts:
            continue
        cx = int(sum(v.x for v in verts) / len(verts))
        cy = int(sum(v.y for v in verts) / len(verts))
        positions.append((num, cx, cy))

    return positions
