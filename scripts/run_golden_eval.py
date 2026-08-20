"""Milestone 8 -- golden eval runner.

20 hand-authored cases (data/careflow/eval/golden_eval.jsonl), weighted
toward refusal since the failure mode this project cares most about is a
system that gives clinical advice. Routes each case to the real pipeline
entrypoint for its category and compares actual vs. expected behavior.

Usage:
    python scripts/run_golden_eval.py
"""

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agents.insurance_agent import run_insurance_agent  # noqa: E402
from app.agents.intake import parse_intake_message  # noqa: E402
from app.agents.referral_agent import run_referral_agent  # noqa: E402
from app.config import settings  # noqa: E402
from app.rag.index import close_qdrant_client  # noqa: E402
from app.rag.qa_agent import answer_policy_question  # noqa: E402


def _load_cases() -> list[dict]:
    with settings.golden_eval_path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _run_agent_case(text: str, channel: str, patient_id: str | None, run_agent) -> tuple[str, str]:
    patient_request = parse_intake_message(text, channel=channel)
    result = run_agent(patient_request, text, patient_id=patient_id)
    if result["flagged"]:
        return "refuse", result["response"]
    if result["tool_calls"]:
        return "tool_action", result["response"]
    return "answer", result["response"]


def _run_case(case: dict) -> dict:
    category = case["category"]
    text = case["input"]
    patient_id = case.get("patient_id")

    if category == "clinical_refusal":
        actual, detail = _run_agent_case(text, case["channel"], patient_id, run_insurance_agent)
    elif category == "policy_qa":
        answer = answer_policy_question(text, patient_id=patient_id)
        actual = "flag_ungrounded" if answer.flagged else "answer"
        detail = answer.answer
    elif category in ("scheduling", "eligibility"):
        actual, detail = _run_agent_case(text, case["channel"], patient_id, run_insurance_agent)
    elif category == "referral":
        actual, detail = _run_agent_case(text, case["channel"], patient_id, run_referral_agent)
    else:
        raise ValueError(f"Unknown category {category!r} in case {case['id']}")

    return {
        "id": case["id"],
        "category": category,
        "expected": case["expected_behavior"],
        "actual": actual,
        "passed": actual == case["expected_behavior"],
        "detail": detail,
    }


def main() -> None:
    if not settings.has_llm_key:
        print("No LLM provider key configured -- skipping golden eval (see .env.example).")
        return
    if not settings.golden_eval_path.exists():
        print(f"Golden eval set not found at {settings.golden_eval_path}.")
        return

    cases = _load_cases()
    results = [_run_case(c) for c in cases]

    settings.golden_eval_results_path.parent.mkdir(parents=True, exist_ok=True)
    with settings.golden_eval_results_path.open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")

    passed = sum(r["passed"] for r in results)
    print(f"{passed}/{len(results)} cases passed.\n")
    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        print(f"[{status}] {r['id']:6s} ({r['category']:16s}) expected={r['expected']:16s} actual={r['actual']}")
    print(f"\nFull results written to {settings.golden_eval_results_path}")


if __name__ == "__main__":
    try:
        main()
    finally:
        close_qdrant_client()
