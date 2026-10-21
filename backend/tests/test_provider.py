import asyncio
import json

import httpx
import pytest

from backend.app.config import Settings
from backend.app.providers.anthropic import AnthropicProvider
from backend.app.providers.base import (
    InvalidProviderResponse,
    MissingCredentials,
    ProviderRateLimited,
    ProviderTimeout,
    ProviderUnavailable,
)
from backend.app.providers.factory import create_provider
from backend.app.providers.gemini import GeminiProvider


def settings() -> Settings:
    return Settings(
        gemini_api_key="test-secret",
        anthropic_api_key="test-secret",
        provider_timeout_seconds=1,
    )


def test_provider_factory_selects_configured_provider() -> None:
    assert isinstance(create_provider(Settings(ai_provider="gemini")), GeminiProvider)
    assert isinstance(create_provider(Settings(ai_provider="anthropic")), AnthropicProvider)


def test_anthropic_provider_extracts_structured_json() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={"content": [{"type": "text", "text": '{"ok":true}'}]},
        )
    )
    result = asyncio.run(AnthropicProvider(settings(), transport).generate_json("return json"))
    assert result == {"ok": True}


def test_anthropic_provider_maps_rate_limit_and_timeout() -> None:
    rate_limit_transport = httpx.MockTransport(lambda request: httpx.Response(429))
    with pytest.raises(ProviderRateLimited):
        asyncio.run(AnthropicProvider(settings(), rate_limit_transport).generate_json("prompt"))

    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("provider timed out", request=request)

    timeout_transport = httpx.MockTransport(timeout)
    with pytest.raises(ProviderTimeout):
        asyncio.run(AnthropicProvider(settings(), timeout_transport).generate_json("prompt"))


def test_anthropic_provider_rejects_malformed_output_and_missing_key() -> None:
    malformed_transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"content": [{"type": "text", "text": "not json"}]})
    )
    with pytest.raises(InvalidProviderResponse):
        asyncio.run(AnthropicProvider(settings(), malformed_transport).generate_json("prompt"))

    with pytest.raises(MissingCredentials):
        asyncio.run(AnthropicProvider(Settings(anthropic_api_key="")).generate_json("prompt"))


def test_gemini_provider_sends_json_request_and_extracts_response() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/v1beta/interactions")
        assert request.headers["x-goog-api-key"] == "test-secret"
        payload = json.loads(request.content)
        assert payload["model"] == "gemini-3.8-flash"
        assert payload["response_format"]["mime_type"] == "application/json"
        assert payload["generation_config"] == {
            "max_output_tokens": 1000,
            "thinking_level": "low",
        }
        return httpx.Response(
            200,
            json={
                "steps": [
                    {
                        "type": "model_output",
                        "content": [{"type": "text", "text": '{"ok":true}'}],
                    }
                ]
            },
        )

    result = asyncio.run(GeminiProvider(settings(), httpx.MockTransport(respond)).generate_json("return json"))
    assert result == {"ok": True}


def test_gemini_provider_maps_rate_limit_timeout_and_invalid_output() -> None:
    rate_limit_transport = httpx.MockTransport(lambda request: httpx.Response(429))
    with pytest.raises(ProviderRateLimited):
        asyncio.run(GeminiProvider(settings(), rate_limit_transport).generate_json("prompt"))

    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("provider timed out", request=request)

    timeout_transport = httpx.MockTransport(timeout)
    with pytest.raises(ProviderTimeout):
        asyncio.run(GeminiProvider(settings(), timeout_transport).generate_json("prompt"))

    malformed_transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "steps": [
                    {"type": "model_output", "content": [{"type": "text", "text": "not json"}]}
                ]
            },
        )
    )
    with pytest.raises(InvalidProviderResponse):
        asyncio.run(GeminiProvider(settings(), malformed_transport).generate_json("prompt"))

    with pytest.raises(MissingCredentials):
        asyncio.run(GeminiProvider(Settings(gemini_api_key="")).generate_json("prompt"))


def test_gemini_provider_retries_service_unavailable_once() -> None:
    attempts = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(503)
        return httpx.Response(
            200,
            json={
                "steps": [
                    {"type": "model_output", "content": [{"type": "text", "text": '{"ok":true}'}]}
                ]
            },
        )

    result = asyncio.run(
        GeminiProvider(settings(), httpx.MockTransport(respond)).generate_json("prompt")
    )
    assert result == {"ok": True}
    assert attempts == 2

    attempts = 0

    def stay_unavailable(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503)

    unavailable_transport = httpx.MockTransport(stay_unavailable)
    with pytest.raises(ProviderUnavailable):
        asyncio.run(
            GeminiProvider(settings(), unavailable_transport).generate_json("prompt")
        )
    assert attempts == 2
