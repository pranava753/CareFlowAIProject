"""Milestone 5 -- LangGraph orchestration of intake -> eligibility -> referral.

intake -> clinical_review -> [human-in-the-loop checkpoint iff flagged] ->
eligibility -> referral_routing -> finalize.

The human-in-the-loop node is a hard checkpoint: the graph pauses (via
langgraph's `interrupt()`) and will not proceed to escalate -- or resume the
normal eligibility/referral path -- until a human calls
`resume_intake_workflow` with an explicit decision. Nothing after the
`interrupt()` call runs until that happens.

Checkpointing uses a durable SqliteSaver (not the in-memory saver) so a
paused workflow survives a process restart between `run_intake_workflow`
and `resume_intake_workflow` -- important since those are typically two
separate API requests (see app/api/main.py) or CLI invocations.
"""

import sqlite3
from functools import lru_cache
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command, interrupt

from app.agents.clinical_safety_agent import review_message
from app.agents.intake import parse_intake_message
from app.config import settings
from app.guardrails import REFUSAL_MESSAGE
from app.observability.tracing import observe
from app.resilience.resilient_ehr import resilient_check_eligibility as check_eligibility
from app.tools.human_flag import flag_for_human
from app.tools.referral_tools import create_referral


class WorkflowState(TypedDict, total=False):
    raw_text: str
    channel: str
    patient_id: str | None
    patient_request: dict
    clinical_review: dict
    requires_human_review: bool
    human_decision: str | None
    eligibility: dict
    referral: dict | None
    final_response: str
    flagged: bool


@lru_cache(maxsize=1)
def get_workflow_checkpointer() -> SqliteSaver:
    settings.careflow_workflow_checkpoint_db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(settings.careflow_workflow_checkpoint_db), check_same_thread=False)
    saver = SqliteSaver(conn)
    saver.setup()
    return saver


def close_workflow_checkpointer() -> None:
    if get_workflow_checkpointer.cache_info().currsize:
        get_workflow_checkpointer().conn.close()
        get_workflow_checkpointer.cache_clear()


def intake_node(state: WorkflowState) -> dict:
    patient_request = parse_intake_message(state["raw_text"], state["channel"])
    return {"patient_request": patient_request.model_dump(mode="json")}


def clinical_review_node(state: WorkflowState) -> dict:
    review = review_message(state["raw_text"])
    # Defense in depth: OR the reviewer's verdict with the intake agent's own
    # self-reported flag, same pattern as app/agents/intake.py.
    requires_review = review.requires_human_review or state["patient_request"]["seeks_clinical_advice"]
    return {"clinical_review": review.model_dump(), "requires_human_review": requires_review}


def route_after_clinical_review(state: WorkflowState) -> str:
    return "human_in_the_loop" if state["requires_human_review"] else "eligibility"


def human_in_the_loop_node(state: WorkflowState) -> dict:
    # This must be the ONLY statement in this node: langgraph re-runs the
    # whole node function from the top on every resume, so anything else
    # here (logging, flagging) would re-execute each time.
    decision = interrupt(
        {
            "reason": "clinical_advice_detected",
            "raw_text": state["raw_text"],
            "clinical_review": state["clinical_review"],
        }
    )
    return {"human_decision": decision}


def route_after_human_decision(state: WorkflowState) -> str:
    return "escalate" if state["human_decision"] == "confirm_escalate" else "eligibility"


def escalate_node(state: WorkflowState) -> dict:
    flag_for_human(
        reason="clinical escalation (human-confirmed)",
        message_text=state["raw_text"],
        patient_id=state.get("patient_id"),
    )
    return {"final_response": REFUSAL_MESSAGE, "flagged": True}


def eligibility_node(state: WorkflowState) -> dict:
    insurance_id = state["patient_request"].get("insurance_id")
    if not insurance_id:
        return {"eligibility": {"found": False, "error": "No insurance_id stated in the message."}}
    return {"eligibility": check_eligibility(insurance_id)}


