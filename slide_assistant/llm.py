"""LLM provider adapters.

Every provider exposes ``generate_json(system, user, schema, schema_name) -> dict``.
Both hosted providers use *structured outputs* (JSON Schema constrained decoding),
so the response is always parseable JSON in the deck shape.

Providers:
- ``claude``  - Anthropic Claude via the official ``anthropic`` SDK
- ``openai``  - OpenAI GPT via the official ``openai`` SDK
- ``demo``    - offline, deterministic generator (no API key) for trying the UI/pipeline
"""

from __future__ import annotations

import json
import os
from typing import Protocol

DEFAULT_CLAUDE_MODEL = "claude-opus-5-5"
DEFAULT_OPENAI_MODEL = "gpt-4o"


class ProviderError(RuntimeError):
    """Raised for any provider failure with a message that is safe to show in the UI."""


class LLMProvider(Protocol):
    name: str
    model: str

    def generate_json(self, system: str, user: str, schema: dict, schema_name: str) -> dict: ...


# ---------------------------------------------------------------------------
# Anthropic Claude
# ---------------------------------------------------------------------------

class ClaudeProvider:
    name = "claude"

    def __init__(self, model: str | None = None, api_key: str | None = None, effort: str = "medium"):
        try:
            import anthropic
        except ImportError as e:  # pragma: no cover
            raise ProviderError("Install the Anthropic SDK: pip install anthropic") from e
        self._anthropic = anthropic
        self.model = model or os.getenv("CLAUDE_MODEL", DEFAULT_CLAUDE_MODEL)
        self.effort = effort
        # With no explicit key the SDK resolves ANTHROPIC_API_KEY / `ant auth login` profiles itself.
        self.client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

    def generate_json(self, system: str, user: str, schema: dict, schema_name: str) -> dict:
        a = self._anthropic
        try:
            response = self.client.beta.messages.create(
                model=self.model,
                max_tokens=16000,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_config={
                    "effort": self.effort,
                    "format": {"type": "json_schema", "schema": schema},
                },
                # If a safety classifier declines the request, the API re-runs it on a
                # fallback model inside the same call instead of returning nothing.
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except a.AuthenticationError as e:
            raise ProviderError("Claude: invalid or missing API key (set ANTHROPIC_API_KEY).") from e
        except TypeError as e:  # raised by the SDK when no credential can be resolved
            if "authentication" in str(e).lower():
                raise ProviderError(
                    "Claude: no API key found. Set ANTHROPIC_API_KEY in .env or enter it in the sidebar."
                ) from e
            raise
        except a.NotFoundError as e:
            raise ProviderError(f"Claude: model '{self.model}' not found.") from e
        except a.RateLimitError as e:
            raise ProviderError("Claude: rate limited - wait a moment and retry.") from e
        except a.BadRequestError as e:
            raise ProviderError(f"Claude rejected the request: {e.message}") from e
        except a.APIStatusError as e:
            raise ProviderError(f"Claude API error {e.status_code}: {e.message}") from e
        except a.APIConnectionError as e:
            raise ProviderError("Claude: could not reach the API (network error).") from e

        if response.stop_reason == "refusal":
            raise ProviderError("Claude declined this request. Try rephrasing the topic.")
        if response.stop_reason == "max_tokens":
            raise ProviderError("Claude ran out of output tokens; request fewer slides.")
        text = next((b.text for b in response.content if b.type == "text"), None)
        if not text:
            raise ProviderError("Claude returned no text content.")
        return _loads(text, "Claude")


# ---------------------------------------------------------------------------
# OpenAI GPT
# ---------------------------------------------------------------------------

class OpenAIProvider:
    name = "openai"

    def __init__(self, model: str | None = None, api_key: str | None = None):
        try:
            import openai
        except ImportError as e:  # pragma: no cover
            raise ProviderError("Install the OpenAI SDK: pip install openai") from e
        self._openai = openai
        self.model = model or os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)
        try:
            self.client = openai.OpenAI(api_key=api_key) if api_key else openai.OpenAI()
        except openai.OpenAIError as e:  # raised at construction when OPENAI_API_KEY is unset
            raise ProviderError(
                "OpenAI: no API key found. Set OPENAI_API_KEY in .env or enter it in the sidebar."
            ) from e

    def generate_json(self, system: str, user: str, schema: dict, schema_name: str) -> dict:
        o = self._openai
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": schema_name, "schema": schema, "strict": True},
                },
            )
        except o.AuthenticationError as e:
            raise ProviderError("OpenAI: invalid or missing API key (set OPENAI_API_KEY).") from e
        except o.NotFoundError as e:
            raise ProviderError(f"OpenAI: model '{self.model}' not found.") from e
        except o.RateLimitError as e:
            raise ProviderError("OpenAI: rate limited or out of quota.") from e
        except o.BadRequestError as e:
            raise ProviderError(f"OpenAI rejected the request: {e.message}") from e
        except o.APIStatusError as e:
            raise ProviderError(f"OpenAI API error {e.status_code}: {e.message}") from e
        except o.APIConnectionError as e:
            raise ProviderError("OpenAI: could not reach the API (network error).") from e

        choice = response.choices[0]
        if getattr(choice.message, "refusal", None):
            raise ProviderError(f"OpenAI declined: {choice.message.refusal}")
        if choice.finish_reason == "length":
            raise ProviderError("OpenAI ran out of output tokens; request fewer slides.")
        return _loads(choice.message.content or "", "OpenAI")


# ---------------------------------------------------------------------------
# Offline demo provider
# ---------------------------------------------------------------------------

class DemoProvider:
    """Deterministic, offline stand-in for an LLM.

    It produces a structurally complete deck (every layout type, a chart, notes) for any
    topic so the full pipeline and UI can be demonstrated without an API key. The text is
    generic and the chart data is clearly labelled as illustrative.
    """

    name = "demo"
    model = "offline-template"

    def generate_json(self, system: str, user: str, schema: dict, schema_name: str) -> dict:
        from .demo_content import demo_deck, demo_outline, parse_demo_request

        topic, n, charts = parse_demo_request(user)
        if schema_name == "deck_outline":
            return demo_outline(topic, n, charts)
        return demo_deck(topic, n, charts)


def _loads(text: str, who: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise ProviderError(f"{who} returned malformed JSON: {e}") from e


def get_provider(name: str, model: str | None = None, api_key: str | None = None) -> LLMProvider:
    name = name.lower().strip()
    if name in ("claude", "anthropic"):
        return ClaudeProvider(model=model or None, api_key=api_key or None)
    if name in ("openai", "gpt"):
        return OpenAIProvider(model=model or None, api_key=api_key or None)
    if name in ("demo", "offline"):
        return DemoProvider()
    raise ProviderError(f"Unknown provider '{name}'. Use claude, openai or demo.")
