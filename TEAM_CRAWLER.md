# 🔍 과년도 문제 서칭 & 업데이트팀

## 담당 범위
유통관리사 10개년 기출문제 수집, 정제, DB 저장, 주기적 업데이트 파이프라인

## 담당 파일
```
crawler/
├── scraper.py          # 메인 크롤러 (공개 기출 사이트)
└── data_processor.py   # 데이터 정제 및 중복 제거

scripts/
├── init_db.py          # DB 최초 초기화 + 데이터 로드
└── update_questions.py # 신규 문제 추가 업데이트
```

## 크롤링 대상

| 사이트 유형 | 대상 데이터 | 비고 |
|------------|------------|------|
| 공개 CBT 사이트 | 유통관리사 2급 기출 | robots.txt 준수 필수 |
| 샘플 데이터 (폴백) | 과목별 5문제씩 | 개발/테스트용 |

> ⚠️ 크롤링 전 반드시 대상 사이트 **robots.txt** 및 **이용약관** 확인

## 유통관리사 2급 과목 구성

| 과목 | 문제 번호 범위 | 문제 수 |
|------|-------------|---------|
| 유통물류일반관리 | 1 ~ 20 | 20문제 |
| 상권분석 | 21 ~ 40 | 20문제 |
| 유통마케팅 | 41 ~ 60 | 20문제 |
| 유통정보 | 61 ~ 80 | 20문제 |

## 데이터 스키마
```python
@dataclass
class QuestionData:
    year: int           # 출제 연도 (2015~2024)
    round: int          # 회차 (1~3)
    subject: str        # 과목명
    question_num: int   # 문제 번호 (1~80)
    question_text: str  # 문제 본문
    options: list[str]  # 보기 5개
    answer: int         # 정답 번호 (1~5)
    explanation: str    # 해설 (있는 경우)
    source_url: str     # 출처 URL
```

## 스크립트 사용법

```bash
# DB 초기화 (샘플 데이터)
python scripts/init_db.py --use-sample

# DB 초기화 (실제 크롤링)
python scripts/init_db.py --crawl 2015 2024

# 신규 문제 업데이트
python scripts/update_questions.py --year 2024
```

## 벡터 DB 구성

| 항목 | 값 |
|------|-----|
| 엔진 | ChromaDB |
| 저장 경로 | `./database/chroma_db` |
| 컬렉션명 | `distribution_exam_questions` |
| 임베딩 모델 | `paraphrase-multilingual-MiniLM-L12-v2` |
| 임베딩 대상 | `질문 텍스트 + 보기 합본` |

## 크롤러 클래스 인터페이스
```python
class DistributionExamCrawler:
    async def crawl_all(start_year: int, end_year: int) -> list[QuestionData]
    async def crawl_year(year: int) -> list[QuestionData]
    # 요청 딜레이: 1.5초, 재시도: 최대 3회

class QuestionProcessor:
    def clean(questions: list[QuestionData]) -> list[QuestionData]
    def deduplicate(questions: list[QuestionData]) -> list[QuestionData]
    def validate(question: QuestionData) -> bool
```

## 의존성
```
chromadb, sentence-transformers
sqlalchemy, aiosqlite
httpx, beautifulsoup4, lxml
tqdm
```

## 주의사항
- `database/models.py`에서 `init_db`, `AsyncSessionLocal` import
- 경로 설정: `sys.path.append(str(Path(__file__).parent.parent))`
- 보기 정규화: `①②③` → `1. 2. 3.` 변환
