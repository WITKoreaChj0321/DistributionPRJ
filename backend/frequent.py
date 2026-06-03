"""
최빈출 기출문제 분석.

여러 연도에 걸쳐 유사 문제가 반복 출제되는 유형을 '최빈출'로 판단한다.
각 문제를 벡터 검색하여 '다른 연도의 유사 문제 수'를 빈출 점수로 계산.
"""
import re

_SIM_THRESHOLD = 0.75
_NEIGHBORS = 6
_cache: list[dict] | None = None


def _clean_question(text: str) -> str:
    """본문에서 보기 나열 제거 → 질문만."""
    text = re.split(r'[①②③④⑤❶❷❸❹❺]', text)[0]
    text = re.sub(r'\|\s*\d+\.\s.*$', '', text)  # '| 1. ...' 보기 제거
    qm = text.find('?')
    if qm > 0:
        text = text[:qm + 1]
    return text.strip()


_CIRCLE = {1: "①", 2: "②", 3: "③", 4: "④", 5: "⑤"}


def _ans_content(doc: str, meta: dict) -> str:
    """정답 번호 + 보기 내용. 1) metadata options, 2) 본문 내 보기에서 추출."""
    ans = meta.get("answer", 0)
    circle = _CIRCLE.get(ans, str(ans))
    content = ""

    # 1) metadata options 우선
    opts_raw = str(meta.get("options") or "")
    opts = [o for o in opts_raw.split("\n") if o]
    if isinstance(ans, int) and 1 <= ans <= len(opts):
        content = re.sub(r'^\s*\d+[.)]\s*', '', opts[ans - 1]).strip()

    # 2) 없으면 본문(question_text)에 섞인 보기 '| N. 내용'에서 추출
    if not content and isinstance(ans, int):
        m = re.search(rf'(?:\||\b){ans}[.)]\s*([^|①②③④⑤]+)', doc)
        if m:
            content = m.group(1).strip()

    return f"{circle} {content}".strip()


def compute_frequent(
    vector_db, top_n: int = 10, subject: str | None = None, use_cache: bool = True
) -> list[dict]:
    """최빈출 기출문제 반환 (빈출 점수 내림차순). subject로 과목 필터."""
    all_items = _compute_all(vector_db, use_cache)
    if subject and subject != "전체":
        all_items = [q for q in all_items if q["subject"] == subject]
    return all_items[:top_n]


def _compute_all(vector_db, use_cache: bool = True) -> list[dict]:
    """전체 최빈출 리스트 계산 (캐시)."""
    global _cache
    if use_cache and _cache is not None:
        return _cache

    col = vector_db.get_collection()
    data = col.get(include=["documents", "metadatas", "embeddings"])
    ids   = data.get("ids", [])
    embs  = data.get("embeddings", [])
    metas = data.get("metadatas", [])
    docs  = data.get("documents", [])

    if not ids:
        return []

    res = col.query(
        query_embeddings=embs,
        n_results=_NEIGHBORS,
        include=["distances", "metadatas"],
    )

    scored: list[tuple[int, int]] = []
    for i in range(len(ids)):
        my_year = metas[i].get("year")
        cnt = 0
        for d, m in zip(res["distances"][i], res["metadatas"][i]):
            if (1 - d) >= _SIM_THRESHOLD and m.get("year") != my_year:
                cnt += 1
        scored.append((cnt, i))

    scored.sort(key=lambda x: x[0], reverse=True)

    # 유형 중복 제거: 이미 담은 문제와 매우 유사하면 skip
    result: list[dict] = []
    seen_texts: list[str] = []
    for cnt, i in scored:
        if cnt < 2:  # 2개 연도 미만 반복은 제외
            continue
        q_text = _clean_question(docs[i])
        # 간단한 중복 체크 (앞 20자 동일)
        key = q_text[:20]
        if key in seen_texts:
            continue
        seen_texts.append(key)
        result.append({
            "subject":       metas[i].get("subject", ""),
            "question_text": q_text,
            "answer_content": _ans_content(docs[i], metas[i]),
            "frequency":     cnt,
        })

    _cache = result
    return result
