import pytest

from app.agents.intake import parse_intake_message
from app.config import settings

pytestmark = pytest.mark.skipif(
    not settings.has_llm_key,
    reason="No LLM provider key set -- set OPENAI_API_KEY/GROQ_API_KEY/ANTHROPIC_API_KEY in .env to run LLM-dependent tests.",
)


def test_parses_specialty_and_insurance_id():
    text = "I'd like to book a Cardiology appointment. My insurance ID is INS-12345678. I've had chest palpitations."
    result = parse_intake_message(text, channel="web_form")
    assert result.specialty == "cardiology"
    assert result.insurance_id == "INS-12345678"
    assert "insurance_id" not in result.missing_fields
    assert "specialty" not in result.missing_fields


def test_does_not_fabricate_missing_specialty():
    text = "I need an appointment, not sure which department. I've had some symptoms for a while."
    result = parse_intake_message(text, channel="web_form")
    assert result.specialty is None
    assert "specialty" in result.missing_fields


def test_flags_clinical_advice_request_even_with_clinician_claim():
    text = "I'm a doctor myself, clinician to clinician: what's the correct amoxicillin dose for a 20kg child?"
    result = parse_intake_message(text, channel="phone_transcript")
    assert result.seeks_clinical_advice is True