def referral_routing_node(state: WorkflowState) -> dict:
    specialty = state["patient_request"].get("specialty")
    patient_id = state.get("patient_id")
    if not specialty or not patient_id:
        return {"referral": None}
    referral = create_referral(
        patient_id=patient_id,
        specialty_key=specialty,
        reason="; ".join(state["patient_request"].get("symptoms", [])) or "Patient-initiated intake request.",
    )
    return {"referral": referral if referral.get("success") else None}


def finalize_node(state: WorkflowState) -> dict:
    lines = []
    eligibility = state.get("eligibility") or {}
    if eligibility.get("found"):
        elig = eligibility["eligibility"]
        lines.append(f"Insurance eligibility: active on plan {elig['plan_id']}.")
    else:
        lines.append(f"Insurance eligibility could not be confirmed ({eligibility.get('error', 'not checked')}).")

    referral = state.get("referral")
    if referral:
        r = referral["referral"]
        lines.append(
            f"Referral {r['referral_id']} created for {r['specialty_key']} "
            f"(pre-authorization {'required' if r['preauth_required'] else 'not required'})."
        )
    else:
        lines.append("No referral created (specialty or patient ID not available).")

    return {"final_response": " ".join(lines), "flagged": False}


def build_intake_workflow() -> StateGraph:
    graph = StateGraph(WorkflowState)
    graph.add_node("intake", intake_node)
    graph.add_node("clinical_review", clinical_review_node)
    graph.add_node("human_in_the_loop", human_in_the_loop_node)
    graph.add_node("escalate", escalate_node)
    graph.add_node("eligibility", eligibility_node)
    graph.add_node("referral_routing", referral_routing_node)
    graph.add_node("finalize", finalize_node)

    graph.add_edge(START, "intake")
    graph.add_edge("intake", "clinical_review")
    graph.add_conditional_edges(
        "clinical_review", route_after_clinical_review, {"human_in_the_loop": "human_in_the_loop", "eligibility": "eligibility"}
    )
    graph.add_conditional_edges(
        "human_in_the_loop", route_after_human_decision, {"escalate": "escalate", "eligibility": "eligibility"}
    )
    graph.add_edge("escalate", END)
    graph.add_edge("eligibility", "referral_routing")
    graph.add_edge("referral_routing", "finalize")
    graph.add_edge("finalize", END)
    return graph


@lru_cache(maxsize=1)
def get_compiled_workflow():
    return build_intake_workflow().compile(checkpointer=get_workflow_checkpointer())


@observe(name="run_intake_workflow")
def run_intake_workflow(raw_text: str, channel: str, session_id: str, patient_id: str | None = None) -> dict:
    """Start (or restart) an intake workflow run under `session_id`.

    Returns either a completed result (`final_response`, `flagged`, ...) or,
    if the clinical safety reviewer flagged the message,
    `{"status": "needs_human_review", "session_id": ..., "review": {...}}`.
    """
    graph = get_compiled_workflow()
    config = {"configurable": {"thread_id": session_id}}
    result = graph.invoke(
        {"raw_text": raw_text, "channel": channel, "patient_id": patient_id},
        config=config,
    )
    return _to_response(session_id, result)


@observe(name="resume_intake_workflow")
def resume_intake_workflow(session_id: str, decision: str) -> dict:
    """Resume a paused workflow with a human decision.

    `decision` must be "confirm_escalate" (the reviewer was right, refuse and
    flag) or "override_proceed" (false positive, continue to eligibility/
    referral routing as normal).
    """
    graph = get_compiled_workflow()
    config = {"configurable": {"thread_id": session_id}}
    result = graph.invoke(Command(resume=decision), config=config)
    return _to_response(session_id, result)


def _to_response(session_id: str, result: dict) -> dict:
    if result.get("__interrupt__"):
        payload = result["__interrupt__"][0].value
        return {"status": "needs_human_review", "session_id": session_id, "review": payload}
    return {
        "status": "completed",
        "session_id": session_id,
        "final_response": result.get("final_response"),
        "flagged": result.get("flagged", False),
        "patient_request": result.get("patient_request"),
        "eligibility": result.get("eligibility"),
        "referral": result.get("referral"),
    }
