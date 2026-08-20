"""Milestone 4 -- LLM-judge groundedness check.

Verifies every factual claim in a drafted RAG answer is directly supported
by the retrieved context, so the policy/insurance agent never states a
coverage detail that isn't actually in the corpus.
"""

from app.config import settings
from app.llm import extract_structured
from app.models.rag import GroundednessResult

_PROMPT_TEMPLATE = """\
You are a strict fact-checker. Given the CONTEXT excerpts and a drafted ANSWER, determine whether \
every factual claim in the ANSWER (numbers, coverage terms, policy rules, yes/no statements) is \
directly supported by the CONTEXT. If the answer states anything not present in the context, list \
it under unsupported_claims and set is_grounded to false. If the answer only says information isn't \
available, treat that as grounded.

CONTEXT:
{context}

ANSWER:
{answer}
"""


def check_groundedness(answer: str, context_chunks: list[dict], model: str | None = None) -> GroundednessResult:
    context = "\n\n".join(f"[{c['doc_title']}] {c['text']}" for c in context_chunks)
    prompt = _PROMPT_TEMPLATE.format(context=context, answer=answer)
    return extract_structured(prompt, GroundednessResult, model=model or settings.careflow_judge_model)
