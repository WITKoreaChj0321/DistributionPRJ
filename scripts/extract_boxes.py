"""
원본 교사용 PDF에서 글상자/그림(이미지 영역)을 잘라 boxes/ 폴더에 저장하고,
(year, round, num) → 이미지 경로 매핑 JSON을 만든다.

- 글상자 본문은 PDF에 '이미지'로 박혀 있어 텍스트 추출 불가 → 영역 크롭으로 보존.
- 각 이미지는 같은 컬럼에서 바로 위 문제번호에 귀속.
"""
import sys, io, re, json
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
import fitz

PDF_DIR = ROOT / "data" / "questions"
OUT_DIR = ROOT / "유통관리사" / "boxes"
OUT_DIR.mkdir(parents=True, exist_ok=True)
MAP_JSON = ROOT / "scripts" / "box_map.json"
ZOOM = 3.0
QNUM = re.compile(r"^(\d{1,3})[.\)]$")


def month_to_round(mm):
    if mm in (5, 6): return 1
    if mm in (7, 8): return 2
    return 3


def label_of(stem):
    d = re.search(r"(20\d{2})(\d{2})(\d{2})", stem)
    return f"{d.group(1)}년 {month_to_round(int(d.group(2)))}회", d.group(1), month_to_round(int(d.group(2)))


def q_tokens(page, W):
    """페이지 내 문제번호 토큰: (num, x0, top)."""
    out = []
    for w in page.get_text("words"):
        x0, y0, txt = w[0], w[1], w[4]
        m = QNUM.match(txt)
        if m and 1 <= int(m.group(1)) <= 100:
            out.append((int(m.group(1)), x0, y0))
    return out


def main():
    pdfs = sorted(PDF_DIR.glob("*교사용*.pdf"),
                  key=lambda p: re.search(r"(20\d{6})", p.stem).group(1))
    box_map = {}   # "YYYY년 N회|num" -> [filenames]
    total_imgs = 0
    for pdf in pdfs:
        label, year, rnd = label_of(pdf.stem)
        doc = fitz.open(str(pdf))
        M = fitz.Matrix(ZOOM, ZOOM)
        last = doc.page_count - 1  # 정답표 페이지 제외
        per_pdf = 0
        for pno in range(doc.page_count):
            if pno == last and doc.page_count > 1:
                continue
            page = doc[pno]
            W, H = page.rect.width, page.rect.height
            qpos = q_tokens(page, W)
            if not qpos:
                continue
            seen = set()
            for im in page.get_image_info(xrefs=True):
                b = im["bbox"]
                x0, y0, x1, y1 = b
                w, h = x1 - x0, y1 - y0
                # 글상자/그림 후보 필터: 한 컬럼 폭 이내, 충분한 크기, 헤더 제외
                if w < 80 or h < 22:        # 너무 작음(아이콘/장식)
                    continue
                if w > W * 0.62:            # 전체폭 배너/머리글
                    continue
                if y0 < 60:                 # 페이지 상단 헤더
                    continue
                key = (round(x0), round(y0), round(x1), round(y1))
                if key in seen:
                    continue
                seen.add(key)
                # 귀속 문제번호: 같은 컬럼에서 바로 위
                cx = 0 if x0 < W / 2 else 1
                cand = [(n, qx, qy) for (n, qx, qy) in qpos
                        if (0 if qx < W / 2 else 1) == cx and qy <= y0 + 2]
                if not cand:
                    cand = [(n, qx, qy) for (n, qx, qy) in qpos if qy <= y0 + 2]
                if not cand:
                    continue
                num = max(cand, key=lambda t: t[2])[0]
                clip = fitz.Rect(x0 - 4, y0 - 4, x1 + 4, y1 + 4)
                pix = page.get_pixmap(matrix=M, clip=clip)
                idx = len(box_map.get(f"{label}|{num}", []))
                fn = f"{year}_{rnd}_{num}{'' if idx == 0 else '_' + str(idx + 1)}.png"
                pix.save(str(OUT_DIR / fn))
                box_map.setdefault(f"{label}|{num}", []).append(fn)
                per_pdf += 1
                total_imgs += 1
        print(f"{label}: {per_pdf} images  ({pdf.name})")
    MAP_JSON.write_text(json.dumps(box_map, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n총 {total_imgs}개 이미지, {len(box_map)}개 문제에 귀속")
    print("map ->", MAP_JSON.relative_to(ROOT))


if __name__ == "__main__":
    main()
