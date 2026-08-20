class TransientEHRError(Exception):
    """Raised by a mock EHR/insurance call that should be retried."""


class CircuitOpenError(Exception):
    """Raised instead of calling through when a circuit breaker is OPEN."""
