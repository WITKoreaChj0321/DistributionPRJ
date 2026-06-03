"""
기출문제 파일 로더
data/questions/ 폴더의 JSON / CSV 파일을 읽어 표준 형식으로 반환.
"""
import csv
import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from crawler.data_processor import QuestionProcessor

_REQUIRED = {"year", "round", "subject", "question_num", "question_text", "options", "answer"}
_SUBJECT_RANGES = [
    (1,  20, "유통물류일반관리"),
    (21, 40, "상권분석"),
    (41, 60, "유통마케팅"),
    (61, 80, "유통정보"),
]


def _infer_subject(question_num: int) -> str:
    for start, end, name in _SUBJECT_RANGES:
        if start <= question_num <= end:
            return name
    return "유통물류일반관리"


def _normalize_row(row: dict) -> dict:
    """필드 타입 변환 및 subject 자동 추론."""
    q = dict(row)
    q["year"]         = int(q.get("year", 0))
    q["round"]        = int(q.get("round", 1))
    q["question_num"] = int(q.get("question_num", 0))
    q["answer"]       = int(q.get("answer", 1))
    q["explanation"]  = str(q.get("explanation", ""))
    q["source_url"]   = str(q.get("source_url", ""))

    # subject 없으면 문제 번호로 자동 추론
    if not q.get("subject"):
        q["subject"] = _infer_subject(q["question_num"])

    # options가 문자열(CSV)이면 파싱
    opts = q.get("options", [])
    if isinstance(opts, str):
        opts = [o.strip() for o in opts.split("|") if o.strip()]
    q["options"] = opts

    return q


def _load_json(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        data = data.get("questions", [data])
    return [_normalize_row(r) for r in data]


def _load_csv(path: Path) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(_normalize_row(row))
    return rows


def load_from_folder(folder: str | Path = "data/questions") -> list[dict]:
    """
    지정 폴더의 .json / .csv 파일을 모두 읽어 정제된 문제 목록 반환.

    CSV 보기(options) 구분자: 파이프(|)
    예) 1. 수급조절|2. 가격형성|3. 정보전달|4. 생산|5. 위험부담
    """
    folder = Path(folder)
    if not folder.exists():
        raise FileNotFoundError(f"폴더를 찾을 수 없습니다: {folder.resolve()}")

    raw: list[dict] = []
    loaded_files: list[str] = []

    for path in sorted(folder.iterdir()):
        if path.name.startswith((".", "format_example")):
            continue
        if path.suffix == ".json":
            raw.extend(_load_json(path))
            loaded_files.append(path.name)
        elif path.suffix == ".csv":
            raw.extend(_load_csv(path))
            loaded_files.append(path.name)
        elif path.suffix == ".pdf":
            from crawler.pdf_loader import load_pdf
            raw.extend(load_pdf(path))
            loaded_files.append(path.name)

    if not raw:
        print(f"[파일 로더] '{folder}' 에 JSON/CSV 파일이 없습니다.")
        return []

    print(f"[파일 로더] {len(loaded_files)}개 파일 로드: {', '.join(loaded_files)}")
    print(f"[파일 로더] 총 {len(raw)}문제 → 정제 시작")

    processor = QuestionProcessor(verbose=True)
    return processor.process(raw)
