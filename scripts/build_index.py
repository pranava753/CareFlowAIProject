"""Build the Qdrant dense index + BM25 sparse index over the policy corpus.

Run after generate.py has produced data/careflow/corpus/markdown/.

Usage:
    python scripts/build_index.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.rag.index import build_all_indexes  # noqa: E402


def main() -> None:
    n = build_all_indexes()
    print(f"Indexed {n} chunks into Qdrant ({'careflow_policy_corpus'}) and the BM25 sidecar index.")


if __name__ == "__main__":
    main()
