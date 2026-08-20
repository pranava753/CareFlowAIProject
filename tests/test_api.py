import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.config import settings

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_workflow_resume_rejects_invalid_decision():
    response = client.post("/workflow/resume", json={"session_id": "does-not-matter", "decision": "not-a-real-decision"})
    assert response.status_code == 422


@pytest.mark.skipif(
    not settings.has_llm_key,
    reason="No LLM provider key set -- set OPENAI_API_KEY/GROQ_API_KEY/ANTHROPIC_API_KEY in .env to run LLM-dependent tests.",
)
def test_intake_endpoint():
    response = client.post(
        "/intake",
        json={"raw_text": "I'd like to book a Cardiology appointment. My insurance ID is INS-12345678.", "channel": "web_form"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["specialty"] == "cardiology"
    assert body["insurance_id"] == "INS-12345678"
