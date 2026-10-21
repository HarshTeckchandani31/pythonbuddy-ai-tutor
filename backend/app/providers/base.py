from typing import Protocol


class ProviderError(Exception):
    """Base class for errors returned by a configured AI provider."""


class MissingCredentials(ProviderError):
    pass


class ProviderRateLimited(ProviderError):
    pass


class ProviderTimeout(ProviderError):
    pass


class ProviderUnavailable(ProviderError):
    pass


class InvalidProviderResponse(ProviderError):
    pass


class AIProvider(Protocol):
    async def generate_json(self, prompt: str) -> dict[str, object]: ...
