from pathlib import Path
from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from datetime import datetime, timezone

# 절대 경로: database/questions.db (실행 위치와 무관)
_DB_PATH = Path(__file__).resolve().parent / "questions.db"
DATABASE_URL = f"sqlite+aiosqlite:///{_DB_PATH}"

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Question(Base):
    __tablename__ = "questions"

    id = Column(Integer, primary_key=True, index=True)
    year = Column(Integer, nullable=False, index=True)           # 연도
    round = Column(Integer, nullable=False)                       # 회차
    subject = Column(String(100), nullable=False, index=True)     # 과목
    question_num = Column(Integer, nullable=False)                # 문제 번호
    question_text = Column(Text, nullable=False)                  # 문제 본문
    option_1 = Column(Text)
    option_2 = Column(Text)
    option_3 = Column(Text)
    option_4 = Column(Text)
    option_5 = Column(Text)
    answer = Column(Integer, nullable=False)                      # 정답 번호
    explanation = Column(Text)                                    # 해설
    source_url = Column(String(500))
    chroma_id = Column(String(100), unique=True)                  # ChromaDB 연동 ID
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "year": self.year,
            "round": self.round,
            "subject": self.subject,
            "question_num": self.question_num,
            "question_text": self.question_text,
            "options": [
                self.option_1, self.option_2, self.option_3,
                self.option_4, self.option_5
            ],
            "answer": self.answer,
            "explanation": self.explanation,
        }


class WrongAnswer(Base):
    """퀴즈에서 발생한 오답 기록 (텔레그램 일일 발송용)."""
    __tablename__ = "wrong_answers"

    id = Column(Integer, primary_key=True, index=True)
    qkey = Column(String(50), index=True)        # "2020년 1회|8" 형태 문제 식별자
    subject = Column(String(100))
    year = Column(String(30))                    # "2020년 1회"
    num = Column(Integer)
    question_text = Column(Text)
    answer_text = Column(Text)                    # 정답 보기 내용
    answer_no = Column(Integer)                   # 정답 번호(1~5)
    chosen_no = Column(Integer)                   # 사용자가 고른 번호
    img_url = Column(String(500))                 # 글상자 이미지 절대 URL (있으면)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    sent_at = Column(DateTime, nullable=True)     # 텔레그램 발송 완료 시각

    def to_dict(self) -> dict:
        return {
            "id": self.id, "qkey": self.qkey, "subject": self.subject,
            "year": self.year, "num": self.num, "question_text": self.question_text,
            "answer_text": self.answer_text, "answer_no": self.answer_no,
            "chosen_no": self.chosen_no, "img_url": self.img_url,
        }


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_question(year: int, round_: int, num: int) -> "Question | None":
    """연도+회차+번호로 문제 조회. 연도/회차가 0이면 해당 조건 무시."""
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        stmt = select(Question).where(Question.question_num == num)
        if year:
            stmt = stmt.where(Question.year == year)
        if round_:
            stmt = stmt.where(Question.round == round_)
        result = await session.execute(stmt)
        return result.scalars().first()
