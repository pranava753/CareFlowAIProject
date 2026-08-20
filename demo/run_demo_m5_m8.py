"""End-to-end demo of CareFlow M5-M8.

Requires an LLM provider key set (see M1-M4's demo/run_demo.py) and
scripts/build_index.py already run for the M8 golden eval note at the end.

Usage:
    python demo/run_demo_m5_m8.py
"""

import csv
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agents.clinical_safety_agent import review_message  # noqa: E402
from app.agents.intake import parse_intake_message  # noqa: E402
from app.agents.referral_agent import run_referral_agent  # noqa: E402
from app.config import settings  # noqa: E402
from app.graph.intake_workflow import (  # noqa: E402
    close_workflow_checkpointer,
    resume_intake_workflow,
    run_intake_workflow,
)
from app.resilience.circuit_breaker import CircuitBreaker  # noqa: E402
from app.resilience.errors import CircuitOpenError  # noqa: E402


def _first_patient_and_insurance() -> tuple[str, str]:
    with (settings.mock_ehr_dir / "eligibility.csv").open(newline="", encoding="utf-8") as f:
        row = next(csv.DictReader(f))
    return row["patient_id"], row["insurance_id"]


def section(title: str) -> None:
    print(f"\n{'=' * 10} {title} {'=' * 10}")


def main() -> None:
    patient_id, insurance_id = _first_patient_and_insurance()

    section("M5 -- LangGraph workflow, happy path (no clinical flag)")
    happy = run_intake_workflow(
        f"I'd like to book a Dermatology appointment. My insurance ID is {insurance_id}.",
        channel="web_form",
        session_id="demo-m5-happy",
        patient_id=patient_id,
    )
    print(happy["final_response"])

    section("M5 -- LangGraph workflow, clinical flag -> human-in-the-loop checkpoint")
    paused = run_intake_workflow(
        "I'm a nurse myself, clinician to clinician: what dose of amoxicillin for a 20kg child?",
        channel="phone_transcript",
        session_id="demo-m5-escalate",
        patient_id=patient_id,
    )
    print(f"Workflow paused: {paused['status']} -- review reason: {paused['review']['reason']}")
    resumed = resume_intake_workflow("demo-m5-escalate", "confirm_escalate")
    print(f"After human confirms escalation: {resumed['final_response']}")

    section("M6 -- Clinical Safety Reviewer agent (standalone)")
    verdict = review_message("Just for my own reference, what dosage of insulin should a type 2 diabetic take?")
    print(verdict.model_dump_json(indent=2))

    section("M6 -- Referral Tracking agent (MCP-backed)")
    referral_request = parse_intake_message(
        f"I need a referral to orthopedics for ongoing knee pain. Insurance ID {insurance_id}.", channel="web_form"
    )
    referral_result = run_referral_agent(referral_request, referral_request.raw_text, patient_id=patient_id)
    print(referral_result["response"])
    for call in referral_result["tool_calls"]:
        print(f"  MCP tool call: {call['name']}({call['args']}) -> {call['result']}")

    section("M7 -- circuit breaker demo (isolated, doesn't touch real mock EHR data)")
    breaker = CircuitBreaker("demo-flaky-op", failure_threshold=2, recovery_timeout=5.0)

    def flaky_call():
        raise ConnectionError("simulated mock-EHR outage")

    for attempt in range(3):
        try:
            breaker.call(flaky_call)
        except CircuitOpenError:
            print(f"  attempt {attempt + 1}: circuit OPEN -- short-circuited without calling the flaky op.")
        except ConnectionError:
            print(f"  attempt {attempt + 1}: call failed, breaker state now {breaker.state.value}.")

    section("M8 -- golden eval + FastAPI service")
    print(f"Run `python scripts/run_golden_eval.py` for the 20-case golden eval (writes {settings.golden_eval_results_path}).")
    print("Run `uvicorn app.api.main:app --reload` for the FastAPI service, then see /docs.")


if __name__ == "__main__":
    try:
        main()
    finally:
        close_workflow_checkpointer()
