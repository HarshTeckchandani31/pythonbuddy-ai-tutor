from dataclasses import dataclass
import os

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    ai_provider: str = os.getenv("AI_PROVIDER", "gemini").strip().lower()
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "").strip()
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip()
    supabase_url: str = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    supabase_publishable_key: str = os.getenv("SUPABASE_PUBLISHABLE_KEY", "").strip()
    supabase_service_role_key: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    admin_email: str = os.getenv("ADMIN_EMAIL", "").strip().casefold()
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "").strip()
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001").strip()
    provider_timeout_seconds: float = float(os.getenv("AI_TIMEOUT_SECONDS", "20"))
    max_request_bytes: int = int(os.getenv("MAX_REQUEST_BYTES", "65536"))
    cors_origins: tuple[str, ...] = tuple(
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
        if origin.strip()
    )

    def __post_init__(self) -> None:
        if not 0 < self.provider_timeout_seconds <= 120:
            raise ValueError("AI_TIMEOUT_SECONDS must be between 0 and 120")
        if not 0 < self.max_request_bytes <= 1_048_576:
            raise ValueError("MAX_REQUEST_BYTES must be between 1 and 1048576")
