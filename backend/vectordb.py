import sys
import uuid
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

import asyncio
from typing import Optional

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

COLLECTION_NAME = "distribution_exam_questions"
EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
# 절대 경로로 고정 (실행 위치와 무관하게 동작)
_DEFAULT_CHROMA_DIR = str(Path(__file__).resolve().parent.parent / "database" / "chroma_db")


def _make_id(q: dict) -> str:
    """ID 없는 문제에 연도-회차-번호 기반 ID 생성."""
    year = q.get("year", 0)
    round_ = q.get("round", 0)
    q_num = q.get("question_num", 0)
    if year and round_ and q_num:
        return f"dist_{year}_{round_}_{q_num:03d}"
    return f"dist_{uuid.uuid4().hex[:12]}"


class VectorDBManager:
    def __init__(self, persist_dir: str = _DEFAULT_CHROMA_DIR):
        self._persist_dir = persist_dir
        self._client: Optional[chromadb.PersistentClient] = None
        self._collection: Optional[chromadb.Collection] = None
        self._embedder: Optional[SentenceTransformer] = None

    def _get_client(self) -> chromadb.PersistentClient:
        if self._client is None:
            Path(self._persist_dir).mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(
                path=self._persist_dir,
                settings=Settings(anonymized_telemetry=False),
            )
        return self._client

    def get_collection(self) -> chromadb.Collection:
        if self._collection is None:
            client = self._get_client()
            self._collection = client.get_or_create_collection(
                name=COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    def _get_embedder(self) -> SentenceTransformer:
        if self._embedder is None:
            self._embedder = SentenceTransformer(EMBEDDING_MODEL)
        return self._embedder

    def _embed(self, texts: list[str]) -> list[list[float]]:
        embedder = self._get_embedder()
        vectors = embedder.encode(texts, convert_to_numpy=True)
        return vectors.tolist()

    async def add_questions(self, questions: list[dict]) -> None:
        """
        questions 항목 형식:
        {
            "id": str,
            "question_text": str,
            "year": int, "round": int, "subject": str,
            "question_num": int, "options": list[str],
            "answer": int, "explanation": str,
        }
        """
        if not questions:
            return

        # 빈 question_text 제외 (ChromaDB 빈 문서 거부)
        questions = [q for q in questions if q.get("question_text", "").strip()]
        if not questions:
            return

        loop = asyncio.get_running_loop()
        collection = self.get_collection()

        texts = [q["question_text"] for q in questions]
        ids = [str(q["id"]) if "id" in q else _make_id(q) for q in questions]

        metadatas = []
        for q in questions:
            metadatas.append({
                "year": int(q.get("year", 0)),
                "round": int(q.get("round", 0)),
                "subject": str(q.get("subject", "")),
                "question_num": int(q.get("question_num", 0)),
                "options": "\n".join(q.get("options", [])),
                "answer": int(q.get("answer", 0)),
                "explanation": str(q.get("explanation", "")),
            })

        embeddings = await loop.run_in_executor(None, self._embed, texts)

        def _upsert():
            collection.upsert(
                ids=ids,
                embeddings=embeddings,
                documents=texts,
                metadatas=metadatas,
            )

        await loop.run_in_executor(None, _upsert)

    async def search_similar(
        self,
        query_text: str,
        n_results: int = 5,
        subject_filter: Optional[str] = None,
    ) -> list[dict]:
        if not query_text.strip():
            return []

        loop = asyncio.get_running_loop()
        collection = self.get_collection()

        # 빈 컬렉션 조기 반환
        total = collection.count()
        if total == 0:
            return []

        # n_results를 실제 문서 수로 clamp (ChromaDB 오류 방지)
        safe_n = min(n_results, total)

        query_embedding = await loop.run_in_executor(
            None, self._embed, [query_text]
        )

        where = {"subject": subject_filter} if subject_filter else None

        def _query(w: Optional[dict], n: int):
            kwargs: dict = {
                "query_embeddings": query_embedding,
                "n_results": n,
                "include": ["documents", "metadatas", "distances"],
            }
            if w:
                kwargs["where"] = w
            return collection.query(**kwargs)

        try:
            results = await loop.run_in_executor(None, _query, where, safe_n)
        except Exception:
            # subject_filter 결과가 n_results보다 적으면 필터 없이 재시도
            if where:
                results = await loop.run_in_executor(None, _query, None, safe_n)
            else:
                return []

        output: list[dict] = []
        ids = results.get("ids", [[]])[0]
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for doc_id, doc, meta, dist in zip(ids, docs, metas, distances):
            similarity = 1.0 - float(dist)  # cosine distance → similarity
            options_raw = meta.get("options", "")
            options = [o for o in options_raw.split("\n") if o] if options_raw else []

            output.append({
                "id": doc_id,
                "question_text": doc,
                "year": meta.get("year", 0),
                "round": meta.get("round", 0),
                "subject": meta.get("subject", ""),
                "question_num": meta.get("question_num", 0),
                "options": options,
                "answer": meta.get("answer", 0),
                "explanation": meta.get("explanation", ""),
                "similarity": round(similarity, 4),
            })

        return output

    def get_stats(self) -> dict:
        try:
            collection = self.get_collection()
            count = collection.count()
            return {
                "collection_name": COLLECTION_NAME,
                "total_questions": count,
                "persist_dir": self._persist_dir,
                "embedding_model": EMBEDDING_MODEL,
            }
        except Exception as e:
            return {"error": str(e)}
