"""Milestone 2 -- co-pay calculator.

Reads plans.csv / plan_specialty_coverage.csv / eligibility.csv directly
(the same authoritative tables generate.py renders the Cost-Share Schedule
and Pre-Authorization Matrix documents from), so a number returned here can
never disagree with the policy corpus.
"""

import csv
from pathlib import Path

from app.config import settings


def _read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def calculate_copay(insurance_id: str, visit_type: str = "specialist") -> dict:
    """Flat office-visit copay for a patient's plan.

    visit_type: "specialist" or "primary_care".
    """
    if visit_type not in ("specialist", "primary_care"):
        return {"success": False, "error": "visit_type must be 'specialist' or 'primary_care'."}

    eligibility_rows = _read_csv(settings.mock_ehr_dir / "eligibility.csv")
    elig = next((r for r in eligibility_rows if r["insurance_id"] == insurance_id), None)
    if elig is None:
        return {"success": False, "error": f"No eligibility record found for insurance ID {insurance_id}."}

    plans = _read_csv(settings.mock_ehr_dir / "plans.csv")
    plan = next((p for p in plans if p["plan_id"] == elig["plan_id"]), None)
    if plan is None:
        return {"success": False, "error": f"Plan {elig['plan_id']} not found."}

    copay_field = "specialist_copay_usd" if visit_type == "specialist" else "primary_care_copay_usd"
    return {
        "success": True,
        "plan_id": plan["plan_id"],
        "plan_name": plan["plan_name"],
        "visit_type": visit_type,
        "copay_usd": float(plan[copay_field]),
        "deductible_remaining_usd": float(elig["deductible_remaining_usd"]),
        "note": (
            "This copay applies to the office visit itself. Any procedure performed during the "
            "visit is billed separately under coinsurance -- use the pre-authorization / coverage "
            "lookup for a specific procedure's estimated cost."
        ),
    }


def estimate_procedure_cost(insurance_id: str, specialty_key: str) -> dict:
    """Estimated patient cost-share for the specialty's typical procedure, and whether it needs pre-auth."""
    eligibility_rows = _read_csv(settings.mock_ehr_dir / "eligibility.csv")
    elig = next((r for r in eligibility_rows if r["insurance_id"] == insurance_id), None)
    if elig is None:
        return {"success": False, "error": f"No eligibility record found for insurance ID {insurance_id}."}

    coverage_rows = _read_csv(settings.mock_ehr_dir / "plan_specialty_coverage.csv")
    coverage = next(
        (r for r in coverage_rows if r["plan_id"] == elig["plan_id"] and r["specialty_key"] == specialty_key),
        None,
    )
    if coverage is None:
        return {"success": False, "error": f"No coverage rule found for plan {elig['plan_id']} / specialty {specialty_key}."}

    estimated_cost = float(coverage["estimated_cost_usd"])
    deductible_remaining = float(elig["deductible_remaining_usd"])
    coverage_pct_after_deductible = float(coverage["plan_coverage_pct_after_deductible"])

    amount_toward_deductible = min(estimated_cost, deductible_remaining)
    remaining_after_deductible = max(0.0, estimated_cost - amount_toward_deductible)
    patient_coinsurance_share = round(remaining_after_deductible * (1 - coverage_pct_after_deductible / 100), 2)
    estimated_patient_cost = round(amount_toward_deductible + patient_coinsurance_share, 2)

    return {
        "success": True,
        "specialty_key": specialty_key,
        "typical_procedure": coverage["typical_procedure"],
        "estimated_total_cost_usd": estimated_cost,
        "requires_preauth": coverage["requires_preauth"].lower() == "true",
        "preauth_turnaround_business_days": int(coverage["preauth_turnaround_business_days"]),
        "estimated_patient_cost_usd": estimated_patient_cost,
        "note": "Estimate only; final cost depends on the claim actually submitted by the provider.",
    }
