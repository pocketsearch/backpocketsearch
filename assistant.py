"""Groq-backed assistant module for pocketSearch.

Configuration is driven entirely by environment variables:
  GROQ_API_KEY   - Groq API key (required to enable the assistant)
  GROQ_MODEL     - model name (default: llama-3.1-70b-versatile)
  GROQ_TIMEOUT   - request timeout in seconds (default: 30)

When GROQ_API_KEY is not set the assistant is disabled and
``get_response()`` raises ``AssistantDisabledError``.
"""

import os

_SYSTEM_PROMPT = (
    "You are a concise assistant. "
    "Answer directly, clearly, and accurately. "
    "Be blunt but not rude. "
    "Do not claim certainty when unsure. "
    "Refuse unsafe requests when needed."
)

_DEFAULT_MODEL = "llama-3.1-70b-versatile"
_DEFAULT_TIMEOUT = 30


class AssistantDisabledError(RuntimeError):
    """Raised when the assistant is not configured (missing GROQ_API_KEY)."""


def is_enabled() -> bool:
    """Return True if the Groq API key is configured."""
    return bool(os.environ.get("GROQ_API_KEY", "").strip())


def get_response(user_text: str) -> str:
    """Return a Groq assistant response for *user_text*.

    Raises:
        AssistantDisabledError: if GROQ_API_KEY is not set.
        groq.APIError (or subclasses): on API-level errors.
    """
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        raise AssistantDisabledError(
            "GROQ_API_KEY is not set. Configure it to enable the assistant."
        )

    from groq import Groq  # imported lazily so the app runs without groq installed

    model = os.environ.get("GROQ_MODEL", _DEFAULT_MODEL).strip() or _DEFAULT_MODEL
    timeout_raw = os.environ.get("GROQ_TIMEOUT", str(_DEFAULT_TIMEOUT))
    try:
        timeout = int(timeout_raw)
    except (ValueError, TypeError):
        timeout = _DEFAULT_TIMEOUT

    client = Groq(api_key=api_key, timeout=timeout)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
        ],
        temperature=0.2,
    )
    return resp.choices[0].message.content
