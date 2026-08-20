"""Milestone 3/4 -- local embedded Qdrant dense index + BM25 sparse index.

Both are built from the same chunk set (app.rag.ingest.load_corpus_chunks)
so the hybrid retriever in app.rag.retriever can fuse them by chunk_id.
"""

import pickle
from functools import lru_cache

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

from app.config import settings
from app.rag.ingest import Chunk, load_corpus_chunks


@lru_cache(maxsize=1)
def get_embedding_model() -> SentenceTransformer:
    return SentenceTransformer(settings.careflow_embedding_model)


@lru_cache(maxsize=1)
def get_qdrant_client() -> QdrantClient:
    settings.careflow_qdrant_path.mkdir(parents=True, exist_ok=True)
    return QdrantClient(path=str(settings.careflow_qdrant_path))


def close_qdrant_client() -> None:
    """Close the cached local-mode Qdrant client explicitly.

    QdrantClient's own __del__ can fire during interpreter shutdown (after
    Python has already torn down some modules), which prints a harmless but
    noisy "Exception ignored ... sys.meta_path is None" message. Calling this
    at the end of a script avoids that.
    """
    if get_qdrant_client.cache_info().currsize:
        get_qdrant_client().close()
        get_qdrant_client.cache_clear()


def build_dense_index(chunks: list[Chunk] | None = None) -> int:
    chunks = chunks or load_corpus_chunks()
    model = get_embedding_model()
    client = get_qdrant_client()

    vectors = model.encode([c.text for c in chunks], show_progress_bar=False)
    dim = len(vectors[0])
    collection = settings.careflow_qdrant_collection

    try:
        client.delete_collection(collection)
    except Exception:
        pass
    client.create_collection(
        collection_name=collection,
        vectors_config=qmodels.VectorParams(size=dim, distance=qmodels.Distance.COSINE),
    )
    client.upsert(
        collection_name=collection,
        points=[
            qmodels.PointStruct(
                id=i,
                vector=vectors[i].tolist(),
                payload={
                    "chunk_id": c.chunk_id,
                    "doc_id": c.doc_id,
                    "doc_title": c.doc_title,
                    "text": c.text,
                },
            )
            for i, c in enumerate(chunks)
        ],
    )
    return len(chunks)


def build_bm25_index(chunks: list[Chunk] | None = None) -> int:
    chunks = chunks or load_corpus_chunks()
    tokenized = [c.text.lower().split() for c in chunks]
    bm25 = BM25Okapi(tokenized)
    chunk_meta = [
        {"chunk_id": c.chunk_id, "doc_id": c.doc_id, "doc_title": c.doc_title, "text": c.text}
        for c in chunks
    ]
    settings.careflow_bm25_index_path.parent.mkdir(parents=True, exist_ok=True)
    with settings.careflow_bm25_index_path.open("wb") as f:
        pickle.dump({"bm25": bm25, "chunk_meta": chunk_meta}, f)
    return len(chunks)


def load_bm25_index() -> tuple[BM25Okapi, list[dict]]:
    if not settings.careflow_bm25_index_path.exists():
        raise FileNotFoundError(
            f"BM25 index not found at {settings.careflow_bm25_index_path}. Run scripts/build_index.py first."
        )
    with settings.careflow_bm25_index_path.open("rb") as f:
        data = pickle.load(f)
    return data["bm25"], data["chunk_meta"]


def build_all_indexes() -> int:
    chunks = load_corpus_chunks()
    build_dense_index(chunks)
    build_bm25_index(chunks)
    return len(chunks)
