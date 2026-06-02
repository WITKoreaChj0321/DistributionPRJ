"""
유통관리사 기출문제 데이터 정제 모듈
"""
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

sys.path.append(str(Path(__file__).parent.parent))


# 정규화할 원문자 → 숫자 매핑
CIRCLE_NUM_MAP = {
    "①": "1", "②": "2", "③": "3", "④": "4", "⑤": "5",
    "⑥": "6", "⑦": "7", "⑧": "8", "⑨": "9", "⑩": "10",
}

# 보기 번호 패턴 (①, ②, 1., ㄱ., (1) 등)
OPTION_PREFIX_PATTERN = re.compile(
    r"^[\s]*([①②③④⑤⑥⑦⑧⑨⑩]|\d+[.)]\s*|[ㄱ-ㅎ][.)]\s*|\(\d+\)\s*)"
)


def clean_question_text(text: str) -> str:
    """문제 텍스트에서 불필요한 공백·특수문자 제거."""
    if not text:
        return ""
    # 원문자 정규화
    for circle, num in CIRCLE_NUM_MAP.items():
        text = text.replace(circle, num)
    # 연속 공백·개행 정리
    text = re.sub(r"\s+", " ", text)
    # 앞뒤 공백 제거
    text = text.strip()
    # 불필요한 HTML 엔티티 제거
    text = re.sub(r"&[a-zA-Z]+;", " ", text)
    text = re.sub(r"&#\d+;", " ", text)
    # 연속 마침표 정리 (…같은 것)
    text = re.sub(r"\.{3,}", "...", text)
    # 중복 공백 재정리
    text = re.sub(r" {2,}", " ", text).strip()
    return text


def normalize_options(options: list[str]) -> list[str]:
    """
    보기 번호 정규화.
    ① → "1. ", ② → "2. " 형식으로 통일.
    이미 "1." 형식이면 유지.
    """
    normalized = []
    for i, opt in enumerate(options, start=1):
        if not opt:
            normalized.append(f"{i}. ")
            continue
        text = clean_question_text(opt)
        # 원문자 변환 후 접두 번호 패턴 제거
        text = OPTION_PREFIX_PATTERN.sub("", text).strip()
        normalized.append(f"{i}. {text}")
    return normalized


def validate_question(data: dict) -> tuple[bool, str]:
    """
    필수 필드 검증.
    반환값: (유효 여부, 오류 메시지)
    """
    required_fields = {
        "year": (int, lambda v: 2000 <= v <= 2030),
        "round": (int, lambda v: 1 <= v <= 5),
        "subject": (str, lambda v: bool(v.strip())),
        "question_num": (int, lambda v: 1 <= v <= 200),
        "question_text": (str, lambda v: len(v.strip()) >= 5),
        "options": (list, lambda v: 2 <= len(v) <= 5),
        "answer": (int, lambda v: 1 <= v <= 5),
    }

    for field, (expected_type, validator) in required_fields.items():
        if field not in data:
            return False, f"필수 필드 누락: {field}"
        value = data[field]
        if not isinstance(value, expected_type):
            return False, f"타입 오류 [{field}]: {type(value).__name__} (expected {expected_type.__name__})"
        if not validator(value):
            return False, f"값 범위 오류 [{field}]: {value}"

    return True, ""


def deduplicate(questions: list[dict]) -> list[dict]:
    """
    중복 문제 제거.
    중복 기준: 동일 연도 + 회차 + 문제 번호
    """
    seen: set[tuple] = set()
    unique: list[dict] = []
    for q in questions:
        key = (q.get("year"), q.get("round"), q.get("question_num"))
        if key not in seen:
            seen.add(key)
            unique.append(q)
    return unique


class QuestionProcessor:
    """기출문제 배치 정제 처리기."""

    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self._stats = {"total": 0, "valid": 0, "invalid": 0, "duplicates": 0}

    def process(self, raw_questions: list[dict]) -> list[dict]:
        """
        원시 문제 목록을 정제하여 반환.
        1. 텍스트 정제
        2. 보기 정규화
        3. 유효성 검증
        4. 중복 제거
        """
        self._stats = {"total": len(raw_questions), "valid": 0, "invalid": 0, "duplicates": 0}
        cleaned: list[dict] = []

        for q in raw_questions:
            processed = self._process_single(q)
            if processed is None:
                self._stats["invalid"] += 1
                continue
            cleaned.append(processed)
            self._stats["valid"] += 1

        before_dedup = len(cleaned)
        cleaned = deduplicate(cleaned)
        self._stats["duplicates"] = before_dedup - len(cleaned)

        if self.verbose:
            self._print_stats()

        return cleaned

    def _process_single(self, q: dict) -> Optional[dict]:
        """단일 문제 정제."""
        processed = dict(q)  # 복사

        # 텍스트 정제
        if "question_text" in processed:
            processed["question_text"] = clean_question_text(processed["question_text"])
        if "explanation" in processed and processed["explanation"]:
            processed["explanation"] = clean_question_text(processed["explanation"])

        # 보기 정규화
        if "options" in processed and isinstance(processed["options"], list):
            processed["options"] = normalize_options(processed["options"])

        # 유효성 검증
        valid, err = validate_question(processed)
        if not valid:
            if self.verbose:
                print(f"[데이터 처리] 유효성 오류 제외: {err} | {processed.get('year')}년 {processed.get('round')}회 {processed.get('question_num')}번")
            return None

        return processed

    def get_stats(self) -> dict:
        return dict(self._stats)

    def _print_stats(self):
        s = self._stats
        print(
            f"[데이터 처리] 완료 — "
            f"전체: {s['total']}, 유효: {s['valid']}, "
            f"오류 제외: {s['invalid']}, 중복 제거: {s['duplicates']}"
        )


if __name__ == "__main__":
    from crawler.scraper import load_sample_data

    raw = load_sample_data()
    processor = QuestionProcessor(verbose=True)
    result = processor.process(raw)
    print(f"\n처리 후 문제 수: {len(result)}")
    print("\n첫 번째 문제 보기 정규화 결과:")
    for opt in result[0]["options"]:
        print(f"  {opt}")
