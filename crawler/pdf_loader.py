"""
유통관리사 기출문제 PDF 파서

지원:
  - 선택형(텍스트) PDF: pdfplumber 2컬럼 분리
  - 스캔 PDF: PyMuPDF + pytesseract OCR 폴백
  - 정답: 마지막 페이지 정답표 자동 파싱
"""
import re
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

# ── 상수 ───────────────────────────────────────────
_CIRCLE_TO_NUM = {"①": 1, "②": 2, "③": 3, "④": 4, "⑤": 5}
_CIRCLE_PAT    = re.compile(r"[①②③④⑤]")
_FILLED_PAT    = re.compile(r"[❶❷❸❹❺]")  # 교사용 정답 표시
_FILLED_MAP    = {"❶": 1, "❷": 2, "❸": 3, "❹": 4, "❺": 5}

_SUBJECT_RANGES = [
    (1,  20,  "유통물류일반관리"),
    (21, 40,  "상권분석"),
    (41, 60,  "유통마케팅"),
    (61, 80,  "유통정보"),
]


def _infer_subject(q_num: int) -> str:
    for start, end, name in _SUBJECT_RANGES:
        if start <= q_num <= end:
            return name
    return "유통정보"


# ── 텍스트 추출 ─────────────────────────────────────

def _column_text(page) -> str:
    """
    pdfplumber 페이지를 좌·우 컬럼으로 분리 후 합산.
    각 컬럼을 독립적으로 읽어 문제 섞임 방지.
    """
    w = page.width
    left  = page.within_bbox((0,     0, w * 0.5, page.height))
    right = page.within_bbox((w * 0.5, 0, w,      page.height))

    def safe(col):
        try:
            return col.extract_text(x_tolerance=3, y_tolerance=3) or ""
        except Exception:
            return ""

    return safe(left) + "\n" + safe(right)


def _extract_pdfplumber(path: Path) -> list[str]:
    import pdfplumber
    pages = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            pages.append(_column_text(page))
    return pages


def _extract_ocr(path: Path) -> list[str]:
    """스캔 PDF 폴백: PyMuPDF → PIL → pytesseract."""
    import fitz
    import pytesseract
    from PIL import Image
    import io

    doc = fitz.open(str(path))
    pages = []
    for page in doc:
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        pages.append(pytesseract.image_to_string(img, lang="kor+eng"))
    return pages


def _get_pages(path: Path) -> list[str]:
    for fn in (_extract_pdfplumber, _extract_ocr):
        try:
            pages = fn(path)
            total = sum(len(p.strip()) for p in pages)
            if total > 200:
                return pages
        except Exception:
            continue
    raise RuntimeError(f"PDF 텍스트 추출 실패: {path}")


# ── 정답 표 파싱 ─────────────────────────────────────

def _parse_answer_table(text: str) -> dict[int, int]:
    """
    마지막 페이지 정답표 파싱.
    형식:
      1 2 3 4 5 6 7 8 9 10
      ⑤ ⑤ ⑤ ② ① ③ ② ② ③ ④
    """
    answers: dict[int, int] = {}
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    for i, line in enumerate(lines):
        nums = re.findall(r"\d+", line)
        # 번호만 있는 행 (정답 행 아닌 헤더 행)
        if nums and not _CIRCLE_PAT.search(line) and not _FILLED_PAT.search(line):
            if i + 1 < len(lines):
                ans_line = lines[i + 1]
                circles  = _CIRCLE_PAT.findall(ans_line)
                for num, circle in zip(nums, circles):
                    q_num = int(num)
                    if 1 <= q_num <= 200:
                        answers[q_num] = _CIRCLE_TO_NUM[circle]
    return answers


def _parse_filled_answers(pages: list[str]) -> dict[int, int]:
    """교사용: 채워진 원문자(❶❷❸❹❺)로 정답 감지."""
    answers: dict[int, int] = {}
    q_num = None

    for text in pages:
        for line in text.split("\n"):
            # 새 문제 번호 감지
            m = re.match(r"^(\d{1,3})[.\)]\s", line.strip())
            if m:
                q_num = int(m.group(1))
            # 채워진 원문자 감지
            for ch, val in _FILLED_MAP.items():
                if ch in line and q_num and q_num not in answers:
                    answers[q_num] = val

    return answers


# ── 문제 텍스트 파싱 ─────────────────────────────────

def _split_options(body: str) -> tuple[str, list[str]]:
    """
    문제 본문에서 질문 텍스트와 보기 5개 분리.
    보기 구분자: ①②③④⑤
    """
    parts = re.split(r"(?=[①②③④⑤❶❷❸❹❺])", body)
    if len(parts) < 2:
        return body.strip(), []

    q_text = parts[0].strip()
    opts   = []
    for i, p in enumerate(parts[1:6], 1):
        # 원문자/채워진원문자 제거 후 텍스트
        opt_body = re.sub(r"^[①②③④⑤❶❷❸❹❺]\s*", "", p).strip()
        if opt_body:
            opts.append(f"{i}. {opt_body}")

    return q_text, opts


