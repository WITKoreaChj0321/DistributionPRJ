"""APScheduler: 매일 18시(KST) 미발송 오답을 집계해 텔레그램 채널로 발송."""
import sys
from datetime import datetime, timezone
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.models import AsyncSessionLocal, WrongAnswer
from .config import settings
from .telegram import send_message

_CIRCLE = {1: "①", 2: "②", 3: "③", 4: "④", 5: "⑤"}
_scheduler: AsyncIOScheduler | None = None


def _format_digest(rows: list[WrongAnswer]) -> str:
    """미발송 오답을 문제별로 집계(중복=오답 횟수)해 메시지 생성."""
    # qkey 기준 집계
    agg: dict[str, dict] = {}
    for r in rows:
        a = agg.setdefault(r.qkey, {"row": r, "count": 0})
        a["count"] += 1
    items = sorted(agg.values(), key=lambda x: x["count"], reverse=True)

    today = datetime.now().strftime("%Y-%m-%d")
    head = f"📚 유통관리사 오늘의 오답 정리 ({today})\n총 {len(items)}문제 · 오답 {len(rows)}건\n"
    blocks = [head]
    for i, it in enumerate(items, 1):
        r: WrongAnswer = it["row"]
        circle = _CIRCLE.get(r.answer_no or 0, str(r.answer_no or ""))
        block = (
            f"\n{i}. [{r.subject}] {r.year} {r.num}번 · {it['count']}회 오답\n"
            f"Q. {(r.question_text or '').strip()}\n"
            f"✅ 정답 {circle} {r.answer_text or ''}"
        )
        if r.img_url:
            block += f"\n📷 글상자: {r.img_url}"
        if r.explanation:
            exp = r.explanation.strip()
            block += f"\n📝 {exp[:200] + '…' if len(exp) > 200 else exp}"
        blocks.append(block)
    return "\n".join(blocks)


async def send_daily_digest() -> dict:
    """미발송 오답을 집계·발송하고 sent_at 표시."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(WrongAnswer).where(WrongAnswer.sent_at.is_(None))
        )
        rows = list(result.scalars().all())
        if not rows:
            return {"ok": True, "sent": 0, "message": "발송할 오답 없음"}

        text = _format_digest(rows)
        res = await send_message(text)
        if not res.get("ok"):
            return {"ok": False, "error": res.get("error"), "count": len(rows)}

        now = datetime.now(timezone.utc)
        for r in rows:
            r.sent_at = now
        await session.commit()
        return {"ok": True, "questions": len(set(r.qkey for r in rows)),
                "records": len(rows), "telegram": res}


def start_scheduler() -> None:
    global _scheduler
    if _scheduler:
        return
    _scheduler = AsyncIOScheduler(timezone=settings.telegram_timezone)
    _scheduler.add_job(
        send_daily_digest,
        CronTrigger(hour=settings.telegram_daily_hour,
                    minute=settings.telegram_daily_minute,
                    timezone=settings.telegram_timezone),
        id="daily_wrong_digest",
        replace_existing=True,
    )
    _scheduler.start()
    print(f"[scheduler] 매일 {settings.telegram_daily_hour:02d}:"
          f"{settings.telegram_daily_minute:02d} {settings.telegram_timezone} "
          f"오답 발송 → {settings.telegram_channel}")


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
