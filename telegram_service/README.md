# 유통관리사 오답 발송 서비스 (경량 백엔드)

웹 퀴즈에서 발생한 오답을 수집하고, **매일 18시(KST)** `@licencedistribute` 채널로 자동 발송합니다.
무거운 AI 라이브러리 없이 가벼워서 무료 클라우드(Render 등)에 바로 배포됩니다.

## 엔드포인트
| 메서드 | 경로 | 설명 |
|---|---|---|
| POST | `/api/wrong` | 오답 1건 수집 (퀴즈가 호출) |
| POST | `/api/wrong/send-now` | 미발송 오답 즉시 집계·발송 (외부 cron이 18시에 호출 가능) |
| GET | `/health` | 헬스체크 (keep-alive 핑용) |

## 환경변수
| 키 | 필수 | 기본값 | 설명 |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | ✅ | — | @BotFather 토큰 |
| `TELEGRAM_CHANNEL` | | `@licencedistribute` | 발송 채널 |
| `TELEGRAM_TIMEZONE` | | `Asia/Seoul` | 발송 기준 시간대 |
| `TELEGRAM_DAILY_HOUR` / `_MINUTE` | | `18` / `0` | 발송 시각 |
| `ALLOW_ORIGINS` | | `*` | CORS 허용 도메인 (예: `https://witkoreachj0321.github.io`) |
| `DATABASE_URL` | | sqlite | 영구 DB 쓰려면 Postgres URL 지정 |

---

## Render 무료 배포 (단계별)

### 1. Render 가입
- https://render.com → **GitHub로 가입/로그인** → 이 저장소(`DistributionPRJ`) 접근 허용

### 2. 웹 서비스 생성
- 대시보드 → **New + → Web Service**
- 저장소 `DistributionPRJ` 선택
- 설정 입력:
  | 항목 | 값 |
  |---|---|
  | **Root Directory** | `telegram_service` |
  | **Runtime** | Python 3 |
  | **Build Command** | `pip install -r requirements.txt` |
  | **Start Command** | `uvicorn app:app --host 0.0.0.0 --port $PORT` |
  | **Instance Type** | Free |

### 3. 환경변수 입력 (Environment 탭)
- `TELEGRAM_BOT_TOKEN` = (BotFather 토큰)
- `TELEGRAM_CHANNEL` = `@licencedistribute`
- `ALLOW_ORIGINS` = `https://witkoreachj0321.github.io`

### 4. 배포 → 주소 확인
- **Create Web Service** → 빌드 완료되면 주소가 생깁니다:
  `https://distribution-wrong-bot.onrender.com` (예시)
- 브라우저로 `그-주소/health` 열어 `{"ok":true}` 확인

### 5. 퀴즈 연결
- `docs/index.html`의 `const API_BASE = ''` 를 위 주소로 변경:
  ```js
  const API_BASE = 'https://distribution-wrong-bot.onrender.com';
  ```
- 커밋·푸시 → GitHub Pages 퀴즈가 오답을 이 서버로 보냄

---

## ⚠️ 무료 플랜 주의 — 잠자기(sleep)
Render 무료 웹서비스는 **15분간 요청이 없으면 잠들고, 그동안 18시 스케줄러도 안 돕니다.**
또한 잠들었다 깨면 SQLite 데이터가 초기화될 수 있습니다. 해결책:

### 방법 A. 깨어있게 유지 (권장, 간단)
- **UptimeRobot**(무료, https://uptimerobot.com)에서 **5분마다 `/health` 핑** 설정
  → 서버가 항상 깨어 있어 데이터 유지 + 18시 내장 스케줄러 정상 작동

### 방법 B. 외부 cron으로 18시에 직접 호출
- **cron-job.org**(무료)에서 매일 18:00 KST에
  `POST https://그-주소/api/wrong/send-now` 호출
  (이러면 그 순간 서버를 깨우며 발송)
- 단, 이 경우에도 낮 동안 수집 데이터 유지를 위해 방법 A 핑을 같이 쓰는 게 안전

### 영구 데이터가 꼭 필요하면
- Render 무료 **PostgreSQL** 생성 → `DATABASE_URL`에 연결(asyncpg URL)
  → 재배포·잠자기와 무관하게 데이터 보존
