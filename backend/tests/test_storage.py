import asyncio
import json
from uuid import uuid4

import httpx
import pytest

from backend.app.config import Settings
from backend.app.schemas import LearnerProfile, QuestionDraft
from backend.app.sessions import Attempt, LearningSession, QuizItem
from backend.app.storage import (
    AuthenticatedUser,
    InvalidAccessToken,
    SupabaseUnavailable,
    SupabaseSessionRepository,
)


def sample_profile() -> LearnerProfile:
    return LearnerProfile(
        name="Riya",
        level="beginner",
        difficulty="beginner",
        topic="Python variables",
    )


def sample_question() -> QuestionDraft:
    return QuestionDraft(
        question="What does count store?",
        expected_answer="3",
        accepted_answers=["3"],
        explanation="count is assigned 3.",
        hint="Read the right side of the assignment.",
        skill="python variables",
    )


def test_session_storage_serialization_round_trips_quiz_and_progress() -> None:
    session_id = str(uuid4())
    question = sample_question()
    session = LearningSession(
        session_id=session_id,
        profile=sample_profile(),
        attempts=[Attempt(skill="python variables", correct=True)],
        practice_questions={"practice-1": question},
        answered_practice_ids={"practice-1"},
        quiz=[QuizItem("quiz-1", question, answered=True, correct=False)],
        quiz_cursor=1,
    )
    row = SupabaseSessionRepository._session_data(str(uuid4()), session)
    restored = SupabaseSessionRepository._session_from_row(row)

    assert restored.session_id == session_id
    assert restored.profile == session.profile
    assert restored.attempts == session.attempts
    assert restored.practice_questions == session.practice_questions
    assert restored.answered_practice_ids == session.answered_practice_ids
    assert restored.quiz == session.quiz
    assert restored.quiz_cursor == session.quiz_cursor


def test_supabase_session_read_is_scoped_to_owner_and_keeps_key_server_side() -> None:
    user_id = str(uuid4())
    session_id = str(uuid4())
    expected = {
        "id": session_id,
        "user_id": user_id,
        "profile": sample_profile().model_dump(mode="json"),
        "attempts": [],
        "practice_questions": {},
        "answered_practice_ids": [],
        "quiz": [],
        "quiz_cursor": 0,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/rest/v1/learning_sessions")
        assert dict(request.url.params)["id"] == f"eq.{session_id}"
        assert dict(request.url.params)["user_id"] == f"eq.{user_id}"
        assert request.headers["apikey"] == "server-only-test-key"
        assert request.headers["authorization"] == "Bearer server-only-test-key"
        return httpx.Response(200, json=[expected])

    repository = SupabaseSessionRepository(
        Settings(
            supabase_url="https://example.supabase.co",
            supabase_service_role_key="server-only-test-key",
        ),
        transport=httpx.MockTransport(respond),
    )

    async def read_and_close() -> LearningSession:
        try:
            return await repository.get_session(user_id, session_id)
        finally:
            await repository.close()

    restored = asyncio.run(read_and_close())
    assert restored.session_id == session_id
    assert restored.profile == sample_profile()


def test_supabase_create_and_update_persist_account_profile_and_session_state() -> None:
    user_id = str(uuid4())
    stored_rows: dict[str, dict[str, object]] = {}
    profile_rows: list[dict[str, object]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        table = request.url.path.rsplit("/", 1)[-1]
        if request.method == "POST" and table == "learner_profiles":
            profile_rows.append(json.loads(request.content))
            return httpx.Response(201)
        if request.method == "POST" and table == "learning_sessions":
            row = json.loads(request.content)
            row["created_at"] = "2026-01-01T00:00:00Z"
            stored_rows[row["id"]] = row
            return httpx.Response(201)
        if request.method == "PATCH" and table == "learning_sessions":
            query = dict(request.url.params)
            row = stored_rows[query["id"].removeprefix("eq.")]
            row.update(json.loads(request.content))
            return httpx.Response(200, json=[row])
        raise AssertionError(f"Unexpected Supabase request: {request.method} {request.url}")

    repository = SupabaseSessionRepository(
        Settings(
            supabase_url="https://example.supabase.co",
            supabase_service_role_key="server-only-test-key",
        ),
        transport=httpx.MockTransport(respond),
    )

    async def create_update_and_close() -> LearningSession:
        try:
            user = AuthenticatedUser(user_id, "riya@example.com", "Riya")
            session = await repository.create_session(user, sample_profile())
            session.attempts.append(Attempt(skill="python variables", correct=True))
            await repository.save_session(user_id, session)
            return session
        finally:
            await repository.close()

    session = asyncio.run(create_update_and_close())
    assert profile_rows[0]["user_id"] == user_id
    assert profile_rows[0]["email"] == "riya@example.com"
    assert profile_rows[0]["full_name"] == "Riya"
    assert stored_rows[session.session_id]["attempts"] == [
        {"skill": "python variables", "correct": True}
    ]


def test_supabase_auth_validates_access_token_and_extracts_verified_identity() -> None:
    user_id = str(uuid4())

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/auth/v1/user")
        assert request.headers["apikey"] == "public-test-key"
        assert request.headers["authorization"] == "Bearer valid-access-token"
        return httpx.Response(
            200,
            json={
                "id": user_id,
                "email": "riya@example.com",
                "user_metadata": {"full_name": "Riya"},
            },
        )

    repository = SupabaseSessionRepository(
        Settings(
            supabase_url="https://example.supabase.co",
            supabase_publishable_key="public-test-key",
        ),
        transport=httpx.MockTransport(respond),
    )

    async def authenticate_and_close() -> AuthenticatedUser:
        try:
            return await repository.authenticate("valid-access-token")
        finally:
            await repository.close()

    user = asyncio.run(authenticate_and_close())
    assert user == AuthenticatedUser(user_id, "riya@example.com", "Riya")


def test_supabase_auth_rejects_invalid_access_token() -> None:
    repository = SupabaseSessionRepository(
        Settings(
            supabase_url="https://example.supabase.co",
            supabase_publishable_key="public-test-key",
        ),
        transport=httpx.MockTransport(lambda request: httpx.Response(401)),
    )

    async def authenticate_and_close() -> None:
        try:
            await repository.authenticate("invalid-access-token")
        finally:
            await repository.close()

    with pytest.raises(InvalidAccessToken):
        asyncio.run(authenticate_and_close())


def test_supabase_repository_rejects_unedited_example_values() -> None:
    repository = SupabaseSessionRepository(
        Settings(
            supabase_url="https://your-project-id.supabase.co",
            supabase_publishable_key="your-supabase-publishable-key",
            supabase_service_role_key="your-server-only-service-role-key",
        )
    )

    async def authenticate() -> None:
        await repository.authenticate("not-a-real-token")

    with pytest.raises(SupabaseUnavailable, match="not configured"):
        asyncio.run(authenticate())
