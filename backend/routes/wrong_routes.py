"""오답 수집 + 텔레그램 일일 발송 라우트."""
import sys
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from database.models import AsyncSessionLocal, WrongAnswer

router = APIRouter(prefix="/api")


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
    explanation: str = ""


@router.post("/wrong")
async def record_wrong(w: WrongIn) -> dict:
    """퀴즈에서 발생한 오답 1건을 서버에 기록 (프론트가 fire-and-forget 호출)."""
    async with AsyncSessionLocal() as session:
        session.add(WrongAnswer(
            qkey=w.qkey or f"{w.year}|{w.num}",
            subject=w.subject, year=w.year, num=w.num,
            question_text=w.question_text, answer_text=w.answer_text,
            answer_no=w.answer_no or None, chosen_no=w.chosen_no or None,
            img_url=w.img_url or None, explanation=w.explanation or None,
        ))
        await session.commit()
    return {"ok": True}


@router.post("/wrong/send-now")
async def send_now() -> dict:
    """수동 발송 트리거 (테스트용). 미발송 오답을 즉시 집계·전송."""
    from ..scheduler import send_daily_digest
    return await send_daily_digest()


@router.get("/wrong/pending")
async def pending() -> dict:
    """미발송 오답 현황 조회 (읽기 전용, 채널 발송 없음)."""
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        rows = list((await session.execute(
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