_HEADER_PAT = re.compile(
    r"유통관리사\s*\d*급[^\n]*\n|최강\s*자격증[^\n]*\n?|전자문제집\s*CBT[^\n]*\n?|"
    r"www\.\S+|◐[^◑]*◑|[◐◑]",
    re.IGNORECASE,
)
_GARBAGE_PAT = re.compile(r"^[\s◐◑제자강최]+$", re.MULTILINE)


def _clean(text: str) -> str:
    """페이지 헤더·광고·특수문자 제거."""
    text = _HEADER_PAT.sub(" ", text)
    text = _GARBAGE_PAT.sub("", text)
    text = re.sub(r"\s{3,}", " ", text)
    return text.strip()


def _clean_qtext(text: str) -> str:
    """질문 텍스트 후처리: 남은 헤더 잔여물 제거."""
    # ◐ ◑ 와 그 사이 텍스트 제거
    text = re.sub(r"[◐◑][^①②③④⑤\n]*", "", text)
    # '최강', '자격증', 'CBT', 'www' 포함 잔여 줄 제거
    lines = [
        l for l in text.split("\n")
        if not re.search(r"최강|자격증|CBT|www\.", l, re.IGNORECASE)
    ]
    return " ".join(l.strip() for l in lines if l.strip())


def _parse_questions(
    pages: list[str],
    year: int,
    round_: int,
    answers: dict[int, int],
) -> list[dict]:
    questions: dict[int, dict] = {}

    # 마지막 페이지(정답표 페이지)를 제외하고 파싱
    content_pages = pages[:-1] if len(pages) > 1 else pages
    full_text = _clean("\n".join(content_pages))

    # 문제 블록 분리: 줄 시작 숫자+점/괄호
    blocks = re.split(r"\n(?=\d{1,3}[.\)]\s)", full_text)

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        m = re.match(r"^(\d{1,3})[.\)]\s*(.+)", block, re.DOTALL)
        if not m:
            continue

        q_num = int(m.group(1))
        if not (1 <= q_num <= 200):
            continue

        body    = m.group(2).strip()
        q_text, opts = _split_options(body)
        q_text = _clean_qtext(q_text)
        if not q_text:
            q_text = f"[{q_num}번 문제 — 글상자 참조]"

        # 이미 파싱된 번호 중 더 긴 텍스트로 업데이트
        if q_num not in questions or len(q_text) > len(questions[q_num]["question_text"]):
            questions[q_num] = {
                "year":         year,
                "round":        round_,
                "subject":      _infer_subject(q_num),
                "question_num": q_num,
                "question_text": q_text,
                "options":      opts,
                "answer":       answers.get(q_num, 1),
                "explanation":  "",
                "source_url":   "",
            }

    return sorted(questions.values(), key=lambda x: x["question_num"])


# ── 파일명에서 연도/회차 추출 ─────────────────────────

def _parse_filename(stem: str) -> tuple[int, int]:
    # 연도: 4자리 연도 (2015~2030)
    year_m = re.search(r"(20[12]\d)", stem)
    year   = int(year_m.group(1)) if year_m else 2024

    # 회차: "_1회", "1회차", "제1회" 등
    round_m = re.search(r"[제_\s]?([1-9])\s*회", stem)
    round_  = int(round_m.group(1)) if round_m else 1

    return year, round_


# ── 공개 API ─────────────────────────────────────────

def load_pdf(path: str | Path) -> list[dict]:
    """
    PDF 기출문제 파일을 파싱해 문제 딕셔너리 목록 반환.

    - 마지막 페이지 정답표를 우선 파싱
    - 교사용(❶❷❸❹❺) 표시도 지원
    - 2컬럼 레이아웃 자동 처리
    """
    path   = Path(path)
    year, round_ = _parse_filename(path.stem)
    print(f"[PDF] {path.name}  →  {year}년 {round_}회차 파싱 중...")

    pages   = _get_pages(path)
    print(f"[PDF] {len(pages)}페이지 텍스트 추출 완료")

    # 정답 수집 (정답표 우선 → 교사용 채워진 원문자 보완)
    answers = _parse_answer_table(pages[-1]) if pages else {}
    if len(answers) < 10:
        answers.update(_parse_filled_answers(pages))
    print(f"[PDF] 정답 {len(answers)}개 수집")

    questions = _parse_questions(pages, year, round_, answers)
    print(f"[PDF] {len(questions)}문제 파싱 완료")
    return questions
