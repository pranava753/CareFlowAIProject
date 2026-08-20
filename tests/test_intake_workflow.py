import csv

import pytest

import app.graph.intake_workflow as workflow_module
from app.config import settings
from app.models.clinical_review import ClinicalReviewVerdict
from app.models.patient_request import Channel, PatientRequest, Urgency

pytestmark = pytest.mark.skipif(
    not (settings.mock_ehr_dir / "plans.csv").exists(),
    reason="Mock EHR data not generated yet -- run `python generate.py --domain careflow` first.",
)


@pytest.fixture(autouse=True)
def _isolated_checkpoint_db(tmp_path, monkeypatch):
    """Point the workflow's SqliteSaver singleton at a fresh temp DB per test.

    Both @lru_cache singletons (checkpointer + compiled graph) are cleared
    before and after each test so tests don't see each other's checkpoints
    or a stale compiled graph pointing at a closed connection.
    """
    monkeypatch.setattr(settings, "careflow_workflow_checkpoint_db", tmp_path / "workflow_checkpoints.sqlite")
    workflow_module.get_workflow_checkpointer.cache_clear()
    workflow_module.get_compiled_workflow.cache_clear()
    yield
    workflow_module.close_workflow_checkpointer()
    workflow_module.get_compiled_workflow.cache_clear()


def _first_eligibility_row() -> dict:
    with (settings.mock_ehr_dir / "eligibility.csv").open(newline="", encoding="utf-8") as f:
        return next(csv.DictReader(f))


def _patch_intake(monkeypatch, *, specialty: str, insurance_id: str, seeks_clinical_advice: bool = False):
    def fake_parse(raw_text, channel):
        return PatientRequest(
            channel=Channel(channel),
            raw_text=raw_text,
            specialty=specialty,
            insurance_id=insurance_id,
            urgency=Urgency.ROUTINE,
            seeks_clinical_advice=seeks_clinical_advice,
        )

    monkeypatch.setattr(workflow_module, "parse_intake_message", fake_parse)


def _patch_review(monkeypatch, *, requires_human_review: bool):
    def fake_review(raw_text, model=None):
        return ClinicalReviewVerdict(requires_human_review=requires_human_review, rationale="test stub")

    monkeypatch.setattr(workflow_module, "review_message", fake_review)


def test_happy_path_runs_straight_through_to_finalize(monkeypatch):
    elig = _first_eligibility_row()
    _patch_intake(monkeypatch, specialty="cardiology", insurance_id=elig["insurance_id"])
    _patch_review(monkeypatch, requires_human_review=False)

    result = workflow_module.run_intake_workflow(
        "I'd like to book a cardiology appointment.", "web_form", session_id="test-happy-path", patient_id=elig["patient_id"]
    )

    assert result["status"] == "completed"
    assert result["flagged"] is False
    assert result["eligibility"]["found"] is True
    assert result["referral"] is not None
    assert result["referral"]["referral"]["specialty_key"] == "cardiology"


def test_clinical_flag_pauses_for_human_review_then_confirms_escalation(monkeypatch):
    elig = _first_eligibility_row()
    _patch_intake(monkeypatch, specialty=None, insurance_id=elig["insurance_id"], seeks_clinical_advice=False)
    _patch_review(monkeypatch, requires_human_review=True)

    started = workflow_module.run_intake_workflow(
        "What dose of amoxicillin should I give my child?", "sms", session_id="test-escalate", patient_id=elig["patient_id"]
    )
    assert started["status"] == "needs_human_review"
    assert started["session_id"] == "test-escalate"

    resumed = workflow_module.resume_intake_workflow("test-escalate", "confirm_escalate")
    assert resumed["status"] == "completed"
    assert resumed["flagged"] is True
    assert "not able to give medical advice" in resumed["final_response"]


def test_clinical_flag_override_proceeds_to_eligibility(monkeypatch):
    elig = _first_eligibility_row()
    _patch_intake(monkeypatch, specialty="dermatology", insurance_id=elig["insurance_id"])
    _patch_review(monkeypatch, requires_human_review=True)

    started = workflow_module.run_intake_workflow(
        "Borderline message flagged for review", "email", session_id="test-override", patient_id=elig["patient_id"]
    )
    assert started["status"] == "needs_human_review"

    resumed = workflow_module.resume_intake_workflow("test-override", "override_proceed")
    assert resumed["status"] == "completed"
    assert resumed["flagged"] is False
    assert resumed["eligibility"]["found"] is True
