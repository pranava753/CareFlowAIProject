"""Chunking for the policy/insurance corpus (markdown is the canonical text
source; PDFs are the deliverable format generate.py also renders)."""

from dataclasses import dataclass

from app.config import settings


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    doc_title: str
    text: str
    chunk_index: int


def _split_words(text: str, chunk_size: int = 220, overlap: int = 40) -> list[str]:
    words = text.split()
    if not words:
        return []
    pieces = []
    start = 0
    while start < len(words):
        end = start + chunk_size
        pieces.append(" ".join(words[start:end]))
        if end >= len(words):
            break
        start = end - overlap
    return pieces


def load_corpus_chunks() -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in sorted(settings.corpus_markdown_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        title = lines[0].lstrip("#").strip() if lines else path.stem
        body = "\n".join(lines[1:])
        doc_id = path.stem
        for i, piece in enumerate(_split_words(body)):
            chunks.append(Chunk(chunk_id=f"{doc_id}::{i}", doc_id=doc_id, doc_title=title, text=piece, chunk_index=i))
    return chunks
