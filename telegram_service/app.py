"""
유통관리사 오답 수집 + 텔레그램 일일 발송 — 경량 백엔드 (클라우드 배포용).

무거운 AI 라이브러리 없이 다음만 수행:
  - POST /api/wrong          : 퀴즈 오답 1건 수집
  - POST /api/wrong/send-now : 미발송 오답 즉시 집계·발송 (외부 cron이 18시에 호출 가능)
  - GET  /health             : 헬스체크 (UptimeRobot keep-alive용)
  - 내장 스케줄러             : 매일 18시(KST) 자동 발송 (always-on 환경에서 동작)

환경변수:
  TELEGRAM_BOT_TOKEN  (필수)   @BotFather 토큰
  TELEGRAM_CHANNEL    (@licencedistribute)
  TELEGRAM_DAILY_HOUR (18) / TELEGRAM_DAILY_MINUTE (0) / TELEGRAM_TIMEZONE (Asia/Seoul)
  ALLOW_ORIGINS       (*)       쉼표구분. 예: https://witkoreachj0321.github.io
  DATABASE_URL        (sqlite+aiosqlite:///./wrongs.db)
"""
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import Column, Integer, String, Text, DateTime, select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# ── 설정 (환경변수) ─────────────────────────────
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHANNEL = os.environ.get("TELEGRAM_CHANNEL", "@licencedistribute")
HOUR = int(os.environ.get("TELEGRAM_DAILY_HOUR", "18"))
MINUTE = int(os.environ.get("TELEGRAM_DAILY_MINUTE", "0"))
TZ = os.environ.get("TELEGRAM_TIMEZONE", "Asia/Seoul")
ALLOW_ORIGINS = [o.strip() for o in os.environ.get("ALLOW_ORIGINS", "*").split(",") if o.strip()]
DB_URL = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./wrongs.db")

_CIRCLE = {1: "①", 2: "②", 3: "③", 4: "④", 5: "⑤"}
_TG_LIMIT = 4000

# ── DB ──────────────────────────────────────────
class Base(DeclarativeBase):
    pass

class WrongAnswer(Base):
    __tablename__ = "wrong_answers"
    id = Column(Integer, primary_key=True, index=True)
    qkey = Column(String(50), index=True)
    subject = Column(String(100))
    year = Column(String(30))
    num = Column(Integer)
    question_text = Column(Text)
    answer_text = Column(Text)
    answer_no = Column(Integer)
    chosen_no = Column(Integer)
    img_url = Column(String(500))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    sent_at = Column(DateTime, nullable=True)

engine = create_async_engine(DB_URL)
Session = async_sessionmaker(engine, expire_on_commit=False)

# ── 텔레그램 ────────────────────────────────────
def _chunks(text: str, size: int = _TG_LIMIT) -> list[str]:
    out, cur = [], ""
    for line in text.split("\n"):
        if len(cur) + len(line) + 1 > size:
            if cur:
                out.append(cur)
            cur = line
        else:
            cur = f"{cur}\n{line}" if cur else line
    if cur:
        out.append(cur)
    return out or [""]

async def tg_send(text: str) -> dict:
    if not BOT_TOKEN:
        return {"ok": False, "error": "TELEGRAM_BOT_TOKEN 미설정"}
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    sent = 0
    async with httpx.AsyncClient(timeout=15) as client:
        for part in _chunks(text):
            r = await client.post(url, json={"chat_id": CHANNEL, "text": part})
            data = r.json()
            if not data.get("ok"):
                return {"ok": False, "error": data, "sent": sent}
            sent += 1
    return {"ok": True, "sent": sent}

