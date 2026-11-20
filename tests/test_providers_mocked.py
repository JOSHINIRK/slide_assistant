"""Exercise the real Claude / OpenAI adapters against a mocked HTTP transport.

No network and no API key: verifies that requests serialize correctly through the official
SDKs and that responses (including refusals) are parsed as expected.
"""

import json

import httpx
import httpx2
import pytest

from slide_assistant.demo_content import demo_deck
from slide_assistant.llm import ClaudeProvider, OpenAIProvider, ProviderError
from slide_assistant.pipeline import generate_deck

DECK = demo_deck("EV trends", 5)


def _claude(handler):
    import anthropic

    p = ClaudeProvider(api_key="test-key")
    # anthropic 2.x is built on httpx2
    p.client = anthropic.Anthropic(api_key="test-key", max_retries=0,
                                   http_client=httpx2.Client(transport=httpx2.MockTransport(handler)))
    return p


def _openai(handler):
    import openai

    p = OpenAIProvider(api_key="test-key")
    p.client = openai.OpenAI(api_key="test-key", max_retries=0,
                             http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    return p


def _claude_message(text, stop_reason="end_turn"):
    return {
        "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
        "content": [{"type": "text", "text": text}], "stop_reason": stop_reason,
        "stop_sequence": None, "usage": {"input_tokens": 10, "output_tokens": 10},
    }


def test_claude_request_and_parse():
    seen = []

    def handler(request: httpx2.Request):
        body = json.loads(request.content)
        seen.append((request, body))
        assert request.url.path == "/v1/messages"
        assert body["model"] == "claude-opus-5-5"
        assert body["output_config"]["format"]["type"] == "json_schema"
        assert body["fallbacks"] == "default"
        assert "server-side-fallback-2026-07-01" in request.headers["anthropic-beta"]
        if "outline" in json.dumps(body["output_config"]["format"]["schema"]["properties"]).lower() or \
                "storyline" in body["output_config"]["format"]["schema"]["properties"]:
            out = {"title": "EV", "subtitle": "", "storyline": "s",
                   "slides": [{"title": s["title"], "layout": s["layout"], "purpose": "p"} for s in DECK["slides"]]}
        else:
            out = DECK
        return httpx2.Response(200, json=_claude_message(json.dumps(out)))

    deck, log = generate_deck("Make a 5-slide deck on EV trends", _claude(handler))
    assert len(seen) == 2  # outline + content
    assert len(deck.slides) == 5 and log.outline is not None


def test_claude_refusal():
    handler = lambda r: httpx2.Response(200, json=_claude_message("", stop_reason="refusal"))
    with pytest.raises(ProviderError, match="declined"):
        _claude(handler).generate_json("s", "u", {"type": "object"}, "x")


def test_claude_auth_error():
    handler = lambda r: httpx2.Response(401, json={"type": "error", "error": {
        "type": "authentication_error", "message": "invalid x-api-key"}})
    with pytest.raises(ProviderError, match="API key"):
        _claude(handler).generate_json("s", "u", {"type": "object"}, "x")


def test_openai_request_and_parse():
    def handler(request: httpx.Request):
        body = json.loads(request.content)
        assert request.url.path.endswith("/chat/completions")
        assert body["response_format"]["json_schema"]["strict"] is True
        return httpx.Response(200, json={
            "id": "c1", "object": "chat.completion", "created": 0, "model": body["model"],
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": json.dumps(DECK), "refusal": None}}],
        })

    deck, _ = generate_deck("Make a 5-slide deck on EV trends", _openai(handler), two_stage=False)
    assert len(deck.slides) == 5
