"""
유통관리사 기출문제 DB 초기화 및 데이터 로드 스크립트

사용법:
    python scripts/init_db.py --use-sample          # 샘플 데이터로 초기화
    python scripts/init_db.py --crawl 2015 2024     # 실제 크롤링 후 초기화
"""
import argparse
import asyncio
import sys
import uuid
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

import chromadb
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

from database.models import Question, init_db, AsyncSessionLocal
from crawler.scraper import DistributionExamCrawler, load_sample_data
from crawler.data_processor import QuestionProcessor

# ──────────────────────────────────────────────
# 설정
# ──────────────────────────────────────────────
EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
CHROMA_COLLECTION = "distribution_exam_questions"
CHROMA_PATH = str(Path(__file__).parent.parent / "database" / "chroma_db")


def _build_embedding_text(q: dict) -> str:
    """ChromaDB에 저장할 임베딩용 텍스트 구성."""
    parts = [q.get("question_text", "")]
    for opt in q.get("options", []):
        if opt:
            parts.append(opt)
    if q.get("explanation"):
        parts.append(q["explanation"])
    return " | ".join(p for p in parts if p)


def _make_chroma_id(q: dict) -> str:
    """ChromaDB 문서 ID 생성 (연도-회차-번호 기반, 없으면 UUID)."""
    year = q.get("year", 0)
    round_ = q.get("round", 0)
    q_num = q.get("question_num", 0)
    if year and round_ and q_num:
        return f"dist_{year}_{round_}_{q_num:03d}"
    return f"dist_{uuid.uuid4().hex[:12]}"


def init_chroma() -> chromadb.Collection:
    """ChromaDB 클라이언트 및 컬렉션 초기화."""
    Path(CHROMA_PATH).mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    # 이미 존재하면 가져오고, 없으면 생성
    collection = client.get_or_create_collection(
        name=CHROMA_COLLECTION,
        metadata={"hnsw:space": "cosine"},
    )
    return collection


_SQLITE_BATCH = 100


async def save_to_sqlite(questions: list[dict]) -> int:
    """SQLite에 문제 메타데이터 저장. 저장된 문제 수 반환.

    - 100개 단위 배치 커밋
    - chroma_id 중복 시 IntegrityError 무시 (aiosqlite rowcount 버그 우회)
    """
    from sqlalchemy.exc import IntegrityError

    saved = 0
    async with AsyncSessionLocal() as session:
        for start in range(0, len(questions), _SQLITE_BATCH):
            batch = questions[start : start + _SQLITE_BATCH]
            for q in batch:
                chroma_id = _make_chroma_id(q)
                options = q.get("options", [])
                db_q = Question(
                    year=q["year"],
                    round=q["round"],
                    subject=q["subject"],
                    question_num=q["question_num"],
                    question_text=q["question_text"],
                    option_1=options[0] if len(options) > 0 else None,
                    option_2=options[1] if len(options) > 1 else None,
                    option_3=options[2] if len(options) > 2 else None,
                    option_4=options[3] if len(options) > 3 else None,
                    option_5=options[4] if len(options) > 4 else None,
                    answer=q["answer"],
                    explanation=q.get("explanation", ""),
                    source_url=q.get("source_url", ""),
                    chroma_id=chroma_id,
                )
                session.add(db_q)
                saved += 1

            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                # 중복 포함 배치: 한 건씩 재시도
                for q in batch:
                    chroma_id = _make_chroma_id(q)
                    options = q.get("options", [])
                    try:
                        db_q = Question(
                            year=q["year"], round=q["round"], subject=q["subject"],
                            question_num=q["question_num"], question_text=q["question_text"],
                            option_1=options[0] if len(options) > 0 else None,
                            option_2=options[1] if len(options) > 1 else None,
                            option_3=options[2] if len(options) > 2 else None,
                            option_4=options[3] if len(options) > 3 else None,
                            option_5=options[4] if len(options) > 4 else None,
                            answer=q["answer"], explanation=q.get("explanation", ""),
                            source_url=q.get("source_url", ""), chroma_id=chroma_id,
                        )
                        session.add(db_q)
                        await session.commit()
                    except IntegrityError:
                        await session.rollback()
                        saved -= 1  # 중복은 카운트에서 제외

    return saved


