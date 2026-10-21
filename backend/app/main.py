import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.responses import Response

from backend.app.config import Settings
from backend.app.providers.base import (
    AIProvider,
    InvalidProviderResponse,
    MissingCredentials,
    ProviderRateLimited,
    ProviderTimeout,
    ProviderUnavailable,
)
from backend.app.providers.factory import create_provider
from backend.app.routes import router
from backend.app.sessions import SessionNotFound, SessionStore
from backend.app.services import TutorService
from backend.app.storage import SessionRepository, SupabaseSessionRepository, SupabaseUnavailable


logger = logging.getLogger("pythonbuddy")
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
FRONTEND_INDEX = FRONTEND_DIST / "index.html"
FRONTEND_ASSET_SUFFIXES = {
    ".css",
    ".gif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".js",
    ".json",
    ".map",
    ".png",
    ".svg",
    ".txt",
    ".webp",
    ".woff",
    ".woff2",
}


def create_app(
    settings: Settings | None = None,
    provider: AIProvider | None = None,
    sessions: SessionStore | None = None,
    session_repository: SessionRepository | None = None,
) -> FastAPI:
    config = settings or Settings()
    active_provider = provider or create_provider(config)
    active_sessions = sessions or SessionStore()
    repository = session_repository or SupabaseSessionRepository(config)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        await repository.close()

    app = FastAPI(
        title="PythonBuddy Tutor API",
        version="1.0.0",
        description="Personalized Python lessons, practice, quizzes, and progress summaries.",
        lifespan=lifespan,
    )
    app.state.settings = config
    app.state.tutor_service = TutorService(active_provider, active_sessions)
    app.state.session_repository = repository
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(config.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.middleware("http")
    async def limit_request_size(request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                too_large = int(content_length) > config.max_request_bytes
            except ValueError:
                return JSONResponse(status_code=400, content={"detail": "Invalid Content-Length"})
            if too_large:
                return JSONResponse(status_code=413, content={"detail": "Request body is too large"})
        return await call_next(request)

    @app.exception_handler(SessionNotFound)
    async def session_not_found(_: Request, __: SessionNotFound) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": "Learning session not found"})

    @app.exception_handler(SupabaseUnavailable)
    async def supabase_unavailable(_: Request, exc: SupabaseUnavailable) -> JSONResponse:
        logger.warning("Supabase request failed: %s", exc)
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.exception_handler(MissingCredentials)
    async def missing_credentials(_: Request, exc: MissingCredentials) -> JSONResponse:
        logger.warning("AI provider is not configured")
        return JSONResponse(status_code=503, content={"detail": "AI provider credentials are not configured"})

    @app.exception_handler(ProviderRateLimited)
    async def provider_rate_limited(_: Request, exc: ProviderRateLimited) -> JSONResponse:
        logger.warning("AI provider rate limit reached")
        return JSONResponse(status_code=429, content={"detail": "AI provider rate limit reached; try again shortly"})

    @app.exception_handler(ProviderTimeout)
    async def provider_timeout(_: Request, exc: ProviderTimeout) -> JSONResponse:
        logger.warning("AI provider request timed out")
        return JSONResponse(status_code=504, content={"detail": "AI provider timed out; try again"})

    @app.exception_handler(InvalidProviderResponse)
    async def invalid_provider_response(_: Request, exc: InvalidProviderResponse) -> JSONResponse:
        logger.warning("AI provider returned invalid structured content")
        return JSONResponse(status_code=502, content={"detail": "AI provider returned an invalid response"})

    @app.exception_handler(ProviderUnavailable)
    async def provider_unavailable(_: Request, exc: ProviderUnavailable) -> JSONResponse:
        logger.warning("AI provider is unavailable")
        return JSONResponse(status_code=502, content={"detail": "AI provider is unavailable"})

    app.include_router(router)

    if FRONTEND_INDEX.is_file():
        app.frontend("/", directory=str(FRONTEND_DIST), fallback="index.html")
    else:
        @app.get("/", include_in_schema=False)
        async def frontend_index() -> Response:
            return JSONResponse(
                status_code=503,
                content={"detail": "Frontend build missing. Run npm run build:frontend from the workspace root."},
            )

        @app.get("/{frontend_path:path}", include_in_schema=False)
        async def frontend_assets(frontend_path: str) -> Response:
            return JSONResponse(
                status_code=404 if Path(frontend_path).suffix.lower() in FRONTEND_ASSET_SUFFIXES else 503,
                content={
                    "detail": "Not found"
                    if Path(frontend_path).suffix.lower() in FRONTEND_ASSET_SUFFIXES
                    else "Frontend build missing. Run npm run build:frontend from the workspace root."
                },
            )

    return app


app = create_app()
