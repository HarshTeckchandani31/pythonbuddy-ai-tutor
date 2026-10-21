from backend.app.config import Settings
from backend.app.providers.anthropic import AnthropicProvider
from backend.app.providers.base import AIProvider
from backend.app.providers.gemini import GeminiProvider


def create_provider(settings: Settings) -> AIProvider:
    if settings.ai_provider == "gemini":
        return GeminiProvider(settings)
    if settings.ai_provider == "anthropic":
        return AnthropicProvider(settings)
    raise ValueError(f"Unsupported AI_PROVIDER: {settings.ai_provider}")
