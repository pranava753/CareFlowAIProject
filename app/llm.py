import json
import logging
import time
from typing import Any, Type, TypeVar

import litellm
from pydantic import BaseModel, ValidationError

from app.config import settings
from app.observability.tracing import configure_tracing

logger = logging.getLogger(__name__)

configure_tracing()

T = TypeVar("T", bound=BaseModel)

# Some providers (observed with Groq's Llama-3.3 tool calling) occasionally
# emit a malformed function-call token that the provider's own API then
# rejects with a 400 "tool_use_failed" BadRequestError -- not a real prompt
# problem, just model flakiness on that turn. A same-request retry usually
# succeeds since the model rarely repeats the same malformed output twice.
_TRANSIENT_RETRIES = 2
_TRANSIENT_RETRY_DELAY_SECONDS = 1.0

# Free-tier providers (e.g. Groq's on-demand tier) enforce a tokens-per-minute
# cap well below what a multi-turn tool-calling demo can burn through in one
# run. A short request-level retry can't fix that -- the window itself needs
# to roll over -- so this waits long enough for it to, rather than failing an
# otherwise-correct call.
_RATE_LIMIT_RETRIES = 3
_RATE_LIMIT_RETRY_DELAY_SECONDS = 8.0


def _completion_with_retries(**kwargs: Any) -> Any:
    bad_request_attempts = 0
    rate_limit_attempts = 0
    while True:
        try:
            return litellm.completion(**kwargs)
        except litellm.exceptions.BadRequestError:
            bad_request_attempts += 1
            if bad_request_attempts > _TRANSIENT_RETRIES:
                raise
            logger.warning(
                "LLM call failed (attempt %d/%d), retrying: %s", bad_request_attempts, _TRANSIENT_RETRIES, kwargs.get("model")
            )
            time.sleep(_TRANSIENT_RETRY_DELAY_SECONDS)
        except litellm.exceptions.RateLimitError:
            rate_limit_attempts += 1
            if rate_limit_attempts > _RATE_LIMIT_RETRIES:
                raise
            logger.warning(
                "LLM call rate-limited (attempt %d/%d), waiting %.0fs.",
                rate_limit_attempts, _RATE_LIMIT_RETRIES, _RATE_LIMIT_RETRY_DELAY_SECONDS,
            )
            time.sleep(_RATE_LIMIT_RETRY_DELAY_SECONDS)


def chat(messages: list[dict], model: str | None = None, **kwargs: Any) -> str:
    """Single completion call, returns the assistant's text content.

    No provider credential is passed explicitly -- LiteLLM resolves the right
    one (OPENAI_API_KEY, GROQ_API_KEY, ANTHROPIC_API_KEY, ...) from the
    environment based on the model string's provider prefix (e.g. "groq/...").
    """
    response = _completion_with_retries(
        model=model or settings.careflow_llm_model,
        messages=messages,
        **kwargs,
    )
    return response["choices"][0]["message"]["content"] or ""


def chat_message(messages: list[dict], tools: list[dict] | None = None, model: str | None = None, **kwargs: Any) -> Any:
    """Completion call that returns the raw assistant message (for tool-calling loops)."""
    response = _completion_with_retries(
        model=model or settings.careflow_llm_model,
        messages=messages,
        tools=tools,
        **kwargs,
    )
    return response["choices"][0]["message"]


def extract_structured(
    prompt: str,
    schema: Type[T],
    model: str | None = None,
    max_retries: int = 2,
    system: str | None = None,
) -> T:
    """Ask the model for JSON matching `schema`, validate, retry on failure.

    Never fabricates required-but-unstated fields: the system prompt explicitly
    instructs the model to leave anything not stated as null/empty, and callers
    (e.g. the intake agent) should treat missing values as missing, not guess them.
    """
    schema_json = json.dumps(schema.model_json_schema(), indent=2)
    system_prompt = system or (
        "You extract structured data from text. Respond with ONLY a single JSON object "
        "matching the given JSON schema. Never invent values that are not present or "
        "clearly implied in the text -- use null/empty for anything not stated."
    )
    messages: list[dict] = [
        {"role": "system", "content": f"{system_prompt}\n\nJSON schema:\n{schema_json}"},
        {"role": "user", "content": prompt},
    ]

    last_error: Exception | None = None
    for _ in range(max_retries + 1):
        raw = chat(messages, model=model, response_format={"type": "json_object"})
        try:
            data = json.loads(raw)
            return schema.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as exc:
            last_error = exc
            messages.append({"role": "assistant", "content": raw})
            messages.append(
                {
                    "role": "user",
                    "content": f"That was invalid: {exc}. Respond again with ONLY corrected JSON matching the schema.",
                }
            )
    raise ValueError(f"Failed to extract structured output after {max_retries + 1} attempts: {last_error}")
