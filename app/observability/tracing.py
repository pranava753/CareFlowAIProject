"""Milestone 7 -- LangFuse tracing.

LiteLLM has a native Langfuse callback ("langfuse" success/failure callback
string) that traces every app/llm.py completion call automatically -- no
manual span code needed for LLM calls themselves. `configure_tracing()`
turns that on only when Langfuse keys are actually present, so the app
behaves identically (and every test/CI run without Langfuse configured is
unaffected) whether or not tracing is enabled.

`observe` wraps the real `langfuse.decorators.observe` for the workflow/tool
boundaries that aren't plain LLM calls (the LangGraph workflow entrypoints,
the MCP tool dispatch) -- it's a no-op passthrough when Langfuse isn't
configured.
"""

import logging
from typing import Any, Callable, TypeVar

import litellm

from app.config import settings

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])

_configured = False


def configure_tracing() -> bool:
    """Enable LiteLLM's Langfuse callback if keys are configured. Returns whether it did."""
    global _configured
    if not settings.has_langfuse_keys:
        return False
    if not _configured:
        litellm.success_callback = ["langfuse"]
        litellm.failure_callback = ["langfuse"]
        _configured = True
        logger.info("LangFuse tracing enabled (host=%s).", settings.langfuse_host)
    return True


def observe(*decorator_args: Any, **decorator_kwargs: Any) -> Callable[[F], F]:
    """`langfuse.decorators.observe` when configured, otherwise a no-op passthrough."""
    if settings.has_langfuse_keys:
        from langfuse.decorators import observe as _observe

        return _observe(*decorator_args, **decorator_kwargs)

    def _noop_decorator(fn: F) -> F:
        return fn

    return _noop_decorator
