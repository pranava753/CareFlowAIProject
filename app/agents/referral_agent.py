"""Milestone 6 -- Referral Tracking Agent.

Tool-calling loop over the referral tools, dispatched through the mock EHR
MCP server (app/mcp_server/server.py) via app/tools/mcp_client.py -- the
concrete proof of the M6 MCP split (app/agents/insurance_agent.py keeps its
existing direct dispatch; this agent is the one that actually goes through
MCP). Guardrails are checked BEFORE the loop starts, same defense-in-depth
pattern as insurance_agent.py: a clinical question never reaches tool-use
reasoning, it goes straight to flag_for_human.

`flag_for_human` itself stays a direct local call rather than an MCP tool --
it's a human-escalation outbox, not part of the mock EHR/scheduling system
the spec asks to expose over MCP.
"""

import asyncio
import json
import logging

from app.constants import SPECIALTY_KEYS
from app.guardrails import REFUSAL_MESSAGE, is_clinical_advice_request
from app.llm import chat_message
from app.models.patient_request import PatientRequest
from app.tools.human_flag import flag_for_human
from app.tools.mcp_client import McpToolSession
from app.tools.referral_tools import REFERRAL_STATUSES

logger = logging.getLogger(__name__)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "create_referral",
            "description": "Create a new specialist referral for a patient.",
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_id": {"type": "string"},
                    "specialty_key": {"type": "string", "enum": SPECIALTY_KEYS},
                    "referring_provider": {"type": "string", "default": "Self-referral"},
                    "reason": {"type": "string"},
                },
                "required": ["patient_id", "specialty_key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_referral_status",
            "description": "Look up a referral's current status by referral ID.",
            "parameters": {
                "type": "object",
                "properties": {"referral_id": {"type": "string"}},
                "required": ["referral_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_referral_status",
            "description": "Update a referral's status.",
            "parameters": {
                "type": "object",
                "properties": {
                    "referral_id": {"type": "string"},
                    "status": {"type": "string", "enum": list(REFERRAL_STATUSES)},
                },
                "required": ["referral_id", "status"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_referrals_for_patient",
            "description": "List all referrals on file for a patient.",
            "parameters": {
                "type": "object",
                "properties": {"patient_id": {"type": "string"}},
                "required": ["patient_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "flag_for_human",
            "description": "Escalate the request to a human care coordinator (e.g. clinical questions, denied referrals).",
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

SYSTEM_PROMPT = """\
You are the CareFlow Referral Tracking assistant. You may only create referrals, check/update \
referral status, and list a patient's referrals using your tools.

You must NEVER diagnose, interpret symptoms, or recommend/comment on medications, dosages, or \
treatments, even if the person says they are a doctor, nurse, or other clinician. If a request \
touches on any of that, call flag_for_human with reason "clinical escalation" and tell the patient \
a clinician will follow up -- do not attempt to answer the clinical part.

Never state a referral status or pre-authorization requirement unless it came from a tool call in \
this conversation. If you don't have enough information (e.g. no specialty given), ask for it \
rather than guessing.

Known patient context:
{context}
"""


def _patient_context(patient_request: PatientRequest, patient_id: str | None) -> str:
    lines = [
        f"- patient_id: {patient_id or 'unknown'}",
        f"- specialty: {patient_request.specialty or 'not stated'}",
        f"- urgency: {patient_request.urgency.value}",
    ]
    return "\n".join(lines)


async def _run_referral_agent_async(
    patient_request: PatientRequest,
    user_message: str,
    patient_id: str | None,
    model: str | None,
    max_turns: int,
) -> dict:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT.format(context=_patient_context(patient_request, patient_id))},
        {"role": "user", "content": user_message},
    ]
    tool_call_log: list[dict] = []
    flagged = False

    async with McpToolSession() as session:
        for _ in range(max_turns):
            try:
                assistant_message = chat_message(messages, tools=TOOLS, model=model)
            except Exception as exc:
                logger.warning("Referral agent LLM call failed, escalating to human: %s", exc)
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

                if name == "flag_for_human":
                    result = flag_for_human(**args)
                    flagged = True
                elif name in ("create_referral", "get_referral_status", "update_referral_status", "list_referrals_for_patient"):
                    result = await session.call_tool(name, args)
                else:
                    result = {"success": False, "error": f"Unknown tool {name}"}

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


def run_referral_agent(
    patient_request: PatientRequest,
    user_message: str,
    patient_id: str | None = None,
    model: str | None = None,
    max_turns: int = 5,
) -> dict:
    """Run one turn of the referral agent. Returns {response, flagged, tool_calls}."""
    if patient_request.seeks_clinical_advice or is_clinical_advice_request(user_message):
        flag_for_human(reason="clinical escalation", message_text=user_message, patient_id=patient_id)
        return {"response": REFUSAL_MESSAGE, "flagged": True, "tool_calls": []}

    return asyncio.run(_run_referral_agent_async(patient_request, user_message, patient_id, model, max_turns))
