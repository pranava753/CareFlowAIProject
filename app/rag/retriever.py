"""Milestone 4 -- hybrid (dense + sparse) retrieval via reciprocal-rank fusion."""

from app.config import settings
from app.rag.index import get_embedding_model, get_qdrant_client, load_bm25_index


def _dense_search(query: str, top_k: int) -> list[dict]:
    model = get_embedding_model()
    client = get_qdrant_client()
    vector = model.encode(query).tolist()
    result = client.query_points(
        collection_name=settings.careflow_qdrant_collection,
        query=vector,
        limit=top_k,
    )
    return [
        {
            "chunk_id": p.payload["chunk_id"],
            "doc_id": p.payload["doc_id"],
            "doc_title": p.payload["doc_title"],
            "text": p.payload["text"],
            "dense_score": p.score,
        }
        for p in result.points
    ]


def _sparse_search(query: str, top_k: int) -> list[dict]:
    bm25, chunk_meta = load_bm25_index()
    scores = bm25.get_scores(query.lower().split())
    ranked_idx = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
    return [{**chunk_meta[i], "sparse_score": float(scores[i])} for i in ranked_idx]


def hybrid_search(query: str, top_k: int = 20, rrf_k: int = 60) -> list[dict]:
    """Reciprocal-rank fusion of dense (Qdrant) and sparse (BM25) result lists."""
    dense = _dense_search(query, top_k)
    sparse = _sparse_search(query, top_k)

    rrf_scores: dict[str, float] = {}
    chunk_lookup: dict[str, dict] = {}
    for rank_list in (dense, sparse):
        for rank, item in enumerate(rank_list):
            cid = item["chunk_id"]
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + 1.0 / (rrf_k + rank + 1)
            chunk_lookup.setdefault(cid, item).update(item)

    ranked_ids = sorted(rrf_scores, key=lambda cid: rrf_scores[cid], reverse=True)[:top_k]
    return [{**chunk_lookup[cid], "rrf_score": rrf_scores[cid]} for cid in ranked_ids]
