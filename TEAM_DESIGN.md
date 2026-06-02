# 🎨 디자인팀

## 담당 범위
사용자가 시험지를 업로드하고 결과를 확인하는 전체 프론트엔드 UI/UX

## 담당 파일
```
frontend/
├── index.html     # 메인 페이지 (업로드 → 결과 표시)
├── style.css      # 전체 스타일 (반응형, 모바일 우선)
└── app.js         # UI 인터랙션 + API 통신 로직
```

## 화면 구성

### 1. 헤더
- 서비스명: **유통관리사 오답 분석기**
- 서브타이틀: 촬영 → 분석 → 카카오톡 전송 3단계 안내

### 2. 업로드 섹션
- 드래그&드롭 + 클릭 업로드 영역
- 업로드 후 이미지 미리보기
- "분석 시작" 버튼

### 3. 카카오 연동 섹션
- 카카오 로그인 버튼 (FEE500 노란색)
- 로그인 후 친구 선택 드롭다운

### 4. 결과 섹션
- 분석 중 프로그레스 바 + 로딩 애니메이션
- 오답 문제 목록 카드
- 유사 기출문제 카드 (연도, 과목, 유사도 표시)
- "카카오톡으로 전송" 버튼

## 디자인 시스템

| 항목 | 값 |
|------|-----|
| 메인 컬러 | `#3F51B5` (인디고) |
| 포인트 컬러 | `#FEE500` (카카오 노랑) |
| 성공 | `#4CAF50` |
| 경고/오답 | `#F44336` |
| 폰트 | Noto Sans KR |
| 카드 radius | 12px |
| 그림자 | `0 2px 8px rgba(0,0,0,0.12)` |

## API 연동 목록

| 메서드 | 엔드포인트 | 설명 |
|--------|-----------|------|
| POST | `/api/analyze` | 이미지 업로드 → task_id 반환 |
| GET | `/api/result/{task_id}` | 분석 결과 폴링 |
| GET | `/auth/kakao` | 카카오 OAuth 시작 |
| GET | `/api/kakao/friends` | 친구 목록 조회 |
| POST | `/api/send-kakao` | 친구에게 결과 전송 |

## 결과 데이터 구조
```json
{
  "status": "done",
  "wrong_questions": [
    { "question_num": 5, "question_text": "...", "selected_answer": 3, "correct_answer": 1 }
  ],
  "similar_questions": [
    {
      "year": 2022, "round": 2, "subject": "유통마케팅",
      "question_num": 12, "question_text": "...",
      "options": ["1. ...", "2. ...", "3. ...", "4. ...", "5. ..."],
      "answer": 1, "explanation": "...", "similarity": 0.87
    }
  ]
}
```

## 개발 가이드
- `app.js`에서 `BASE_URL = "http://localhost:8000"` 설정
- 분석 상태 폴링: 1초 간격, 최대 60초
- 에러 시 토스트 메시지로 안내
- 카카오 token은 URL 쿼리파라미터로 받아 메모리에 저장
