"""
유통관리사 기출문제 크롤러
대상: CBT 기출문제 공개 사이트 (robots.txt 준수)
"""
import asyncio
import re
import json
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional
import httpx
from bs4 import BeautifulSoup

sys.path.append(str(Path(__file__).parent.parent))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

REQUEST_DELAY = 1.5   # 서버 부하 방지 딜레이 (초)
MAX_RETRIES = 3       # 최대 재시도 횟수

# 유통관리사 2급 과목별 문제 번호 범위
SUBJECT_RANGES = [
    (1,  20, "유통물류일반관리"),
    (21, 40, "상권분석"),
    (41, 60, "유통마케팅"),
    (61, 80, "유통정보"),
]


@dataclass
class QuestionData:
    year: int
    round: int
    subject: str
    question_num: int
    question_text: str
    options: list[str]
    answer: int
    explanation: str = ""
    source_url: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class DistributionExamCrawler:
    """
    공개된 유통관리사 기출문제를 크롤링합니다.
    실제 크롤링 전 대상 사이트 robots.txt와 이용약관을 반드시 확인하세요.
    """

    def __init__(self):
        self.client = httpx.AsyncClient(
            headers=HEADERS, timeout=30.0, follow_redirects=True
        )
        self.results: list[QuestionData] = []

    async def close(self):
        await self.client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self.close()

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------

    async def crawl_all(
        self, start_year: int = 2015, end_year: int = 2024
    ) -> list[QuestionData]:
        """지정 연도 범위 전체 크롤링."""
        self.results = []
        for year in range(start_year, end_year + 1):
            year_qs = await self.crawl_year(year)
            self.results.extend(year_qs)
        return self.results

    async def crawl_year(self, year: int) -> list[QuestionData]:
        """특정 연도의 모든 회차 크롤링 (보통 연 3회)."""
        year_results: list[QuestionData] = []
        for round_ in range(1, 4):
            print(f"[크롤러] {year}년 {round_}회차 수집 중...")
            qs = await self._crawl_round_with_retry(year, round_)
            if qs:
                print(f"[크롤러] {year}년 {round_}회차: {len(qs)}문제 수집")
                year_results.extend(qs)
            else:
                print(f"[크롤러] {year}년 {round_}회차: 데이터 없음")
            await asyncio.sleep(REQUEST_DELAY)
        return year_results

    # ------------------------------------------------------------------
    # 내부 크롤링 로직
    # ------------------------------------------------------------------

    async def _crawl_round_with_retry(
        self, year: int, round_: int
    ) -> list[QuestionData]:
        """재시도 3회 포함 단일 회차 크롤링."""
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                qs = await self._crawl_round(year, round_)
                if qs:
                    return qs
            except httpx.HTTPError as e:
                print(f"[크롤러] HTTP 오류 ({attempt}/{MAX_RETRIES}): {e}")
            except Exception as e:
                print(f"[크롤러] 오류 ({attempt}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES:
                await asyncio.sleep(REQUEST_DELAY * attempt)
        return []

    async def _crawl_round(self, year: int, round_: int) -> list[QuestionData]:
        """CBT 기출문제닷컴 스타일 사이트에서 단일 회차 크롤링."""
        # 일반적인 한국 CBT 기출문제 사이트 URL 패턴 예시
        # robots.txt 허용 범위 내의 공개 페이지만 접근
        urls = [
            f"https://www.cbt.or.kr/index.php?m=view&q=distribution&year={year}&round={round_}",
            f"https://cbt.eduware.co.kr/exam/distribution/{year}/{round_}",
        ]

        for url in urls:
            try:
                resp = await self.client.get(url)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "lxml")
                    qs = self._parse_cbt_page(soup, year, round_, url)
                    if qs:
                        return qs
            except Exception:
                continue
        return []

    def _parse_cbt_page(
        self, soup: BeautifulSoup, year: int, round_: int, source_url: str
    ) -> list[QuestionData]:
        """CBT 기출문제닷컴 스타일 HTML 파싱."""
        questions: list[QuestionData] = []

        # 일반적인 CBT 사이트 셀렉터 패턴들
        selectors = [
            ".question-wrap",
            ".q-item",
            ".exam-question",
            "[class*='question-box']",
            "div.q_wrap",
            "li.question",
        ]

        q_blocks = []
        for sel in selectors:
            q_blocks = soup.select(sel)
            if q_blocks:
                break

        for block in q_blocks:
            try:
                q = self._parse_question_block(block, year, round_, source_url)
                if q:
                    questions.append(q)
            except Exception:
                continue

        return questions

    def _parse_question_block(
        self, block: BeautifulSoup, year: int, round_: int, source_url: str
    ) -> Optional[QuestionData]:
        """단일 문제 블록 HTML 파싱."""
        # 문제 번호
        num_el = block.select_one(
            ".q-num, .question-num, .num, [class*='q_num'], [class*='no']"
        )
        # 문제 텍스트
        text_el = block.select_one(
            ".q-text, .question-text, .q_text, [class*='question_text'], p.q"
        )
        # 보기 항목들
        options_el = block.select(
            ".q-option, .option-item, .choice, li.opt, [class*='choice'], [class*='option']"
        )
        # 정답
        answer_el = block.select_one(
            ".answer, .correct-answer, [class*='answer'], [data-answer]"
        )

        if not text_el or not options_el:
            return None

        # 문제 번호 추출
        q_num = 0
        if num_el:
            m = re.search(r"\d+", num_el.get_text())
            if m:
                q_num = int(m.group())

        q_text = text_el.get_text(separator=" ", strip=True)

        # 보기 정규화
        options = [opt.get_text(separator=" ", strip=True) for opt in options_el[:5]]

        # 정답 추출
        answer = 1
        if answer_el:
            ans_text = answer_el.get("data-answer") or answer_el.get_text()
            m = re.search(r"\d+", str(ans_text))
            if m:
                answer = int(m.group())

        subject = self._infer_subject(q_num)

        return QuestionData(
            year=year,
            round=round_,
            subject=subject,
            question_num=q_num,
            question_text=q_text,
            options=options,
            answer=answer,
            source_url=source_url,
        )

    def _infer_subject(self, q_num: int) -> str:
        """문제 번호 범위로 과목 추정 (유통관리사 2급 기준)."""
        for start, end, subject in SUBJECT_RANGES:
            if start <= q_num <= end:
                return subject
        return "유통물류일반관리"  # 기본값


