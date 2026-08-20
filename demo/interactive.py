"""Interactive CareFlow CLI -- type messages instead of running the fixed demo.

Requires an LLM provider key set in .env and scripts/build_index.py already run.

Usage:
    python demo/interactive.py
"""

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agents.insurance_agent import run_insurance_agent  # noqa: E402
from app.agents.intake import parse_intake_message  # noqa: E402
from app.config import settings  # noqa: E402

VALID_CHANNELS = ("web_form", "phone_transcript", "email", "sms")


def main() -> None:
    print("CareFlow interactive demo. Type 'exit' or 'quit' to leave.\n")
    print("(Note: the first Policy Q&A question in a session loads local embedding/rerank")
    print("models -- torch/sentence-transformers -- which can take up to a minute.)\n")

    channel = input(f"Channel {VALID_CHANNELS} [web_form]: ").strip() or "web_form"
    if channel not in VALID_CHANNELS:
        print("Unrecognized channel, defaulting to web_form.")
        channel = "web_form"
    patient_id = input("Synthetic patient_id, e.g. P00001 [optional]: ").strip() or None

    print(
        "\nType a message as if you were the patient. Each message is parsed by the "
        "Intake Agent (M1) first, then you choose where to route it -- clinical-advice "
        "requests are refused and flagged automatically regardless of routing.\n"
    )

    while True:
        text = input("You: ").strip()
        if text.lower() in ("exit", "quit"):
            break
        if not text:
            continue

        patient_request = parse_intake_message(text, channel=channel)
        print(
            f"  [intake] specialty={patient_request.specialty} "
            f"urgency={patient_request.urgency.value} "
            f"insurance_id={patient_request.insurance_id} "
            f"seeks_clinical_advice={patient_request.seeks_clinical_advice} "
            f"missing_fields={patient_request.missing_fields}"
        )

        if patient_request.seeks_clinical_advice:
            result = run_insurance_agent(patient_request, text, patient_id=patient_id)
            print(f"\nAssistant: {result['response']}\n")
            continue

        route = input("  Route to [1] Insurance/Scheduling agent  [2] Policy Q&A agent (default 1): ").strip() or "1"
        if route == "2":
            # Imported lazily: this pulls in sentence-transformers/torch, which is
            # slow to import cold, so users who never pick this route never pay for it.
            from app.rag.qa_agent import answer_policy_question

            answer = answer_policy_question(text, patient_id=patient_id)
            print(f"\nAssistant: {answer.answer}")
            print(f"Citations: {answer.citations}\n")
        else:
            result = run_insurance_agent(patient_request, text, patient_id=patient_id)
            print(f"\nAssistant: {result['response']}\n")
            for call in result["tool_calls"]:
                print(f"  tool call: {call['name']}({call['args']}) -> {call['result']}")

    print(f"\nDone. Human-escalation queue (if anything was flagged): {settings.human_queue_path}")


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\nExiting.")
    finally:
        # Only close the Qdrant client if the RAG path was actually used this run.
        if "app.rag.index" in sys.modules:
            sys.modules["app.rag.index"].close_qdrant_client()
