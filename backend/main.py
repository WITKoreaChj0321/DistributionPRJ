import os
import warnings
from contextlib import asynccontextmanager
from pathlib import Path

# ChromaDB 텔레메트리 및 HuggingFace 심링크 경고 억제
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
warnings.filterwarnings("ignore", category=UserWarning, module="huggingface_hub")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .routes.analyze import router as analyze_router
from .routes.kakao_routes import router as kakao_router
from .routes.wrong_routes import router as wrong_router

# 프로젝트 루트 (backend/ 의 부모)
BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    import sys

    sys.path.insert(0, str(BASE_DIR))

    # SQLite 테이블 생성
    from database.models import init_db
    await init_db()

    # ChromaDB가 비어있으면 샘플 데이터 자동 시딩
    from .vectordb import VectorDBManager
    from crawler.scraper import load_sample_data
    from crawler.data_processor import QuestionProcessor

    vector_db = VectorDBManager()
    stats = vector_db.get_stats()
    if stats.get("total_questions", 0) == 0:
        raw = load_sample_data()
        processor = QuestionProcessor(verbose=False)
        questions = processor.process(raw)
        await vector_db.add_questions(questions)

    # 텔레그램 일일 오답 발송 스케줄러 (18시 KST)
    from .scheduler import start_scheduler, shutdown_scheduler
    start_scheduler()

    yield

    shutdown_scheduler()


app = FastAPI(
    title="유통관리사 오답 분석기",
    version="1.0.0",
    debug=settings.debug,
    lifespan=lifespan,
)

# ──────────────────────────────────────────────
# CORS
# ──────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.debug else ["http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ──────────────────────────────────────────────
# 라우터 등록
# ──────────────────────────────────────────────
app.include_router(analyze_router)
app.include_router(kakao_router)
app.include_router(wrong_router)

# ──────────────────────────────────────────────
# 정적 파일 (frontend/)
# ──────────────────────────────────────────────
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/", include_in_schema=False)
async def root():
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {"message": "유통관리사 오답 분석기 API가 실행 중입니다."}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