def save_to_chroma(
    collection: chromadb.Collection,
    questions: list[dict],
    model: SentenceTransformer,
) -> int:
    """ChromaDB에 임베딩 벡터 저장. 저장된 문제 수 반환."""
    if not questions:
        return 0

    ids = []
    texts = []
    metadatas = []

    for q in questions:
        chroma_id = _make_chroma_id(q)
        text = _build_embedding_text(q)
        ids.append(chroma_id)
        texts.append(text)
        metadatas.append({
            "year": q["year"],
            "round": q["round"],
            "subject": q["subject"],
            "question_num": q["question_num"],
            "answer": q["answer"],
        })

    # 배치 임베딩 (tqdm 진행 표시)
    print(f"[ChromaDB] 임베딩 생성 중... ({len(texts)}문제)")
    batch_size = 32
    all_embeddings = []
    for i in tqdm(range(0, len(texts), batch_size), desc="임베딩"):
        batch = texts[i : i + batch_size]
        embeddings = model.encode(batch, show_progress_bar=False).tolist()
        all_embeddings.extend(embeddings)

    # ChromaDB upsert (중복 ID는 덮어쓰기)
    collection.upsert(
        ids=ids,
        embeddings=all_embeddings,
        documents=texts,
        metadatas=metadatas,
    )
    return len(ids)


async def run_init(
    use_sample: bool,
    crawl_range: tuple[int, int] | None,
    folder: str | None,
):
    """메인 초기화 로직."""
    print("=" * 60)
    print("유통관리사 기출문제 DB 초기화")
    print("=" * 60)

    # 1. SQLite 테이블 생성
    print("\n[1/4] SQLite 테이블 생성 중...")
    await init_db()
    print("      완료")

    # 2. ChromaDB 컬렉션 생성
    print("\n[2/4] ChromaDB 컬렉션 초기화 중...")
    collection = init_chroma()
    print(f"      컬렉션: {CHROMA_COLLECTION} | 저장 경로: {CHROMA_PATH}")

    # 3. 데이터 수집
    print("\n[3/4] 데이터 수집 중...")
    questions: list[dict] = []

    if folder:
        from crawler.file_loader import load_from_folder
        questions = load_from_folder(folder)

    elif use_sample:
        raw_questions = load_sample_data()
        print(f"      샘플 데이터 {len(raw_questions)}문제 로드됨")
        processor = QuestionProcessor(verbose=True)
        questions = processor.process(raw_questions)

    elif crawl_range:
        start_year, end_year = crawl_range
        print(f"      {start_year}~{end_year}년 크롤링 시작...")
        async with DistributionExamCrawler() as crawler:
            crawled = await crawler.crawl_all(start_year, end_year)
        raw_questions = [q.to_dict() for q in crawled]
        if not raw_questions:
            print("      크롤링 결과 없음. 샘플 데이터로 대체합니다.")
            raw_questions = load_sample_data()
        print(f"      크롤링 완료: {len(raw_questions)}문제")
        processor = QuestionProcessor(verbose=True)
        questions = processor.process(raw_questions)

    print(f"      최종 적재 대상: {len(questions)}문제")

    # 4. 임베딩 모델 로드 및 저장
    if not questions:
        print("\n저장할 문제가 없습니다. 종료합니다.")
        return

    print(f"\n[4/4] 임베딩 모델 로드 중... ({EMBEDDING_MODEL})")
    model = SentenceTransformer(EMBEDDING_MODEL)

    chroma_saved = save_to_chroma(collection, questions, model)
    print(f"      ChromaDB 저장 완료: {chroma_saved}문제")

    sqlite_saved = await save_to_sqlite(questions)
    print(f"      SQLite 저장 완료: {sqlite_saved}문제")

    print("\n" + "=" * 60)
    print(f"초기화 완료 — 총 {sqlite_saved}문제 저장됨")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="유통관리사 기출문제 DB 초기화")
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument(
        "--from-folder",
        metavar="FOLDER",
        nargs="?",
        const="data/questions",
        help="폴더에서 JSON/CSV 파일 로드 (기본: data/questions)",
    )
    group.add_argument(
        "--use-sample",
        action="store_true",
        help="내장 샘플 데이터 20문제로 초기화 (테스트용)",
    )
    group.add_argument(
        "--crawl",
        nargs=2,
        type=int,
        metavar=("START_YEAR", "END_YEAR"),
        help="지정 연도 범위 크롤링 (예: --crawl 2015 2024)",
    )
    args = parser.parse_args()

    # 인자 없으면 data/questions 폴더 우선, 없으면 샘플
    folder = args.from_folder
    if folder is None and not args.use_sample and not args.crawl:
        default_folder = Path(__file__).parent.parent / "data" / "questions"
        has_files = any(
            f.suffix in (".json", ".csv", ".pdf")
            for f in default_folder.iterdir()
            if not f.name.startswith((".", "format_example"))
        ) if default_folder.exists() else False
        folder = str(default_folder) if has_files else None

    use_sample = args.use_sample or (folder is None and not args.crawl)
    crawl_range = tuple(args.crawl) if args.crawl else None
    asyncio.run(run_init(use_sample=use_sample, crawl_range=crawl_range, folder=folder))


if __name__ == "__main__":
    main()
