"""Milestone 5/6 -- referral tracking tools.

Same CSV read/write pattern as app/tools/mock_ehr.py, operating on
data/careflow/mock_ehr/referrals.csv. preauth_required is looked up from
plan_specialty_coverage.csv (via the patient's eligibility record) rather
than guessed, so it can never disagree with the coverage/pre-authorization
corpus documents.
"""

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.config import settings

REFERRAL_STATUSES = ("pending", "approved", "scheduled", "completed", "expired", "cancelled")
_VALID_TURNAROUND_DAYS = 60


def _read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _next_referral_id(rows: list[dict]) -> str:
    existing = [int(r["referral_id"].removeprefix("REF-")) for r in rows if r["referral_id"].startswith("REF-")]
    next_n = (max(existing) + 1) if existing else 1
    return f"REF-{next_n:05d}"


def _lookup_preauth_required(patient_id: str, specialty_key: str) -> bool | None:
    eligibility_rows = _read_csv(settings.mock_ehr_dir / "eligibility.csv")
    elig = next((r for r in eligibility_rows if r["patient_id"] == patient_id), None)
    if elig is None:
        return None
    coverage_rows = _read_csv(settings.mock_ehr_dir / "plan_specialty_coverage.csv")
    coverage = next(
        (r for r in coverage_rows if r["plan_id"] == elig["plan_id"] and r["specialty_key"] == specialty_key),
        None,
    )
    if coverage is None:
        return None
    return coverage["requires_preauth"].lower() == "true"


def create_referral(
    patient_id: str,
    specialty_key: str,
    referring_provider: str = "Self-referral",
    reason: str = "",
) -> dict:
    """Create a new referral record. preauth_required is looked up, never guessed."""
    path = settings.mock_ehr_dir / "referrals.csv"
    rows = _read_csv(path)
    fieldnames = list(rows[0].keys()) if rows else [
        "referral_id", "patient_id", "specialty_key", "referring_provider", "reason",
        "status", "preauth_required", "preauth_status", "created_date", "valid_until_date",
    ]

    preauth_required = _lookup_preauth_required(patient_id, specialty_key)
    if preauth_required is None:
        return {"success": False, "error": f"No coverage rule found for patient {patient_id} / specialty {specialty_key}."}

    today = datetime.now(timezone.utc).date()
    referral = {
        "referral_id": _next_referral_id(rows),
        "patient_id": patient_id,
        "specialty_key": specialty_key,
        "referring_provider": referring_provider,
        "reason": reason,
        "status": "pending",
        "preauth_required": preauth_required,
        "preauth_status": "pending" if preauth_required else "",
        "created_date": today.isoformat(),
        "valid_until_date": (today + timedelta(days=_VALID_TURNAROUND_DAYS)).isoformat(),
    }
    rows.append(referral)
    _write_csv(path, rows, fieldnames)
    return {"success": True, "referral": referral}


def get_referral_status(referral_id: str) -> dict:
    rows = _read_csv(settings.mock_ehr_dir / "referrals.csv")
    referral = next((r for r in rows if r["referral_id"] == referral_id), None)
    if referral is None:
        return {"found": False, "error": f"No referral found with id {referral_id}."}
    return {"found": True, "referral": referral}


def update_referral_status(referral_id: str, status: str) -> dict:
    if status not in REFERRAL_STATUSES:
        return {"success": False, "error": f"status must be one of {REFERRAL_STATUSES}."}

    path = settings.mock_ehr_dir / "referrals.csv"
    rows = _read_csv(path)
    if not rows:
        return {"success": False, "error": f"No referral found with id {referral_id}."}
    fieldnames = list(rows[0].keys())
    target = next((r for r in rows if r["referral_id"] == referral_id), None)
    if target is None:
        return {"success": False, "error": f"No referral found with id {referral_id}."}

    target["status"] = status
    _write_csv(path, rows, fieldnames)
    return {"success": True, "referral": target}


def list_referrals_for_patient(patient_id: str) -> list[dict]:
    rows = _read_csv(settings.mock_ehr_dir / "referrals.csv")
    return [r for r in rows if r["patient_id"] == patient_id]
