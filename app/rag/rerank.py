"""Milestone 4 -- cross-encoder reranking of hybrid retrieval candidates."""

from functools import lru_cache

from sentence_transformers import CrossEncoder

from app.config import settings


@lru_cache(maxsize=1)
def get_reranker() -> CrossEncoder:
    return CrossEncoder(settings.careflow_reranker_model)


def rerank(query: str, candidates: list[dict], top_n: int = 5) -> list[dict]:
    if not candidates:
        return []
    model = get_reranker()
    pairs = [(query, c["text"]) for c in candidates]
    scores = model.predict(pairs)
    scored = sorted(zip(candidates, scores), key=lambda pair: pair[1], reverse=True)
    return [{**c, "rerank_score": float(s)} for c, s in scored[:top_n]]
