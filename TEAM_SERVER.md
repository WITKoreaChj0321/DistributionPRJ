# ⚙️ 서버팀

## 담당 범위
FastAPI REST API 서버 구축, 카카오 OAuth 및 친구에게 보내기 API 연동

## 담당 파일
```
backend/
├── main.py                  # FastAPI 앱 진입점
├── config.py                # 환경변수 설정 (pydantic-settings)
├── kakao.py                 # 카카오 API 클라이언트
└── routes/
    ├── __init__.py
    ├── analyze.py           # 이미지 분석 엔드포인트
    └── kakao_routes.py      # 카카오 OAuth + 전송 엔드포인트
```

## API 명세

### 분석 API
| 메서드 | 경로 | 설명 | 요청 | 응답 |
|--------|------|------|------|------|
| POST | `/api/analyze` | 이미지 업로드 + 분석 시작 | `multipart/form-data` | `{task_id, status}` |
| GET | `/api/result/{task_id}` | 분석 결과 조회 | - | `{status, wrong_questions, similar_questions}` |

### 카카오 API
| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/auth/kakao` | 카카오 OAuth 로그인 시작 |
| GET | `/auth/kakao/callback` | OAuth 콜백 (token 발급) |
| GET | `/api/kakao/friends` | 친구 목록 조회 |
| POST | `/api/send-kakao` | 친구에게 분석 결과 전송 |

## 분석 태스크 상태 흐름
```
POST /api/analyze
    → task_id 생성
    → BackgroundTask 등록 (OCR → 분석 → 검색)
    → {"task_id": "uuid", "status": "processing"}

GET /api/result/{task_id}
    → "processing" | "done" | "error"
    → done: 전체 결과 반환
```

## 카카오 OAuth 플로우
```
[클라이언트] → GET /auth/kakao
    → 302 redirect to kauth.kakao.com/oauth/authorize
        ?client_id={REST_API_KEY}
        &redirect_uri={REDIRECT_URI}
        &response_type=code
        &scope=friends,talk_message

[카카오] → GET /auth/kakao/callback?code=xxx
    → POST kauth.kakao.com/oauth/token (코드 교환)
    → 302 redirect to /?token={access_token}

[클라이언트] → GET /api/kakao/friends?token=xxx
    → GET kapi.kakao.com/v1/api/talk/friends

[클라이언트] → POST /api/send-kakao
    body: {task_id, friend_uuid, token}
    → POST kapi.kakao.com/v1/api/talk/friends/message/send
```

## 카카오 메시지 템플릿 (Feed 타입)
```json
{
  "object_type": "feed",
  "content": {
    "title": "📚 유통관리사 오답 분석 결과",
    "description": "틀린 문제: 5, 12, 23번 | 유사 문제 9개",
    "link": { "web_url": "", "mobile_web_url": "" }
  },
  "buttons": [
    { "title": "Q.12 [유통마케팅] SCM의 목적은?", "link": {...} }
  ]
}
```

## 환경변수 (`.env`)
```env
GOOGLE_APPLICATION_CREDENTIALS=./credentials/google_vision.json
KAKAO_REST_API_KEY=your_rest_api_key
KAKAO_REDIRECT_URI=http://localhost:8000/auth/kakao/callback
SECRET_KEY=your_secret_key
DEBUG=true
```

## 카카오 개발자 앱 설정 체크리스트
- [ ] [developers.kakao.com](https://developers.kakao.com) 앱 등록
- [ ] REST API 키 발급
- [ ] 리다이렉트 URI 등록: `http://localhost:8000/auth/kakao/callback`
- [ ] 동의항목 → `friends`, `talk_message` 활성화
- [ ] 테스트 친구 등록 (개발 단계에서 필수)

## 서버 실행
```bash
cd C:/APP_Workspace/유통관리사-helper
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

## 의존성
```
fastapi, uvicorn[standard]
python-multipart
httpx
pydantic-settings
python-jose[cryptography]
```

## 아키텍처 연결도
```
main.py
  ├── routes/analyze.py   →  backend/ocr.py
  │                       →  backend/analyzer.py
  │                       →  backend/search.py
  │                       →  backend/vectordb.py
  │
  └── routes/kakao_routes.py  →  backend/kakao.py
                               →  backend/config.py
```