# ── 집계·발송 ───────────────────────────────────
def _format_digest(rows: list[WrongAnswer]) -> str:
    agg: dict[str, dict] = {}
    for r in rows:
        a = agg.setdefault(r.qkey, {"row": r, "count": 0})
        a["count"] += 1
    items = sorted(agg.values(), key=lambda x: x["count"], reverse=True)
    today = datetime.now().strftime("%Y-%m-%d")
    blocks = [f"📚 유통관리사 오늘의 오답 정리 ({today})\n총 {len(items)}문제 · 오답 {len(rows)}건\n"]
    for i, it in enumerate(items, 1):
        r: WrongAnswer = it["row"]
        circle = _CIRCLE.get(r.answer_no or 0, str(r.answer_no or ""))
        block = (f"\n{i}. [{r.subject}] {r.year} {r.num}번 · {it['count']}회 오답\n"
                 f"Q. {(r.question_text or '').strip()}\n"
                 f"✅ 정답 {circle} {r.answer_text or ''}")
        if r.img_url:
            block += f"\n📷 글상자: {r.img_url}"
        blocks.append(block)
    return "\n".join(blocks)

async def send_daily_digest() -> dict:
    async with Session() as s:
        rows = list((await s.execute(
            select(WrongAnswer).where(WrongAnswer.sent_at.is_(None)))).scalars().all())
        if not rows:
            return {"ok": True, "sent": 0, "message": "발송할 오답 없음"}
        res = await tg_send(_format_digest(rows))
        if not res.get("ok"):
            return {"ok": False, "error": res.get("error"), "count": len(rows)}
        now = datetime.now(timezone.utc)
        for r in rows:
            r.sent_at = now
        await s.commit()
        return {"ok": True, "questions": len(set(r.qkey for r in rows)),
                "records": len(rows), "telegram": res}

# ── 스케줄러 + 앱 ───────────────────────────────
_scheduler: AsyncIOScheduler | None = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _scheduler
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    _scheduler = AsyncIOScheduler(timezone=TZ)
    _scheduler.add_job(send_daily_digest,
                       CronTrigger(hour=HOUR, minute=MINUTE, timezone=TZ),
                       id="daily_wrong_digest", replace_existing=True)
    _scheduler.start()
    print(f"[scheduler] 매일 {HOUR:02d}:{MINUTE:02d} {TZ} → {CHANNEL}")
    yield
    if _scheduler:
        _scheduler.shutdown(wait=False)

app = FastAPI(title="유통관리사 오답 발송 서비스", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOW_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

class WrongIn(BaseModel):
    qkey: str = ""
    subject: str = ""
    year: str = ""
    num: int = 0
    question_text: str = ""
    answer_text: str = ""
    answer_no: int = 0
    chosen_no: int = 0
    img_url: str = ""

@app.get("/")
async def root():
    return {"service": "유통관리사 오답 발송", "channel": CHANNEL,
            "daily": f"{HOUR:02d}:{MINUTE:02d} {TZ}"}

@app.get("/health")
async def health():
    return {"ok": True}

@app.post("/api/wrong")
async def record_wrong(w: WrongIn):
    async with Session() as s:
        s.add(WrongAnswer(
            qkey=w.qkey or f"{w.year}|{w.num}", subject=w.subject, year=w.year,
            num=w.num, question_text=w.question_text, answer_text=w.answer_text,
            answer_no=w.answer_no or None, chosen_no=w.chosen_no or None,
            img_url=w.img_url or None))
        await s.commit()
    return {"ok": True}

@app.post("/api/wrong/send-now")
async def send_now():
    return await send_daily_digest()

@app.get("/api/wrong/pending")
async def pending():
    """미발송 오답 현황 조회 (읽기 전용, 채널 발송 없음)."""
    async with Session() as s:
        rows = list((await s.execute(
            select(WrongAnswer).where(WrongAnswer.sent_at.is_(None))
            .order_by(WrongAnswer.id.desc()))).scalars().all())
    return {
        "ok": True,
        "pending": len(rows),
        "questions": len(set(r.qkey for r in rows)),
        "items": [{"year": r.year, "num": r.num, "subject": r.subject,
                   "chosen_no": r.chosen_no, "answer_no": r.answer_no,
                   "q": (r.question_text or "")[:40]} for r in rows[:50]],
    }
