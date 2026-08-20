"""Milestone 4 -- Insurance/Policy RAG Agent.

Wires guardrail -> hybrid retrieve -> rerank -> cited answer -> groundedness
gate. Falls back to a "flag for human" response rather than ever stating an
ungrounded coverage detail.
"""

from app.guardrails import REFUSAL_MESSAGE, is_clinical_advice_request
from app.llm import chat
from app.models.rag import RAGAnswer
from app.rag.groundedness import check_groundedness
from app.rag.rerank import rerank
from app.rag.retriever import hybrid_search
from app.tools.human_flag import flag_for_human

FALLBACK_MESSAGE = (
    "I don't have grounded information on that in our policy documents, so I don't want to guess. "
    "I've flagged this for a human care coordinator to confirm."
)

_ANSWER_PROMPT_TEMPLATE = """\
Answer the question using ONLY the excerpts below from CareFlow's policy/insurance documents. Cite \
the document title in parentheses after each claim. If the excerpts do not contain the answer, say \
so plainly instead of guessing -- do not use outside knowledge.

Excerpts:
{context}

Question: {question}
"""


def answer_policy_question(question: str, patient_id: str | None = None, model: str | None = None) -> RAGAnswer:
    if is_clinical_advice_request(question):
        flag_for_human(reason="clinical escalation", message_text=question, patient_id=patient_id)
        return RAGAnswer(question=question, answer=REFUSAL_MESSAGE, is_grounded=True, flagged=True)

    candidates = hybrid_search(question, top_k=20)
    top_chunks = rerank(question, candidates, top_n=5)

    if not top_chunks:
        flag_for_human(reason="no relevant policy content found", message_text=question, patient_id=patient_id)
        return RAGAnswer(question=question, answer=FALLBACK_MESSAGE, is_grounded=False, flagged=True)

    context = "\n\n".join(f"[{c['doc_title']}] {c['text']}" for c in top_chunks)
    draft = chat(
        [{"role": "user", "content": _ANSWER_PROMPT_TEMPLATE.format(context=context, question=question)}],
        model=model,
    )

    groundedness = check_groundedness(draft, top_chunks, model=model)
    if not groundedness.is_grounded:
        flag_for_human(
            reason=f"ungrounded RAG answer: {groundedness.unsupported_claims}",
            message_text=question,
            patient_id=patient_id,
        )
        return RAGAnswer(question=question, answer=FALLBACK_MESSAGE, is_grounded=False, flagged=True)

    citations = sorted({c["doc_title"] for c in top_chunks})
    return RAGAnswer(question=question, answer=draft, citations=citations, is_grounded=True, flagged=False)
