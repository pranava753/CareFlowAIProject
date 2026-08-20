import pytest

from app.resilience.circuit_breaker import CircuitBreaker, CircuitState
from app.resilience.errors import CircuitOpenError
from app.resilience.resilient_ehr import call_resilient
from app.resilience.retry import retry_with_backoff


def test_retry_with_backoff_succeeds_after_transient_failures():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("transient")
        return "ok"

    result = retry_with_backoff(flaky, retries=3, base_delay=0.0)
    assert result == "ok"
    assert calls["n"] == 3


def test_retry_with_backoff_raises_after_exhausting_retries():
    def always_fails():
        raise ConnectionError("permanent")

    with pytest.raises(ConnectionError):
        retry_with_backoff(always_fails, retries=2, base_delay=0.0)


def test_circuit_breaker_opens_after_threshold_and_short_circuits():
    breaker = CircuitBreaker("test-op", failure_threshold=2, recovery_timeout=999)

    def always_fails():
        raise RuntimeError("boom")

    for _ in range(2):
        with pytest.raises(RuntimeError):
            breaker.call(always_fails)

    assert breaker.state == CircuitState.OPEN
    with pytest.raises(CircuitOpenError):
        breaker.call(always_fails)


def test_circuit_breaker_closes_again_on_success():
    breaker = CircuitBreaker("test-op-2", failure_threshold=1, recovery_timeout=0.0)

    def fails():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        breaker.call(fails)
    assert breaker.state == CircuitState.HALF_OPEN  # recovery_timeout=0 -> immediately eligible

    assert breaker.call(lambda: "recovered") == "recovered"
    assert breaker.state == CircuitState.CLOSED


def test_call_resilient_returns_degraded_dict_after_retries_and_breaker_exhausted():
    def always_fails():
        raise OSError("mock ehr csv unavailable")

    # careflow_ehr_retry_attempts + failure_threshold come from settings; call enough
    # times to guarantee the breaker for this fresh operation name trips.
    name = "test_call_resilient_op"
    from app.resilience.resilient_ehr import _BREAKERS

    _BREAKERS[name] = CircuitBreaker(name, failure_threshold=1, recovery_timeout=999)
    result = call_resilient(name, always_fails)
    assert result == {"success": False, "degraded": True, "error": "test_call_resilient_op failed after retries: mock ehr csv unavailable"}
