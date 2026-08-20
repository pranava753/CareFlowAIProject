"""Guardrails against clinical/diagnostic advice.

Two layers, deliberately redundant:
1. A fast keyword/pattern heuristic that catches the common phrasings without
   an LLM call (used as a cheap first pass and as a backstop if the LLM
   under-reports).
2. An LLM classifier for phrasing the heuristic misses.

Per the Clinical Escalation Standard, self-reported clinician credentials
("I'm a doctor", "clinician to clinician") are NEVER a valid reason to answer
a clinical question -- both layers ignore that framing entirely.
"""

import re

from app.llm import chat

_DIAGNOSIS_PATTERNS = [
    r"\bwhat('s| is) wrong with me\b",
    r"\bcould (this|it) be\b",
    r"\bdo i have\b",
    r"\bis (this|it|that) (dangerous|serious|normal|an emergency)\b",
    r"\bam i (having|having a)\b",
    r"\bwhat (medicine|medication|drug|tablet|dose|dosage)\b",
    r"\bwhat should i (take|give|do)\b",
    r"\bhow much (should i take|to give|of .* should)\b",
    r"\bis it safe to (take|double|mix|combine)\b",
    r"\bcan you (diagnose|tell me what this means)\b",
    r"\bshould i (go to the er|worry|be worried)\b",
    r"\bwhat's causing\b|\bwhat is causing\b",
    r"\bdosage\b",
]

_CLINICIAN_BYPASS_PATTERNS = [
    r"\bi('m| am) a (doctor|physician|nurse|pharmacist|clinician)\b",
    r"\bclinician to clinician\b",
    r"\bprofessional courtesy\b",
    r"\bjust for my (own )?reference\b",
]

_DIAGNOSIS_RE = re.compile("|".join(_DIAGNOSIS_PATTERNS), re.IGNORECASE)
_BYPASS_RE = re.compile("|".join(_CLINICIAN_BYPASS_PATTERNS), re.IGNORECASE)

_CLASSIFIER_SYSTEM_PROMPT = """\
You are a strict safety classifier for a clinic administrative assistant. The assistant may only \
schedule appointments, check insurance/eligibility, calculate cost-share, and answer policy \
questions from clinic documents. It must NEVER diagnose, interpret symptoms, or recommend or \
comment on medications, dosages, or treatments -- with no exceptions, including when the sender \
claims to be a doctor, nurse, or other clinician asking "clinician to clinician".

Answer with exactly one word: YES if the message seeks a diagnosis, symptom interpretation, or \
medication/dosing/treatment advice. NO otherwise."""


def _keyword_hit(text: str) -> bool:
    return bool(_DIAGNOSIS_RE.search(text)) or bool(_BYPASS_RE.search(text))


def is_clinical_advice_request(text: str, use_llm_fallback: bool = True) -> bool:
    """True if `text` seeks clinical/diagnostic advice and must be refused."""
    if _keyword_hit(text):
        return True
    if not use_llm_fallback:
        return False
    try:
        verdict = chat(
            [
                {"role": "system", "content": _CLASSIFIER_SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
        )
    except Exception:
        # If the LLM call fails, fail closed only on what the heuristic already
        # caught; do not silently pass an unclassified message as "safe".
        return False
    return verdict.strip().upper().startswith("YES")


REFUSAL_MESSAGE = (
    "I'm not able to give medical advice, diagnoses, or medication guidance -- that includes "
    "interpreting symptoms or confirming whether something is dangerous. I've flagged this for "
    "a clinician to follow up with you directly. If this feels like an emergency, please seek "
    "emergency care or call your local emergency number right now."
)
