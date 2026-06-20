"""
해설집 PDF에서 문제별 해설(<문제 해설> 본문)을 추출 → scripts/explanations.json.
키: "YYYY년 N회|num"  값: 해설 텍스트
"""
import sys, io, re, json
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
import fitz

PDF_DIR = ROOT / "data" / "questions"
OUT = ROOT / "scripts" / "explanations.json"

# 헤더/광고 잡음 (해설집 페이지 머리말·반복 문구)
_NOISE = re.compile(
    r"본 해설집은[^\n]*|의해서 만들어진 자료[^\n]*|기출문제 해설은[^\n]*|"
    r"유통관리사\s*2급[^\n]*|전자문제집\s*CBT[^\n]*|출문제 및 해설집[^\n]*|"
    r"BT\s*:\s*www\.comcbt\.com[^\n]*|www\.comcbt\.com[^\n]*|"
    r"정답 및 상세해설집[^\n]*|전\s*\d+문항[^\n]*|문제 출처[^\n]*|"
    r"\d과목\s*:[^\n]*|[◐◑]")
_BYLINE = re.compile(r"\[해설작성자[^\]]*\]")
# 해설 시작 마커: [해설](신형 AI) 또는 <문제 해설>(구형 comcbt)
_EXPL_MARK = re.compile(r"\[\s*해설\s*\]|<\s*문제\s*해설\s*>")


def month_round(mm):
    return 1 if mm in (5, 6) else (2 if mm in (7, 8) else 3)


def page_text(pg):
    W = pg.rect.width
    l = pg.get_text(clip=fitz.Rect(0, 0, W / 2, pg.rect.height))
    r = pg.get_text(clip=fitz.Rect(W / 2, 0, W, pg.rect.height))
    return l + "\n" + r


def clean(t):
    t = _NOISE.sub(" ", t)
    t = _BYLINE.sub(" ", t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{2,}", "\n", t)
    return t.strip()


def extract_one(pdf: Path, label: str, out: dict):
    doc = fitz.open(str(pdf))
    full = "\n".join(page_text(doc[p]) for p in range(doc.page_count))
    full = _NOISE.sub(" ", full)  # 먼저 헤더 제거(블록 경계 오염 방지)

    # 문제 블록 분리: 줄 시작 "N." (옵션 ①은 제외)
    blocks = re.split(r"\n(?=\s{0,3}\d{1,3}\.\s)", full)
    cnt = 0
    for b in blocks:
        m = re.match(r"\s{0,3}(\d{1,3})\.\s", b)
        if not m:
            continue
        num = int(m.group(1))
        if not (1 <= num <= 100):
            continue
        # 해설 마커([해설] 또는 <문제 해설>) 이후 ~ 블록 끝
        sm = _EXPL_MARK.search(b)
        if not sm:
            continue
        expl = clean(b[sm.end():])
        if len(expl) >= 4:
            out[f"{label}|{num}"] = expl
            cnt += 1
    return cnt


def main():
    pdfs = sorted(PDF_DIR.glob("*해설*.pdf"),
                  key=lambda p: re.search(r"(20\d{6})", p.stem).group(1))
    out = {}
    for pdf in pdfs:
        d = re.search(r"(20\d{2})(\d{2})(\d{2})", pdf.stem)
        label = f"{d.group(1)}년 {month_round(int(d.group(2)))}회"
        n = extract_one(pdf, label, out)
        print(f"{label}: 해설 {n}개  ({pdf.name})")
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n총 {len(out)}개 해설 → {OUT.relative_to(ROOT)}")
    # 샘플
    print("\n=== 샘플 ===")
    for k in ["2020년 1회|1", "2020년 1회|3", "2020년 1회|8"]:
        v = out.get(k, "(없음)")
        print(f"[{k}] {v[:120]}")


if __name__ == "__main__":
    main()
