import asyncio
import json
import logging
from time import perf_counter

import httpx

from backend.app.config import Settings
from backend.app.providers.base import (
    AIProvider,
    InvalidProviderResponse,
    MissingCredentials,
    ProviderRateLimited,
    ProviderTimeout,
    ProviderUnavailable,
)


logger = logging.getLogger(__name__)
performance_logger = logging.getLogger("uvicorn.error")


class GeminiProvider(AIProvider):
    endpoint = "https://generativelanguage.googleapis.com/v1beta/interactions"

    def __init__(
        self,
        settings: Settings,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport

    async def generate_json(self, prompt: str) -> dict[str, object]:
        if not self._settings.gemini_api_key:
            raise MissingCredentials

        headers = {
            "content-type": "application/json",
            "x-goog-api-key": self._settings.gemini_api_key,
        }
        payload = {
            "model": self._settings.gemini_model,
            "input": prompt,
            "response_format": {
                "type": "text",
                "mime_type": "application/json",
            },
            "generation_config": {
                "max_output_tokens": 1000,
                "thinking_level": "low",
            },
        }
        started_at = perf_counter()
        deadline = started_at + self._settings.provider_timeout_seconds
        attempt = 0
        while True:
            remaining = deadline - perf_counter()
            if remaining <= 0:
                raise ProviderTimeout
            try:
                async with asyncio.timeout(remaining):
                    async with httpx.AsyncClient(
                        timeout=remaining,
                        transport=self._transport,
                    ) as client:
                        response = await client.post(self.endpoint, headers=headers, json=payload)
            except (TimeoutError, httpx.TimeoutException) as exc:
                performance_logger.warning(
                    "Gemini request timed out after %.2f seconds",
                    perf_counter() - started_at,
                )
                raise ProviderTimeout from exc
            except httpx.HTTPError as exc:
                performance_logger.warning(
                    "Gemini request failed after %.2f seconds",
                    perf_counter() - started_at,
                )
                raise ProviderUnavailable from exc

            if response.status_code != 503 or attempt >= 1:
                break

            remaining = deadline - perf_counter()
            if remaining <= 0.5:
                break
            performance_logger.warning("Gemini returned 503; retrying once")
            await asyncio.sleep(min(0.5, remaining))
            attempt += 1

        performance_logger.info(
            "Gemini request completed in %.2f seconds with status %s",
            perf_counter() - started_at,
            response.status_code,
        )
        if response.status_code == 429:
            raise ProviderRateLimited
        if response.status_code >= 500:
            logger.warning("AI provider returned server status %s", response.status_code)
            raise ProviderUnavailable
        if response.is_error:
            logger.warning("AI provider rejected request with status %s", response.status_code)
            raise ProviderUnavailable

        try:
            body = response.json()
            steps = body["steps"]
            text = "".join(
                content["text"]
                for step in steps
                if step.get("type") == "model_output"
                for content in step.get("content", [])
                if content.get("type") == "text" and isinstance(content.get("text"), str)
            )
            result = json.loads(text)
        except (ValueError, TypeError, KeyError, IndexError, AttributeError) as exc:
            raise InvalidProviderResponse from exc
        if not isinstance(result, dict):
            raise InvalidProviderResponse
        return result
