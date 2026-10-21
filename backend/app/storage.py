from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from typing import Protocol
from uuid import UUID, uuid4

import httpx
from pydantic import ValidationError

from backend.app.config import Settings
from backend.app.schemas import LearnerProfile, QuestionDraft
from backend.app.sessions import Attempt, LearningSession, QuizItem, SessionNotFound


logger = logging.getLogger(__name__)
SESSION_COLUMNS = (
    "id,user_id,profile,attempts,practice_questions,answered_practice_ids,"
    "quiz,quiz_cursor,created_at,updated_at"
)


@dataclass(frozen=True)
class AuthenticatedUser:
    user_id: str
    email: str
    full_name: str


class InvalidAccessToken(Exception):
    pass


class SupabaseUnavailable(Exception):
    pass


class SessionRepository(Protocol):
    async def authenticate(self, access_token: str) -> AuthenticatedUser: ...

    async def create_session(
        self,
        user: AuthenticatedUser,
        profile: LearnerProfile,
    ) -> LearningSession: ...

    async def get_session(self, user_id: str, session_id: str) -> LearningSession: ...

    async def get_latest_session(self, user_id: str) -> LearningSession | None: ...

    async def save_session(self, user_id: str, session: LearningSession) -> None: ...

    async def close(self) -> None: ...


