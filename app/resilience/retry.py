"""Milestone 7 -- retry with backoff.

Hand-rolled rather than a dependency (tenacity/pybreaker): this is a small
capstone project and the retry/circuit-breaker logic is itself part of what
M7 is meant to demonstrate.
"""

import logging
import time
from typing import Callable, TypeVar

T = TypeVar("T")

logger = logging.getLogger(__name__)


def retry_with_backoff(
    fn: Callable[[], T],
    *,
    retries: int,
    base_delay: float = 0.2,
    exceptions: tuple[type[Exception], ...] = (Exception,),
) -> T:
    """Call `fn()`, retrying up to `retries` times on `exceptions` with linear backoff."""
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return fn()
        except exceptions as exc:
            last_error = exc
            if attempt < retries:
                delay = base_delay * (attempt + 1)
                logger.warning("Call failed (attempt %d/%d), retrying in %.1fs: %s", attempt + 1, retries + 1, delay, exc)
                time.sleep(delay)
    assert last_error is not None
    raise last_error
