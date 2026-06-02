from sqlalchemy import Column, Integer, String, Text, Float, DateTime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from datetime import datetime

DATABASE_URL = "sqlite+aiosqlite:///./database/questions.db"

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


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
    created_at = Column(DateTime, default=datetime.utcnow)

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


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
