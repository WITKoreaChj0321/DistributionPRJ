import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from dataclasses import dataclass, field
from typing import Optional

from backend.ocr import OCRResult, ParsedQuestion


# 유통관리사 2급 과목 범위
SUBJECT_MAP = [
    (1, 20, "유통물류일반관리"),
    (21, 40, "상권분석"),
    (41, 60, "유통마케팅"),
    (61, 80, "유통정보"),
]


def _infer_subject(question_num: int) -> str:
    for start, end, name in SUBJECT_MAP:
        if start <= question_num <= end:
            return name
    return "기타"


@dataclass
class WrongQuestion:
    question_num: int
    question_text: str
    selected_answer: int
    correct_answer: Optional[int]
    subject: str
    options: list[str] = None  # 보기 중복 판단용 (OCR 추출 시 채워짐)


@dataclass
class AnalysisResult:
    total_questions: int
    wrong_questions: list[WrongQuestion]
    subjects_weak: list[str]  # 약한 과목 목록 (오답 비율 기준)


class ExamAnalyzer:
    def analyze(
        self,
        ocr_result: OCRResult,
        correct_answers: Optional[dict[int, int]] = None,
    ) -> AnalysisResult:
        wrong_questions = self._extract_wrong_questions(ocr_result, correct_answers)
        subjects_weak = self._compute_weak_subjects(wrong_questions, ocr_result)

        return AnalysisResult(
            total_questions=len(ocr_result.parsed_questions),
            wrong_questions=wrong_questions,
            subjects_weak=subjects_weak,
        )

    def _extract_wrong_questions(
        self,
        ocr_result: OCRResult,
        correct_answers: Optional[dict[int, int]],
    ) -> list[WrongQuestion]:
        wrong: list[WrongQuestion] = []

        # 오답으로 마킹된 문제 번호 집합
        marked_wrong_set = set(ocr_result.wrong_question_nums)

        parsed_map = {q.num: q for q in ocr_result.parsed_questions}

        # 1) 오답 마킹 감지 기반
        for num in marked_wrong_set:
            pq = parsed_map.get(num)
            if pq is None:
                pq = ParsedQuestion(num=num, text="", selected_answer=0, is_marked_wrong=True)
            correct = correct_answers.get(num) if correct_answers else None
            wrong.append(WrongQuestion(
                question_num=num,
                question_text=pq.text,
                selected_answer=pq.selected_answer,
                correct_answer=correct,
                subject=_infer_subject(num),
            ))

        # 2) 정답지가 제공된 경우 추가 비교
        if correct_answers:
            already_added = {w.question_num for w in wrong}
            for pq in ocr_result.parsed_questions:
                if pq.num in already_added:
                    continue
                correct = correct_answers.get(pq.num)
                if correct is None:
                    continue
                if not self._compare_answers(pq, correct):
                    wrong.append(WrongQuestion(
                        question_num=pq.num,
                        question_text=pq.text,
                        selected_answer=pq.selected_answer,
                        correct_answer=correct,
                        subject=_infer_subject(pq.num),
                    ))

        wrong.sort(key=lambda w: w.question_num)
        return wrong

    def _compare_answers(self, parsed: ParsedQuestion, correct: int) -> bool:
        """선택 답과 정답 비교. True = 정답."""
        if parsed.selected_answer == 0:
            return True  # 감지 실패 시 오답으로 간주하지 않음
        return parsed.selected_answer == correct

    def _compute_weak_subjects(
        self,
        wrong_questions: list[WrongQuestion],
        ocr_result: OCRResult,
    ) -> list[str]:
        """과목별 오답률 계산 후 50% 이상인 과목을 약점 과목으로 반환."""
        subject_total: dict[str, int] = {}
        subject_wrong: dict[str, int] = {}

        for pq in ocr_result.parsed_questions:
            subj = _infer_subject(pq.num)
            subject_total[subj] = subject_total.get(subj, 0) + 1

        for wq in wrong_questions:
            subject_wrong[wq.subject] = subject_wrong.get(wq.subject, 0) + 1

        weak: list[tuple[float, str]] = []
        for subj, total in subject_total.items():
            wrong_cnt = subject_wrong.get(subj, 0)
            ratio = wrong_cnt / total if total > 0 else 0.0
            if ratio >= 0.5 or (total > 0 and wrong_cnt >= 3):
                weak.append((ratio, subj))

        weak.sort(reverse=True, key=lambda x: x[0])
        return [s for _, s in weak]
