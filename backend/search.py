import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

import asyncio
from typing import Optional

from backend.analyzer import WrongQuestion
from backend.vectordb import VectorDBManager

SIMILARITY_THRESHOLD = 0.5


class SimilarQuestionSearcher:
    def __init__(self, vectordb: VectorDBManager):
        self._db = vectordb

    async def find_similar_for_wrong(
        self,
        wrong_questions: list[WrongQuestion],
        top_k_per_question: int = 3,
    ) -> dict[int, list[dict]]:
        """
        오답 문제 목록에서 각 문제별 유사 기출문제 검색.
        반환: {문제번호: [유사문제 리스트]}
        """
        tasks = [
            self._search_for_one(wq, top_k_per_question)
            for wq in wrong_questions
        ]
        results = await asyncio.gather(*tasks)
        return {wq.question_num: res for wq, res in zip(wrong_questions, results)}

    async def _search_for_one(
        self, wq: WrongQuestion, top_k: int
    ) -> list[dict]:
        query = wq.question_text.strip()
        if not query:
            query = f"유통관리사 {wq.subject} 문제 {wq.question_num}번"

        # 같은 과목 우선 검색 (n_results를 넉넉하게)
        candidates = await self._db.search_similar(
            query_text=query,
            n_results=top_k * 3,
            subject_filter=wq.subject if wq.subject != "기타" else None,
        )

        # 유사도 필터링
        candidates = [c for c in candidates if c["similarity"] >= SIMILARITY_THRESHOLD]

        # 원본 문제 제외 (동일 과목 + 동일 문제번호)
        candidates = [
            c for c in candidates
            if not (
                c["subject"] == wq.subject
                and c["question_num"] == wq.question_num
            )
        ]

        # 유사도 내림차순 정렬 후 top_k 반환
        candidates.sort(key=lambda x: x["similarity"], reverse=True)
        return candidates[:top_k]

    async def search_by_text(
        self,
        text: str,
        subject: Optional[str] = None,
    ) -> list[dict]:
        """
        텍스트로 직접 유사 문제 검색.
        과목 필터 적용 가능.
        """
        results = await self._db.search_similar(
            query_text=text,
            n_results=10,
            subject_filter=subject,
        )
        results = [r for r in results if r["similarity"] >= SIMILARITY_THRESHOLD]
        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results
