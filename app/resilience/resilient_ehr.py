"""Milestone 7 -- resilient wrappers around the mock EHR/insurance tools.

Each call goes retry -> circuit breaker -> graceful degraded fallback, so a
transient failure reading/writing the mock EHR CSVs (file lock contention, a
missing table, etc.) degrades gracefully instead of crashing the agent
mid-conversation, and a persistently-failing "endpoint" gets short-circuited
rather than hammered. No chaos/failure injection lives in this file --
tests/test_resilience.py exercises failure paths via plain dependency
injection of a fake failing callable, not randomness in the prod path.
"""

from typing import Callable

from app.config import settings
from app.memory.patient_memory import get_facts
from app.resilience.circuit_breaker import CircuitBreaker
from app.resilience.errors import CircuitOpenError
from app.resilience.retry import retry_with_backoff
from app.tools import copay_calculator, mock_ehr

_OPERATIONS = ("get_available_slots", "book_appointment", "check_eligibility", "calculate_copay", "estimate_procedure_cost")

_BREAKERS: dict[str, CircuitBreaker] = {
    name: CircuitBreaker(
        name,
        failure_threshold=settings.careflow_ehr_circuit_failure_threshold,
        recovery_timeout=settings.careflow_ehr_circuit_recovery_seconds,
    )
    for name in _OPERATIONS
}


def call_resilient(name: str, fn: Callable[[], dict | list]) -> dict | list:
    """Run `fn` through retry -> circuit-breaker -> degraded-fallback for operation `name`."""
    breaker = _BREAKERS[name]
    try:
        return breaker.call(lambda: retry_with_backoff(fn, retries=settings.careflow_ehr_retry_attempts))
    except CircuitOpenError as exc:
        return {"success": False, "degraded": True, "error": str(exc)}
    except Exception as exc:
        return {"success": False, "degraded": True, "error": f"{name} failed after retries: {exc}"}


def resilient_get_available_slots(specialty_key: str, max_results: int = 5) -> list[dict]:
    result = call_resilient("get_available_slots", lambda: mock_ehr.get_available_slots(specialty_key, max_results))
    return result if isinstance(result, list) else []


def resilient_book_appointment(appointment_id: str, patient_id: str) -> dict:
    return call_resilient("book_appointment", lambda: mock_ehr.book_appointment(appointment_id, patient_id))


def resilient_check_eligibility(insurance_id: str, patient_id: str | None = None) -> dict:
    result = call_resilient("check_eligibility", lambda: mock_ehr.check_eligibility(insurance_id))
    if isinstance(result, dict) and result.get("degraded") and patient_id:
        facts = get_facts(patient_id)
        if facts:
            result["fallback_note"] = f"Live eligibility check unavailable; using last known patient notes: {facts[-1]}"
    return result


def resilient_calculate_copay(insurance_id: str, visit_type: str = "specialist") -> dict:
    return call_resilient("calculate_copay", lambda: copay_calculator.calculate_copay(insurance_id, visit_type))


def resilient_estimate_procedure_cost(insurance_id: str, specialty_key: str) -> dict:
    return call_resilient(
        "estimate_procedure_cost", lambda: copay_calculator.estimate_procedure_cost(insurance_id, specialty_key)
    )