class SupabaseSessionRepository:
    def __init__(
        self,
        settings: Settings,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport
        self._client: httpx.AsyncClient | None = None

    @staticmethod
    def _is_configured(value: str) -> bool:
        return bool(value) and not any(
            placeholder in value.lower()
            for placeholder in ("your-project-id", "your-supabase", "replace-with", "placeholder")
        )

    async def _http_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=10, transport=self._transport)
        return self._client

    def _require_auth_config(self) -> None:
        if not self._is_configured(self._settings.supabase_url) or not self._is_configured(
            self._settings.supabase_publishable_key
        ):
            raise SupabaseUnavailable("Supabase Auth is not configured")

    def _require_database_config(self) -> None:
        if not self._is_configured(self._settings.supabase_url) or not self._is_configured(
            self._settings.supabase_service_role_key
        ):
            raise SupabaseUnavailable("Supabase database access is not configured")

    async def authenticate(self, access_token: str) -> AuthenticatedUser:
        self._require_auth_config()
        client = await self._http_client()
        try:
            response = await client.get(
                f"{self._settings.supabase_url}/auth/v1/user",
                headers={
                    "apikey": self._settings.supabase_publishable_key,
                    "authorization": f"Bearer {access_token}",
                },
            )
        except httpx.HTTPError as exc:
            logger.warning("Supabase Auth request failed")
            raise SupabaseUnavailable from exc

        if response.status_code in (401, 403):
            raise InvalidAccessToken
        if response.is_error:
            logger.warning("Supabase Auth returned status %s", response.status_code)
            raise SupabaseUnavailable
        try:
            body = response.json()
            user_id = str(UUID(body["id"]))
            email = body["email"]
            metadata = body.get("user_metadata") or {}
            full_name = metadata.get("full_name", "")
            if not isinstance(email, str) or not isinstance(full_name, str):
                raise ValueError("Invalid Supabase user data")
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            raise SupabaseUnavailable("Supabase Auth returned an invalid user") from exc
        return AuthenticatedUser(user_id=user_id, email=email, full_name=full_name)

    def _database_headers(self) -> dict[str, str]:
        self._require_database_config()
        return {
            "apikey": self._settings.supabase_service_role_key,
            "authorization": f"Bearer {self._settings.supabase_service_role_key}",
            "content-type": "application/json",
        }

    async def _database_request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        json_body: dict[str, object] | None = None,
        prefer: str | None = None,
    ) -> httpx.Response:
        client = await self._http_client()
        headers = self._database_headers()
        if prefer:
            headers["prefer"] = prefer
        try:
            response = await client.request(
                method,
                f"{self._settings.supabase_url}/rest/v1/{path}",
                params=params,
                headers=headers,
                json=json_body,
            )
        except httpx.HTTPError as exc:
            logger.warning("Supabase database request failed")
            raise SupabaseUnavailable from exc
        if response.is_error:
            logger.warning("Supabase database returned status %s", response.status_code)
            raise SupabaseUnavailable("Supabase database request failed")
        return response

    @staticmethod
    def _response_rows(response: httpx.Response) -> list[object]:
        try:
            rows = response.json()
        except ValueError as exc:
            raise SupabaseUnavailable("Supabase database returned invalid JSON") from exc
        if not isinstance(rows, list):
            raise SupabaseUnavailable("Supabase database returned an invalid row list")
        return rows

    async def create_session(
        self,
        user: AuthenticatedUser,
        profile: LearnerProfile,
    ) -> LearningSession:
        self._require_database_config()
        session = LearningSession(session_id=str(uuid4()), profile=profile)
        profile_data = {
            "user_id": user.user_id,
            "email": user.email,
            "full_name": profile.name or user.full_name,
            "level": profile.level.value,
            "difficulty": profile.difficulty.value,
            "topic": profile.topic,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        await self._database_request(
            "POST",
            "learner_profiles",
            params={"on_conflict": "user_id"},
            json_body=profile_data,
            prefer="resolution=merge-duplicates,return=minimal",
        )
        await self._database_request(
            "POST",
            "learning_sessions",
            json_body=self._session_data(user.user_id, session),
            prefer="return=minimal",
        )
        return session

    @staticmethod
    def _session_data(user_id: str, session: LearningSession) -> dict[str, object]:
        return {
            "id": session.session_id,
            "user_id": user_id,
            "profile": session.profile.model_dump(mode="json"),
            "attempts": [
                {"skill": attempt.skill, "correct": attempt.correct}
                for attempt in session.attempts
            ],
            "practice_questions": {
                question_id: draft.model_dump(mode="json")
                for question_id, draft in session.practice_questions.items()
            },
            "answered_practice_ids": sorted(session.answered_practice_ids),
            "quiz": [
                {
                    "question_id": item.question_id,
                    "draft": item.draft.model_dump(mode="json"),
                    "answered": item.answered,
                    "correct": item.correct,
                }
                for item in session.quiz
            ],
            "quiz_cursor": session.quiz_cursor,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def _session_from_row(row: object) -> LearningSession:
        if not isinstance(row, dict):
            raise SupabaseUnavailable("Supabase returned an invalid session row")
        try:
            return LearningSession(
                session_id=str(UUID(str(row["id"]))),
                profile=LearnerProfile.model_validate(row["profile"]),
                attempts=[
                    Attempt(skill=item["skill"], correct=item["correct"])
                    for item in row["attempts"]
                ],
                practice_questions={
                    question_id: QuestionDraft.model_validate(draft)
                    for question_id, draft in row["practice_questions"].items()
                },
                answered_practice_ids=set(row["answered_practice_ids"]),
                quiz=[
                    QuizItem(
                        question_id=item["question_id"],
                        draft=QuestionDraft.model_validate(item["draft"]),
                        answered=item["answered"],
                        correct=item["correct"],
                    )
                    for item in row["quiz"]
                ],
                quiz_cursor=row["quiz_cursor"],
            )
        except (ValidationError, ValueError, TypeError, KeyError, AttributeError) as exc:
            raise SupabaseUnavailable("Stored learning session is invalid") from exc

    async def get_session(self, user_id: str, session_id: str) -> LearningSession:
        try:
            normalized_id = str(UUID(session_id))
            normalized_user_id = str(UUID(user_id))
        except ValueError as exc:
            raise SessionNotFound from exc
        response = await self._database_request(
            "GET",
            "learning_sessions",
            params={
                "select": SESSION_COLUMNS,
                "id": f"eq.{normalized_id}",
                "user_id": f"eq.{normalized_user_id}",
                "limit": "1",
            },
        )
        rows = self._response_rows(response)
        if not rows:
            raise SessionNotFound
        return self._session_from_row(rows[0])

    async def get_latest_session(self, user_id: str) -> LearningSession | None:
        normalized_user_id = str(UUID(user_id))
        response = await self._database_request(
            "GET",
            "learning_sessions",
            params={
                "select": SESSION_COLUMNS,
                "user_id": f"eq.{normalized_user_id}",
                "order": "created_at.desc",
                "limit": "1",
            },
        )
        rows = self._response_rows(response)
        return self._session_from_row(rows[0]) if rows else None

    async def save_session(self, user_id: str, session: LearningSession) -> None:
        response = await self._database_request(
            "PATCH",
            "learning_sessions",
            params={
                "id": f"eq.{session.session_id}",
                "user_id": f"eq.{user_id}",
            },
            json_body=self._session_data(user_id, session),
            prefer="return=representation",
        )
        rows = self._response_rows(response)
        if not rows:
            raise SessionNotFound

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


class InMemorySessionRepository:
    def __init__(self) -> None:
        self._sessions: dict[str, tuple[str, LearningSession]] = {}

    async def authenticate(self, access_token: str) -> AuthenticatedUser:
        raise NotImplementedError

    async def create_session(
        self,
        user: AuthenticatedUser,
        profile: LearnerProfile,
    ) -> LearningSession:
        session = LearningSession(session_id=str(uuid4()), profile=profile)
        self._sessions[session.session_id] = (user.user_id, session)
        return session

    async def get_session(self, user_id: str, session_id: str) -> LearningSession:
        record = self._sessions.get(session_id)
        if record is None or record[0] != user_id:
            raise SessionNotFound
        return record[1]

    async def get_latest_session(self, user_id: str) -> LearningSession | None:
        return next(
            (session for owner_id, session in reversed(list(self._sessions.values())) if owner_id == user_id),
            None,
        )

    async def save_session(self, user_id: str, session: LearningSession) -> None:
        record = self._sessions.get(session.session_id)
        if record is None or record[0] != user_id:
            raise SessionNotFound

    async def close(self) -> None:
        return None
