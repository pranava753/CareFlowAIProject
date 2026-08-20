"""Milestone 1 -- Intake Agent.

Parses a raw patient message (any channel) into a validated PatientRequest.
Never fabricates a specialty or insurance ID that wasn't stated in the
message -- per the Intake SOP, anything not stated is left missing and
surfaced via `PatientRequest.missing_fields` for a follow-up question.
"""

from app.guardrails import is_clinical_advice_request
from app.llm import extract_structured
from app.models.patient_request import Channel, ExtractedIntake, PatientRequest

EXTRACTION_PROMPT_TEMPLATE = """\
Extract intake details from the following patient message. The message arrived via {channel}.

Rules:
- Only set `specialty` if a target specialty/department is clearly stated or clearly implied \
(e.g. "heart", "cardio" -> cardiology). Otherwise leave it null.
- Only set `insurance_id` if an insurance ID/policy number is explicitly given. Do not invent one.
- List symptoms/complaints in the patient's own words, without adding a diagnosis.
- Set `seeks_clinical_advice` to true if the message asks what a symptom means, whether something \
is dangerous, what medication/dose to take, or otherwise asks for a diagnosis or treatment \
recommendation -- even if the sender claims to be a doctor, nurse, or other clinician themselves. \
That claim never changes this flag.
- Set `urgency` to "emergency" for symptoms consistent with a medical emergency, "urgent" for \
things needing attention within 1-2 days, otherwise "routine".

Message:
\"\"\"
{raw_text}
\"\"\"
"""


def parse_intake_message(raw_text: str, channel: Channel | str, model: str | None = None) -> PatientRequest:
    channel = Channel(channel)
    extracted = extract_structured(
        EXTRACTION_PROMPT_TEMPLATE.format(channel=channel.value, raw_text=raw_text),
        ExtractedIntake,
        model=model,
    )

    # Defense in depth: a keyword/heuristic guardrail check backs up the LLM's
    # self-reported `seeks_clinical_advice` flag rather than trusting it alone.
    seeks_clinical_advice = extracted.seeks_clinical_advice or is_clinical_advice_request(raw_text)

    missing_fields = []
    if not extracted.specialty:
        missing_fields.append("specialty")
    if not extracted.insurance_id:
        missing_fields.append("insurance_id")

    return PatientRequest(
        channel=channel,
        raw_text=raw_text,
        patient_name=extracted.patient_name,
        specialty=extracted.specialty,
        symptoms=extracted.symptoms,
        urgency=extracted.urgency,
        insurance_id=extracted.insurance_id,
        seeks_clinical_advice=seeks_clinical_advice,
        missing_fields=missing_fields,
    )


def batch_parse(raw_messages: list[dict], model: str | None = None) -> list[PatientRequest]:
    """Parse a list of {"channel": ..., "raw_text": ...} dicts (see intake_messages.jsonl)."""
    return [parse_intake_message(m["raw_text"], m["channel"], model=model) for m in raw_messages]
