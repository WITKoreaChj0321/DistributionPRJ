# 유통관리사 기출 퀴즈 — 작업 현황 / 이어가기 문서

> 최종 업데이트: 2026-06-20
> 저장소: https://github.com/WITKoreaChj0321/DistributionPRJ (branch `main`)

---

## 1. 한눈에 보기 (현재 완성된 것)

```
누구나 → https://witkoreachj0321.github.io/DistributionPRJ/  (웹 퀴즈, GitHub Pages)
            │  오답 발생 시 자동 전송
            ▼
        https://distributionprj.onrender.com/api/wrong       (Render 클라우드 백엔드)
            │  매일 18:00 KST 집계
            ▼
        텔레그램 @licencedistribute 채널 자동 발송
```

**3대 기능 모두 완료·프로덕션 검증됨:**
1. **객관식 퀴즈** — 1,105문제, 즉시 정답/오답 판별, 해설, 셔플
2. **글상자 이미지 복원** — 원본 PDF에서 글상자/그림을 잘라 230문제에 표시 (`docs/boxes/`)
3. **오답 텔레그램 발송** — 웹 오답 → 클라우드 수집 → 매일 18시 채널 발송

---

## 2. 배포 정보

| 항목 | 값 |
|---|---|
| **웹(프론트)** | GitHub Pages, `/docs` 폴더 → https://witkoreachj0321.github.io/DistributionPRJ/ |
| **백엔드(클라우드)** | Render 무료, `telegram_service/` → https://distributionprj.onrender.com |
| **텔레그램 봇** | `@licence_distribute_bot` (이름: 유통관리사 오답봇) |
| **채널** | `@licencedistribute` (봇이 관리자=게시권한 보유) |
| **Python(배포)** | 3.12.8 고정 (`PYTHON_VERSION` 환경변수) — 3.14는 greenlet 빌드 실패 |

### Render 환경변수 (대시보드 Environment 탭)
- `TELEGRAM_BOT_TOKEN` = (BotFather 토큰, **비밀** — 코드/문서에 미기재, 로컬은 `.env`)
- `TELEGRAM_CHANNEL` = `@licencedistribute`
- `ALLOW_ORIGINS` = `https://witkoreachj0321.github.io`
- `PYTHON_VERSION` = `3.12.8`

### Render 서비스 설정
- Root Directory: `telegram_service`
- Build: `pip install -r requirements.txt`
- Start: `uvicorn app:app --host 0.0.0.0 --port $PORT`
- Instance: Free

---

## 3. 백엔드 API (telegram_service)

| 메서드 | 경로 | 설명 |
|---|---|---|
| POST | `/api/wrong` | 오답 1건 수집 (퀴즈가 fire-and-forget 호출) |
| POST | `/api/wrong/send-now` | 미발송 오답 즉시 집계·채널 발송 |
| GET | `/api/wrong/pending` | 미발송 오답 현황 조회 (읽기전용, 발송 X) |
| GET | `/health` | 헬스체크 (keep-alive 핑용) |
| GET | `/` | 서비스 설정 정보 |

---

## 4. 주요 파일 맵

### 웹 퀴즈 (배포 대상)
- `docs/index.html` — **단일 파일 퀴즈** (QUIZ_DATA 1,105문제 인라인). `API_BASE`가 Render 주소로 설정됨. `boxes/` 이미지 상대참조.
- `docs/boxes/*.png` — 글상자/그림 이미지 340개 (230문제 연결)

### 클라우드 백엔드 (배포 대상)
- `telegram_service/app.py` — 경량 FastAPI (수집+18시 스케줄러+텔레그램), AI 라이브러리 없음
- `telegram_service/requirements.txt` — 가벼운 의존성 (+greenlet==3.1.1)
- `telegram_service/runtime.txt` — `python-3.12.8`
- `telegram_service/render.yaml` — Render 블루프린트
- `telegram_service/README.md` — 배포 단계별 가이드

### 무거운 풀 백엔드 (미배포, 참고용)
- `backend/` — FastAPI + ChromaDB/torch (오답 벡터분석 등). 텔레그램 기능도 들어있으나 무거워서 배포엔 `telegram_service` 사용.
  - `backend/telegram.py`, `backend/scheduler.py`, `backend/routes/wrong_routes.py`, `database/models.py`(WrongAnswer)

### 데이터 생성 스크립트 (재사용)
- `scripts/enrich_frequent.py` — frequent.json에 보기/정답/해설 보강
- `scripts/extract_boxes.py` — PDF에서 글상자 이미지 추출 → `docs/boxes/`
- `scripts/inject_boxes.py` — QUIZ_DATA에 이미지 경로 주입
- `scripts/box_map.json` — (year|num) → 이미지 매핑
- 원본 PDF: `data/questions/유통관리사2급YYYYMMDD(교사용).pdf` (17개)

