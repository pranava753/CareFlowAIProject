"""Milestone 2 -- single scheduling/insurance-lookup agent.

Tool-calling loop over four mock tools: EHR appointment slots/booking,
insurance eligibility, co-pay/procedure-cost calculator, and flag-for-human.
Guardrails are checked BEFORE the tool-calling loop starts -- a clinical
question never reaches the LLM's tool-use reasoning, it goes straight to
flag_for_human.
"""

import json
import logging

from app.constants import SPECIALTY_KEYS
from app.guardrails import REFUSAL_MESSAGE, is_clinical_advice_request
from app.llm import chat_message
from app.models.patient_request import PatientRequest
from app.resilience.resilient_ehr import (
    resilient_book_appointment as book_appointment,
    resilient_calculate_copay as calculate_copay,
    resilient_check_eligibility as check_eligibility,
    resilient_estimate_procedure_cost as estimate_procedure_cost,
    resilient_get_available_slots as get_available_slots,
)
from app.tools.human_flag import flag_for_human

logger = logging.getLogger(__name__)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_available_slots",
            "description": "List open appointment slots for a clinic specialty.",
            "parameters": {
                "type": "object",
                "properties": {
                    "specialty_key": {"type": "string", "enum": SPECIALTY_KEYS},
                    "max_results": {"type": "integer", "default": 5},
                },
                "required": ["specialty_key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "book_appointment",
            "description": "Book a specific available appointment slot for a patient.",
            "parameters": {
                "type": "object",
                "properties": {
                    "appointment_id": {"type": "string"},
                    "patient_id": {"type": "string"},
                },
                "required": ["appointment_id", "patient_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_eligibility",
            "description": "Look up a patient's insurance eligibility status, plan, and deductible progress by insurance ID.",
            "parameters": {
                "type": "object",
                "properties": {"insurance_id": {"type": "string"}},
                "required": ["insurance_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_copay",
            "description": "Calculate the flat office-visit copay for a patient's plan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "insurance_id": {"type": "string"},
                    "visit_type": {"type": "string", "enum": ["specialist", "primary_care"], "default": "specialist"},
                },
                "required": ["insurance_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "estimate_procedure_cost",
            "description": "Estimate a patient's out-of-pocket cost for a specialty's typical procedure, and whether it needs pre-authorization.",
            "parameters": {
                "type": "object",
                "properties": {
                    "insurance_id": {"type": "string"},
                    "specialty_key": {"type": "string", "enum": SPECIALTY_KEYS},
                },
                "required": ["insurance_id", "specialty_key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "flag_for_human",
            "description": "Escalate the request to a human care coordinator (e.g. clinical questions, no available slots, payer disputes).",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string"},
                    "message_text": {"type": "string"},
                    "patient_id": {"type": "string"},
                },
                "required": ["reason", "message_text"],
            },
        },
    },
]

_DISPATCH = {
    "get_available_slots": get_available_slots,
    "book_appointment": book_appointment,
    "check_eligibility": check_eligibility,
    "calculate_copay": calculate_copay,
    "estimate_procedure_cost": estimate_procedure_cost,
    "flag_for_human": flag_for_human,
}

SYSTEM_PROMPT = """\
You are the CareFlow scheduling/insurance assistant. You may only schedule appointments, check \
insurance eligibility, calculate cost-share, and answer policy/coverage questions using your tools.

You must NEVER diagnose, interpret symptoms, or recommend/comment on medications, dosages, or \
treatments, even if the person says they are a doctor, nurse, or other clinician. If a request \
touches on any of that, call flag_for_human with reason "clinical escalation" and tell the patient \
a clinician will follow up -- do not attempt to answer the clinical part.

Never state a specific dollar amount, coverage decision, or appointment confirmation unless it \
came from a tool call in this conversation. If you don't have enough information (e.g. no \
insurance ID given), ask for it rather than guessing.

Known patient context:
{context}
"""


def _patient_context(patient_request: PatientRequest, patient_id: str | None) -> str:
    lines = [
        f"- patient_id: {patient_id or 'unknown'}",
        f"- specialty: {patient_request.specialty or 'not stated'}",
        f"- insurance_id: {patient_request.insurance_id or 'not stated'}",
        f"- urgency: {patient_request.urgency.value}",
    ]
    return "\n".join(lines)


def run_insurance_agent(
    patient_request: PatientRequest,
    user_message: str,
    patient_id: str | None = None,
    model: str | None = None,
    max_turns: int = 5,
) -> dict:
    """Run one turn of the insurance agent. Returns {response, flagged, tool_calls}."""
    if patient_request.seeks_clinical_advice or is_clinical_advice_request(user_message):
        flag_for_human(reason="clinical escalation", message_text=user_message, patient_id=patient_id)
        return {"response": REFUSAL_MESSAGE, "flagged": True, "tool_calls": []}

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT.format(context=_patient_context(patient_request, patient_id))},
        {"role": "user", "content": user_message},
    ]
    tool_call_log = []
    flagged = False

    for _ in range(max_turns):
        try:
            assistant_message = chat_message(messages, tools=TOOLS, model=model)
        except Exception as exc:
            logger.warning("Insurance agent LLM call failed, escalating to human: %s", exc)
            flag_for_human(reason=f"agent error: {exc}", message_text=user_message, patient_id=patient_id)
            return {
                "response": "I'm having trouble processing that right now -- I've flagged it for a human care coordinator to follow up.",
                "flagged": True,
                "tool_calls": tool_call_log,
            }
        tool_calls = getattr(assistant_message, "tool_calls", None) or assistant_message.get("tool_calls")
        if not tool_calls:
            content = assistant_message.get("content") if isinstance(assistant_message, dict) else assistant_message.content
            return {"response": content or "", "flagged": flagged, "tool_calls": tool_call_log}

        messages.append(assistant_message)
        for call in tool_calls:
            name = call.function.name
            try:
                args = json.loads(call.function.arguments)
            except json.JSONDecodeError:
                args = {}
            fn = _DISPATCH.get(name)
            result = fn(**args) if fn else {"success": False, "error": f"Unknown tool {name}"}
            if name == "flag_for_human":
                flagged = True
            tool_call_log.append({"name": name, "args": args, "result": result})
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(result, default=str),
                }
            )

    return {
        "response": "I need to escalate this -- I wasn't able to resolve it within my tool budget.",
        "flagged": flagged,
        "tool_calls": tool_call_log,
    }
