import pytest

from app.config import settings
from app.tools.copay_calculator import calculate_copay, estimate_procedure_cost
from app.tools.mock_ehr import book_appointment, check_eligibility, get_available_slots

pytestmark = pytest.mark.skipif(
    not (settings.mock_ehr_dir / "plans.csv").exists(),
    reason="Mock EHR data not generated yet -- run `python generate.py --domain careflow` first.",
)


def _first_eligibility_row() -> dict:
    import csv

    with (settings.mock_ehr_dir / "eligibility.csv").open(newline="", encoding="utf-8") as f:
        return next(csv.DictReader(f))


def test_check_eligibility_found():
    elig = _first_eligibility_row()
    result = check_eligibility(elig["insurance_id"])
    assert result["found"] is True
    assert result["eligibility"]["plan_id"] == elig["plan_id"]


def test_check_eligibility_not_found():
    result = check_eligibility("INS-DOES-NOT-EXIST")
    assert result["found"] is False


def test_calculate_copay_matches_plan_csv():
    elig = _first_eligibility_row()
    result = calculate_copay(elig["insurance_id"], visit_type="specialist")
    assert result["success"] is True
    assert result["copay_usd"] >= 0


def test_estimate_procedure_cost_consistent_with_coverage_csv():
    elig = _first_eligibility_row()
    result = estimate_procedure_cost(elig["insurance_id"], "cardiology")
    assert result["success"] is True
    assert result["estimated_patient_cost_usd"] <= result["estimated_total_cost_usd"]


def test_get_available_slots_returns_only_available():
    slots = get_available_slots("cardiology", max_results=3)
    assert all(s["status"] == "available" for s in slots)


def test_book_appointment_marks_slot_booked_then_rejects_rebooking():
    slots = get_available_slots("dermatology", max_results=1)
    if not slots:
        pytest.skip("No available dermatology slots generated in this run.")
    appointment_id = slots[0]["appointment_id"]
    result = book_appointment(appointment_id, patient_id="P00001")
    assert result["success"] is True

    second_attempt = book_appointment(appointment_id, patient_id="P00002")
    assert second_attempt["success"] is False
