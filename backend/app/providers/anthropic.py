import json
import logging

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


class AnthropicProvider(AIProvider):
    endpoint = "https://api.anthropic.com/v1/messages"

    def __init__(
        self,
        settings: Settings,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport

    async def generate_json(self, prompt: str) -> dict[str, object]:
        if not self._settings.anthropic_api_key:
            raise MissingCredentials

        headers = {
            "content-type": "application/json",
            "x-api-key": self._settings.anthropic_api_key,
            "anthropic-version": "2023-06-01",
        }
        payload = {
            "model": self._settings.anthropic_model,
            "max_tokens": 1600,
            "system": "Return valid JSON only. Do not include markdown fences or commentary.",
            "messages": [{"role": "user", "content": prompt}],
        }
        try:
            async with httpx.AsyncClient(
                timeout=self._settings.provider_timeout_seconds,
                transport=self._transport,
            ) as client:
                response = await client.post(self.endpoint, headers=headers, json=payload)
        except httpx.TimeoutException as exc:
            raise ProviderTimeout from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailable from exc

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
            text = "".join(
                block["text"]
                for block in body.get("content", [])
                if block.get("type") == "text" and isinstance(block.get("text"), str)
            )
            result = json.loads(text)
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            raise InvalidProviderResponse from exc
        if not isinstance(result, dict):
            raise InvalidProviderResponse
        return result