### 비밀/런타임 (git 제외됨)
- `.env` — 카카오/텔레그램 토큰 (gitignore)
- `database/questions.db`, `telegram_service/wrongs.db` — 런타임 DB (gitignore)

---

## 5. 운영 방법

- **평소엔 손댈 것 없음.** 웹에서 풀면 자동 수집, 매일 18시 자동 발송.
- **수집 확인**: `GET https://distributionprj.onrender.com/api/wrong/pending` → 미발송 개수/목록
- **즉시 발송(수동)**: `POST https://distributionprj.onrender.com/api/wrong/send-now`
- **발송 시각 변경**: Render 환경변수 `TELEGRAM_DAILY_HOUR`/`_MINUTE` 추가
- 이미 발송된 오답은 `sent_at` 표시 → 재발송 안 함. 매일 "새로 쌓인 것"만 나감.

### 로컬 개발 (선택)
```
# 경량 백엔드 로컬 실행
cd telegram_service
TELEGRAM_BOT_TOKEN=... uvicorn app:app --port 8002

# 웹을 로컬 서버로 (file:// 말고 http 권장)
cd docs && python -m http.server 8001   # http://localhost:8001/
# 이때 docs/index.html의 API_BASE를 로컬 백엔드로 바꿔야 수집됨 (배포시 원복 필수!)
```

---

## 6. 남은 작업 / TODO

- [ ] **UptimeRobot keep-alive (중요·미완)** — 무료 Render는 15분 무요청 시 잠듦 → 18시 발송 누락 + SQLite 초기화 위험.
      https://uptimerobot.com → HTTP(s) 모니터, URL `https://distributionprj.onrender.com/health`, 5분 간격.
- [ ] (선택) **영구 DB** — 무료플랜 SQLite는 재배포/잠자기 시 초기화. 데이터 보존 필요하면 Render 무료 PostgreSQL 연결(`DATABASE_URL`, asyncpg).
- [ ] (선택) **누락 문제 109개 복원** — 원본 크롤이 파싱 못 한 글상자/이미지 문제는 QUIZ_DATA(1,105)에 아예 없음. PDF에서 문제 전체 재추출 시 복원 가능(별도 큰 작업).
- [ ] (선택) **글상자 텍스트화** — 현재 글상자는 이미지 표시(검색·복사 불가). 필요시 구글 비전 OCR로 텍스트화.

---

## 7. 중요 메모 / 주의사항 (gotchas)

1. **배포 전 `docs/index.html`의 `API_BASE` 확인** — 로컬 테스트로 `localhost`로 바꿨다면 배포 시 반드시 `https://distributionprj.onrender.com`으로 원복(또는 push 전 확인). 빈 문자열이면 수집 비활성.
2. **Render는 Python 3.12.8 고정 필수** — 기본 3.14에선 `greenlet`(SQLAlchemy 비동기 필수) 빌드 실패. `PYTHON_VERSION=3.12.8` 환경변수로 해결됨.
3. **봇 토큰은 비밀** — `.env`/Render 환경변수에만. 코드·문서·깃에 넣지 말 것. 노출 시 BotFather `/revoke`로 재발급.
4. **'나에게 보내기' vs '채널 발송'** — 채널 발송은 봇이 채널 관리자여야 함(완료됨). 개인이 자기 텔레그램으로 받는 건 `docs`의 `t.me/share` 공유버튼(봇 불필요).
5. **`file://`로 연 퀴즈는 서버 수집이 막힐 수 있음** — http(배포주소 또는 localhost:8001)로 열어야 fetch 정상.
6. **무료 Render 콜드스타트** — 잠든 뒤 첫 요청은 최대 ~50초 지연. UptimeRobot으로 완화.
7. **`docs/`가 GitHub Pages 소스** — Settings→Pages가 `main` / `/docs`로 설정돼 있어야 함. 루트 리다이렉트는 제거됨(docs가 사이트 루트).

---

## 8. 데이터 현황 메모

- QUIZ_DATA: **1,105문제** (정원 1,530 대비 부족 — 원본 크롤이 글상자/이미지 문제 일부 누락)
- 글상자 이미지 연결: **230문제** (`docs/boxes/`, 340개 이미지)
- 보기 병합 깨짐 보정: 로드 시 `normalizeMergedOptions()`가 205문제 자동 분리
- 손상 데이터 3문제(질문↔정답 불일치)는 퀴즈에서 제외
- 회차 매핑: 월 기준(5~6월=1회, 7~8월=2회, 9~12월=3회), 17개 PDF 전부 QUIZ_DATA와 본문 일치 검증됨
