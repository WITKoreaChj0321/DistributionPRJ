# 🧠 오답 분석팀

## 담당 범위
시험지 이미지 OCR 처리 → 틀린 문제 감지 → 벡터 유사도 검색으로 유사 기출 탐색

## 담당 파일
```
backend/
├── ocr.py        # Google Vision API 기반 OCR 처리
├── analyzer.py   # 오답 감지 및 분석 결과 생성
├── vectordb.py   # ChromaDB 관리 (저장 / 검색)
└── search.py     # 오답 기반 유사 문제 검색 서비스
```

## 처리 파이프라인
```
[업로드 이미지]
      ↓
  OCRProcessor
  - Google Vision API 호출
  - 텍스트 + 위치 정보 추출
  - 오답 표시(X, ×, ✗) 감지
      ↓
  ExamAnalyzer
  - 문제 번호 / 선택 답 파싱
  - 틀린 문제 목록 추출
  - 과목별 약점 분석
      ↓
  SimilarQuestionSearcher
  - 각 오답 텍스트 → 벡터 변환
  - ChromaDB 유사도 검색 (코사인)
  - 문제당 상위 3개 유사 문제 반환
```

## 데이터 클래스

```python
@dataclass
class OCRResult:
    full_text: str
    parsed_questions: list[ParsedQuestion]
    wrong_question_nums: list[int]
    confidence: float

@dataclass
class ParsedQuestion:
    num: int
    text: str
    selected_answer: int
    is_marked_wrong: bool

@dataclass
class WrongQuestion:
    question_num: int
    question_text: str
    selected_answer: int
    correct_answer: int | None
    subject: str

@dataclass
class AnalysisResult:
    total_questions: int
    wrong_questions: list[WrongQuestion]
    subjects_weak: list[str]
```

## OCR 오답 감지 규칙

| 마킹 패턴 | 감지 방법 |
|----------|----------|
| `X` / `/` / `✗` | 텍스트 레이어 패턴 매칭 |
| 빨간 동그라미 | 색상 영역 분석 (Vision API bounding box) |
| 취소선 | 텍스트 위치와 선분 교차 감지 |

## 유사도 검색 설정

| 항목 | 값 |
|------|-----|
| 모델 | `paraphrase-multilingual-MiniLM-L12-v2` |
| 검색 방식 | 코사인 유사도 (1차) + 보기 중복 판단 (2차) |
| 최소 유사도 | 0.5 |
| 문제당 반환 수 | 상위 3개 |
| 같은 과목 우선 | 옵션 지원 |

## 비슷한 유형 판단 기준

5지 선다 보기(①~⑤) 중 **1개 이상 동일한 보기 텍스트가 중복**되는 문제를 "비슷한 유형"으로 분류한다.

### 판단 로직

```
1차 검색: 문제 텍스트 벡터 유사도 (코사인, 임계값 0.5 이상)
      ↓
2차 필터: 보기 중복 검사
  - 후보 문제의 options 리스트와 오답 문제의 options 비교
  - 동일한 보기 문자열이 1개 이상 존재 → 비슷한 유형으로 가중치 부여
  - 중복 보기 수가 많을수록 유사도 점수 보정 (최대 +0.1)
      ↓
최종 정렬: 보정된 유사도 내림차순
```

### 보기 중복 판단 규칙

| 중복 보기 수 | 판단 | 유사도 보정 |
|------------|------|------------|
| 0개 | 유형 무관 | 0 |
| 1개 | 비슷한 유형 | +0.03 |
| 2개 | 유사 유형 | +0.06 |
| 3개 이상 | 매우 유사 유형 | +0.10 |

### 구현 위치

`backend/search.py` — `SimilarQuestionSearcher._search_for_one()` 내 후처리 단계

```python
def _option_overlap_bonus(wrong_opts: list[str], candidate_opts: list[str]) -> float:
    """동일 보기 수에 따른 유사도 보정값 반환."""
    w = {o.strip() for o in wrong_opts if o.strip()}
    c = {o.strip() for o in candidate_opts if o.strip()}
    overlap = len(w & c)
    if overlap == 0: return 0.0
    if overlap == 1: return 0.03
    if overlap == 2: return 0.06
    return 0.10
```

## 클래스 인터페이스

```python
class OCRProcessor:
    async def process_image(image_bytes: bytes) -> OCRResult
    # 폴백: GOOGLE_APPLICATION_CREDENTIALS 없을 시 Mock 반환

class ExamAnalyzer:
    def analyze(ocr_result: OCRResult) -> AnalysisResult

class VectorDBManager:
    async def add_questions(questions: list[dict])
    async def search_similar(query_text: str, n_results: int, subject_filter: str) -> list[dict]
    def get_stats() -> dict

class SimilarQuestionSearcher:
    async def find_similar_for_wrong(wrong_questions: list[WrongQuestion], top_k: int) -> dict[int, list[dict]]
```

## 반환 유사 문제 형식
```json
{
  "id": "2022_2_유통마케팅_12",
  "year": 2022,
  "round": 2,
  "subject": "유통마케팅",
  "question_num": 12,
  "question_text": "다음 중 ...",
  "options": ["1. ...", "2. ...", "3. ...", "4. ...", "5. ..."],
  "answer": 1,
  "explanation": "...",
  "similarity": 0.87
}
```

## 의존성
```
google-cloud-vision
sentence-transformers
chromadb
Pillow, opencv-python-headless
```

## 환경 변수
```
GOOGLE_APPLICATION_CREDENTIALS=./credentials/google_vision.json
```

## 개발 팁
- API 키 없을 때: Mock OCR 결과 반환 (개발/테스트용)
- ChromaDB 경로: `./database/chroma_db` (init_db.py가 먼저 실행되어야 함)
- `vectordb.py`는 서버 시작 시 싱글톤으로 초기화