# ------------------------------------------------------------------
# 샘플 데이터 (크롤링 실패 시 폴백 / 개발 테스트용)
# 각 과목별 5문제씩 총 20개
# ------------------------------------------------------------------

def load_sample_data() -> list[dict]:
    """
    실제 크롤링 실패 시 또는 개발/테스트용 샘플 데이터.
    각 과목별 5문제, 총 20문제.
    """
    return [
        # ── 유통물류일반관리 (1~20번) ──────────────────────────────────
        {
            "year": 2024, "round": 1, "subject": "유통물류일반관리",
            "question_num": 1,
            "question_text": "다음 중 유통경로의 기능으로 옳지 않은 것은?",
            "options": [
                "1. 수급조절 기능",
                "2. 가격형성 기능",
                "3. 정보전달 기능",
                "4. 생산 기능",
                "5. 위험부담 기능",
            ],
            "answer": 4,
            "explanation": (
                "유통경로의 기능에는 수급조절, 가격형성, 정보전달, 위험부담 등이 있으며 "
                "생산 기능은 유통경로의 기능에 해당하지 않는다."
            ),
            "source_url": "sample",
        },
        {
            "year": 2023, "round": 2, "subject": "유통물류일반관리",
            "question_num": 5,
            "question_text": "SCM(공급사슬관리)의 목적으로 가장 적합한 것은?",
            "options": [
                "1. 재고 최소화와 고객서비스 극대화",
                "2. 생산비용만의 절감",
                "3. 판매 채널 다양화",
                "4. 직원 교육 강화",
                "5. 마케팅 비용 절감",
            ],
            "answer": 1,
            "explanation": (
                "SCM은 공급자에서 최종 소비자까지 전체 공급사슬의 재고를 최소화하면서 "
                "고객서비스 수준을 극대화하는 것을 목적으로 한다."
            ),
            "source_url": "sample",
        },
        {
            "year": 2023, "round": 1, "subject": "유통물류일반관리",
            "question_num": 10,
            "question_text": "물류센터에서 크로스도킹(Cross-docking)에 관한 설명으로 옳은 것은?",
            "options": [
                "1. 입고된 상품을 보관 후 출고하는 방식이다",
                "2. 입고 즉시 분류하여 출고하는 방식으로 재고 보관을 최소화한다",
                "3. 상품을 대량으로 구매하여 창고에 저장하는 방식이다",
                "4. 소비자가 직접 창고에서 픽업하는 방식이다",
                "5. 제조업체에서 소비자에게 직접 배송하는 방식이다",
            ],
            "answer": 2,
            "explanation": (
                "크로스도킹은 물류센터에 입고된 상품을 별도 보관 없이 즉시 분류하여 "
                "출고하는 방식으로, 재고 보관 비용을 최소화하고 배송 속도를 높인다."
            ),
            "source_url": "sample",
        },
        {
            "year": 2022, "round": 2, "subject": "유통물류일반관리",
            "question_num": 15,
            "question_text": "유통 경로 갈등(channel conflict)의 원인으로 가장 거리가 먼 것은?",
            "options": [
                "1. 목표 불일치",
                "2. 역할 불명확",
                "3. 정보 비대칭",
                "4. 제품 품질 향상",
                "5. 영역 침범",
            ],
            "answer": 4,
            "explanation": (
                "유통경로 갈등의 주요 원인은 목표 불일치, 역할 불명확, 정보 비대칭, "
                "영역 침범 등이다. 제품 품질 향상은 갈등 원인과 무관하다."
            ),
            "source_url": "sample",
        },
        {
            "year": 2022, "round": 1, "subject": "유통물류일반관리",
            "question_num": 20,
            "question_text": "JIT(Just-in-Time) 시스템의 특징으로 옳지 않은 것은?",
            "options": [
                "1. 소로트 생산",
                "2. 재고 최소화",
                "3. 납품 리드타임 단축",
                "4. 대규모 재고 유지",
                "5. 공급자와의 긴밀한 협력",
            ],
            "answer": 4,
            "explanation": (
                "JIT 시스템은 필요한 때 필요한 양만 생산·조달하여 재고를 최소화하는 "
                "방식으로, 대규모 재고 유지는 JIT와 상반된 개념이다."
            ),
            "source_url": "sample",
        },
        # ── 상권분석 (21~40번) ─────────────────────────────────────────
        {
            "year": 2024, "round": 1, "subject": "상권분석",
            "question_num": 21,
            "question_text": "상권분석 기법 중 허프(Huff)모델에 관한 설명으로 옳은 것은?",
            "options": [
                "1. 경쟁점포의 규모와 거리를 고려한 확률적 모델이다",
                "2. 거리만을 고려한 결정론적 모델이다",
                "3. 인구통계 변수만을 사용한다",
                "4. 점포 이미지를 주요 변수로 사용한다",
                "5. 매출액 예측에 사용할 수 없다",
            ],
            "answer": 1,
            "explanation": (
                "허프모델은 점포의 매력도(규모)와 거리를 이용하여 소비자의 점포 선택 "
                "확률을 구하는 확률적 모델이다."
            ),
            "source_url": "sample",
        },
        {
            "year": 2023, "round": 3, "subject": "상권분석",
            "question_num": 25,
            "question_text": "컨버스(Converse)의 수정 소매 인력 법칙에서 두 도시 사이의 상권 경계점을 결정하는 요인은?",
            "options": [
                "1. 두 도시의 인구 규모와 두 도시 간 거리",
                "2. 두 도시의 소득 수준과 교통망",
                "3. 두 도시의 점포 수와 면적",
                "4. 두 도시의 관광객 수와 교통 비용",
                "5. 두 도시의 물가 수준과 상품 다양성",
            ],
            "answer": 1,
            "explanation": (
                "컨버스의 수정 소매 인력 법칙은 두 도시의 인구 규모와 두 도시 간 거리를 "
                "이용하여 두 도시 사이의 상권 경계점(분기점)을 결정한다."
            ),
            "source_url": "sample",
        },
        {
            "year": 2023, "round": 1, "subject": "상권분석",
            "question_num": 30,
            "question_text": "입지 선정 시 체크리스트 방법의 장점으로 옳은 것은?",
            "options": [
                "1. 입지 요인들의 상대적 중요도를 정확히 반영한다",
                "2. 사용 방법이 간단하고 다양한 입지 요인을 고려할 수 있다",
                "3. 복잡한 통계 분석을 통해 정밀한 결과를 도출한다",
                "4. 소비자 행동을 확률적으로 예측할 수 있다",
                "5. 경쟁점의 영향을 정량적으로 분석할 수 있다",
            ],
            "answer": 2,
            "explanation": (
                "체크리스트 방법은 사용이 간단하고 다양한 입지 요인을 종합적으로 고려할 "
                "수 있다는 장점이 있으나, 요인 간 중요도를 동등하게 취급하는 단점이 있다."
            ),
            "source_url": "sample",
        },
        {
            "year": 2022, "round": 2, "subject": "상권분석",
            "question_num": 35,
            "question_text": "상권의 유형 중 배후지 상권의 특징으로 옳은 것은?",
            "options": [
                "1. 유동인구가 많아 충동 구매가 빈번하다",
                "2. 거주 인구를 주요 고객으로 하는 안정적 상권이다",
                "3. 관광객을 주요 타깃으로 한다",
                "4. 대형 쇼핑몰 주변에 형성된다",
                "5. 주거지역보다 업무지역에 더 많이 형성된다",
            ],
            "answer": 2,
            "explanation": (
                "배후지 상권은 인근 거주 인구를 주요 고객으로 하며, 반복 구매가 이루어져 "
                "비교적 안정적인 매출을 기대할 수 있다."
            ),
            "source_url": "sample",
        },
        {
            "year": 2021, "round": 2, "subject": "상권분석",
            "question_num": 40,
            "question_text": "GIS(지리정보시스템)를 상권분석에 활용할 때의 장점이 아닌 것은?",
            "options": [
                "1. 지리적 데이터를 시각적으로 표현할 수 있다",
                "2. 상권의 공간적 범위를 객관적으로 파악할 수 있다",
                "3. 경쟁 점포의 위치를 지도에 표시하여 분석할 수 있다",
                "4. 소비자의 심리적 구매 동기를 직접 파악할 수 있다",
                "5. 인구통계 데이터와 결합하여 분석할 수 있다",
            ],
            "answer": 4,
            "explanation": (
                "GIS는 지리적·공간적 분석에 유용하지만, 소비자의 심리적 구매 동기를 "
                "직접 파악하는 기능은 제공하지 않는다."
            ),
            "source_url": "sample",
        },
        # ── 유통마케팅 (41~60번) ──────────────────────────────────────
        {
            "year": 2024, "round": 2, "subject": "유통마케팅",
            "question_num": 41,
            "question_text": "소매업의 아코디언 이론(Retail Accordion Theory)에 관한 설명으로 옳은 것은?",
            "options": [
                "1. 소매업태가 저가격에서 고가격으로 진화한다는 이론이다",
                "2. 취급 상품 범위가 넓어졌다 좁아졌다 반복하며 진화한다는 이론이다",
                "3. 소매점의 규모가 점차 대형화된다는 이론이다",
                "4. 온라인과 오프라인이 번갈아 주도권을 갖는다는 이론이다",
                "5. 소매업의 수익률이 주기적으로 변동한다는 이론이다",
            ],
            "answer": 2,
            "explanation": (
                "아코디언 이론은 소매업태가 다양한 상품을 취급하는 종합화 단계와 "
                "특정 상품에 집중하는 전문화 단계를 반복하며 진화한다고 설명한다."
            ),
            "source_url": "sample",
        },
        {
            "year": 2022, "round": 3, "subject": "유통마케팅",
            "question_num": 45,
            "question_text": "CRM(고객관계관리)에서 고객 생애 가치(CLV) 계산 시 고려해야 할 요소가 아닌 것은?",
            "options": [
                "1. 고객 유지율",
                "2. 평균 구매 금액",
                "3. 할인율",
                "4. 직원 만족도",
                "5. 고객 획득 비용",
            ],
            "answer": 4,
            "explanation": (
                "CLV 계산에는 고객 유지율, 평균 구매 금액, 할인율, 고객 획득/유지 비용 "
                "등이 고려되며, 직원 만족도는 포함되지 않는다."
            ),
            "source_url": "sample",
        },
        {
            "year": 2023, "round": 2, "subject": "유통마케팅",
            "question_num": 50,
            "question_text": "판매촉진(Sales Promotion) 수단 중 푸시(Push) 전략에 해당하는 것은?",
            "options": [
                "1. 소비자 쿠폰",
                "2. 광고",
                "3. 중간상 리베이트",
                "4. 샘플링",
                "5. PR 활동",
            ],
            "answer": 3,
            "explanation": (
                "푸시 전략은 제조업체가 유통업자(중간상)를 대상으로 하는 촉진 활동으로, "
                "중간상 리베이트, 판매장려금, 협동광고 등이 해당한다."
            ),
            "source_url": "sample",
        },
        {
            "year": 2022, "round": 1, "subject": "유통마케팅",
            "question_num": 55,
            "question_text": "카테고리 관리(Category Management)의 핵심 원칙으로 가장 적합한 것은?",
            "options": [
                "1. 개별 상품 단위로 독립적으로 관리한다",
                "2. 소비자 관점에서 관련 상품군을 하나의 사업 단위로 관리한다",
                "3. 제조업체 주도로 상품 구색을 결정한다",
                "4. 가격 경쟁력 확보를 최우선으로 한다",
                "5. 재고 회전율 극대화만을 목표로 한다",
            ],
            "answer": 2,
            "explanation": (
                "카테고리 관리는 소비자 관점에서 관련 상품군 전체를 하나의 전략적 "
                "사업 단위로 관리하여 매출과 이익을 극대화하는 접근 방식이다."
            ),
            "source_url": "sample",
        },
        {
            "year": 2021, "round": 3, "subject": "유통마케팅",
            "question_num": 60,
            "question_text": "PB(Private Brand) 상품에 관한 설명으로 옳지 않은 것은?",
            "options": [
                "1. 유통업체가 자체적으로 개발한 브랜드이다",
                "2. NB(National Brand)보다 낮은 가격에 판매되는 경우가 많다",
                "3. 유통업체의 마진율이 NB 상품보다 높은 편이다",
                "4. 제품 개발 및 품질 관리 책임이 제조업체에만 있다",
                "5. 소비자에게 가격 대비 가치를 제공하는 것을 목표로 한다",
            ],
            "answer": 4,
            "explanation": (
                "PB 상품은 유통업체가 기획·개발하는 상품으로, 제품 개발 및 품질 관리의 "
                "최종 책임은 유통업체(소매업체)에 있다."
            ),
            "source_url": "sample",
        },
        # ── 유통정보 (61~80번) ─────────────────────────────────────────
        {
            "year": 2023, "round": 1, "subject": "유통정보",
            "question_num": 62,
            "question_text": "바코드 중 GS1-128 바코드에 관한 설명으로 옳지 않은 것은?",
            "options": [
                "1. 물류단위 식별에 주로 사용된다",
                "2. 응용식별자(AI)를 사용하여 다양한 정보를 표현한다",
                "3. 고정 길이 데이터만 표현 가능하다",
                "4. 제조일자, 유통기한 등을 표현할 수 있다",
                "5. 연속형 심볼로지를 사용한다",
            ],
            "answer": 3,
            "explanation": (
                "GS1-128은 가변 길이 데이터도 표현 가능하며, 응용식별자(AI)를 통해 "
                "다양한 유형의 정보를 유연하게 표현할 수 있다."
            ),
            "source_url": "sample",
        },
        {
            "year": 2024, "round": 1, "subject": "유통정보",
            "question_num": 65,
            "question_text": "EDI(전자문서교환)에 관한 설명으로 옳은 것은?",
            "options": [
                "1. 기업 내부에서만 사용하는 정보시스템이다",
                "2. 표준화된 형식으로 거래 문서를 전자적으로 교환하는 시스템이다",
                "3. 인터넷이 보급된 이후에 등장한 기술이다",
                "4. 소비자와 기업 간(B2C) 거래에 주로 활용된다",
                "5. XML 기반으로만 구현된다",
            ],
            "answer": 2,
            "explanation": (
                "EDI는 기업 간(B2B) 거래에서 주문서, 청구서 등의 문서를 표준화된 형식으로 "
                "전자적으로 교환하는 시스템으로, 인터넷 이전부터 존재했다."
            ),
            "source_url": "sample",
        },
        {
            "year": 2023, "round": 2, "subject": "유통정보",
            "question_num": 70,
            "question_text": "RFID(무선주파수인식) 기술의 특징으로 옳지 않은 것은?",
            "options": [
                "1. 비접촉 방식으로 데이터를 읽을 수 있다",
                "2. 여러 태그를 동시에 인식하는 것이 가능하다",
                "3. 바코드보다 저장 용량이 적다",
                "4. 금속이나 액체 환경에서 인식률이 낮아질 수 있다",
                "5. 실시간 추적 및 재고 관리에 활용된다",
            ],
            "answer": 3,
            "explanation": (
                "RFID 태그는 바코드보다 훨씬 많은 데이터를 저장할 수 있으며, "
                "읽기/쓰기가 가능하다는 것이 바코드 대비 주요 장점 중 하나이다."
            ),
            "source_url": "sample",
        },
        {
            "year": 2022, "round": 1, "subject": "유통정보",
            "question_num": 75,
            "question_text": "빅데이터의 3V 특성에 해당하지 않는 것은?",
            "options": [
                "1. Volume(규모)",
                "2. Velocity(속도)",
                "3. Variety(다양성)",
                "4. Validity(유효성)",
                "5. 위의 보기 중 3V가 모두 있다",
            ],
            "answer": 4,
            "explanation": (
                "빅데이터의 3V는 Volume(규모), Velocity(속도), Variety(다양성)를 의미한다. "
                "Validity(유효성)는 기본 3V에 포함되지 않는다."
            ),
            "source_url": "sample",
        },
        {
            "year": 2021, "round": 2, "subject": "유통정보",
            "question_num": 80,
            "question_text": "전자상거래에서 에스크로(Escrow) 서비스의 목적으로 가장 적합한 것은?",
            "options": [
                "1. 결제 처리 속도를 높이기 위해",
                "2. 구매자와 판매자 간 신뢰 보장 및 안전 거래를 위해",
                "3. 판매자의 매출을 증대시키기 위해",
                "4. 물류 배송 시간을 단축시키기 위해",
                "5. 세금 신고를 간편하게 하기 위해",
            ],
            "answer": 2,
            "explanation": (
                "에스크로 서비스는 제3의 신뢰 기관이 구매 대금을 일시 보관하다가 "
                "거래가 정상적으로 완료되면 판매자에게 지급하는 방식으로, "
                "구매자와 판매자 간 안전 거래를 보장한다."
            ),
            "source_url": "sample",
        },
    ]


if __name__ == "__main__":
    data = load_sample_data()
    print(json.dumps(data[0], ensure_ascii=False, indent=2))
    print(f"\n총 {len(data)}개 샘플 문제 로드됨")

    # 과목별 분류 확인
    subjects = {}
    for q in data:
        subjects.setdefault(q["subject"], 0)
        subjects[q["subject"]] += 1
    print("\n과목별 문제 수:")
    for subj, cnt in subjects.items():
        print(f"  {subj}: {cnt}문제")
