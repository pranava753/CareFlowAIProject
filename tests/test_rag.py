import pytest

from app.config import settings
from app.rag.rerank import rerank
from app.rag.retriever import hybrid_search

pytestmark = pytest.mark.skipif(
    not settings.careflow_bm25_index_path.exists(),
    reason="RAG index not built yet -- run `python scripts/build_index.py` first.",
)


def test_hybrid_search_finds_cost_share_doc_for_copay_question():
    results = hybrid_search("What is the specialist copay for the Gold plan?", top_k=10)
    assert results
    assert any(r["doc_id"] == "cost_share_schedule" for r in results)


def test_hybrid_search_finds_correct_specialty_handbook():
    results = hybrid_search("How long is a dermatology appointment and what should I bring?", top_k=10)
    assert results
    assert any(r["doc_id"] == "handbook_dermatology" for r in results)


def test_rerank_orders_by_relevance_and_respects_top_n():
    candidates = hybrid_search("pre-authorization turnaround time", top_k=10)
    top = rerank("pre-authorization turnaround time", candidates, top_n=3)
    assert len(top) <= 3
    scores = [c["rerank_score"] for c in top]
    assert scores == sorted(scores, reverse=True)


def test_rerank_empty_candidates_returns_empty():
    assert rerank("anything", [], top_n=3) == []
