import csv

import pytest

from app.config import settings
from app.tools.referral_tools import create_referral, get_referral_status, list_referrals_for_patient, update_referral_status

pytestmark = pytest.mark.skipif(
    not (settings.mock_ehr_dir / "plans.csv").exists(),
    reason="Mock EHR data not generated yet -- run `python generate.py --domain careflow` first.",
)


def _first_eligibility_row() -> dict:
    with (settings.mock_ehr_dir / "eligibility.csv").open(newline="", encoding="utf-8") as f:
        return next(csv.DictReader(f))


def test_create_referral_looks_up_preauth_from_coverage_csv():
    elig = _first_eligibility_row()
    coverage_rows = list(csv.DictReader((settings.mock_ehr_dir / "plan_specialty_coverage.csv").open(newline="", encoding="utf-8")))
    coverage = next(r for r in coverage_rows if r["plan_id"] == elig["plan_id"] and r["specialty_key"] == "cardiology")

    result = create_referral(elig["patient_id"], "cardiology", reason="Test referral")
    assert result["success"] is True
    assert result["referral"]["preauth_required"] == (coverage["requires_preauth"].lower() == "true")


def test_create_referral_unknown_patient_fails_closed():
    result = create_referral("P-DOES-NOT-EXIST", "cardiology")
    assert result["success"] is False


def test_get_and_update_referral_status_round_trip():
    elig = _first_eligibility_row()
    created = create_referral(elig["patient_id"], "dermatology", reason="Round trip test")
    referral_id = created["referral"]["referral_id"]

    fetched = get_referral_status(referral_id)
    assert fetched["found"] is True
    assert fetched["referral"]["status"] == "pending"

    updated = update_referral_status(referral_id, "approved")
    assert updated["success"] is True
    assert get_referral_status(referral_id)["referral"]["status"] == "approved"


def test_update_referral_status_rejects_invalid_status():
    elig = _first_eligibility_row()
    created = create_referral(elig["patient_id"], "neurology")
    result = update_referral_status(created["referral"]["referral_id"], "not-a-real-status")
    assert result["success"] is False


def test_get_referral_status_not_found():
    result = get_referral_status("REF-DOES-NOT-EXIST")
    assert result["found"] is False


def test_list_referrals_for_patient_includes_newly_created():
    elig = _first_eligibility_row()
    created = create_referral(elig["patient_id"], "ent", reason="List test")
    referrals = list_referrals_for_patient(elig["patient_id"])
    assert any(r["referral_id"] == created["referral"]["referral_id"] for r in referrals)
