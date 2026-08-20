"""Milestone 7 -- circuit breaker.

Standard CLOSED -> OPEN -> HALF_OPEN -> CLOSED state machine, one instance
per protected operation (see app/resilience/resilient_ehr.py). While OPEN,
calls short-circuit immediately (raising CircuitOpenError) instead of
hammering a failing mock EHR/insurance endpoint; after `recovery_timeout`
seconds it allows one HALF_OPEN trial call to decide whether to close again.
"""

import time
from enum import Enum
from typing import Callable, TypeVar

from app.resilience.errors import CircuitOpenError

T = TypeVar("T")


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(self, name: str, failure_threshold: int = 3, recovery_timeout: float = 30.0):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._opened_at: float | None = None

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN and self._opened_at is not None:
            if time.monotonic() - self._opened_at >= self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
        return self._state

    def call(self, fn: Callable[[], T], *, exceptions: tuple[type[Exception], ...] = (Exception,)) -> T:
        if self.state == CircuitState.OPEN:
            raise CircuitOpenError(f"Circuit '{self.name}' is open; call short-circuited.")

        try:
            result = fn()
        except exceptions:
            self._on_failure()
            raise
        else:
            self._on_success()
            return result

    def _on_success(self) -> None:
        self._failure_count = 0
        self._state = CircuitState.CLOSED
        self._opened_at = None

    def _on_failure(self) -> None:
        self._failure_count += 1
        if self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN
            self._opened_at = time.monotonic()

    def reset(self) -> None:
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._opened_at = None
