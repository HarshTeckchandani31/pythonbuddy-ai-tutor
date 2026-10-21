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
    SuspendedAccount,
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
        assert request.headers["authorization"].startswith("Bearer ")
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


def test_supabase_feedback_storage_uses_authenticated_user_id() -> None:
    user_id = str(uuid4())
    inserted_rows: list[dict[str, object]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path.endswith("/rest/v1/learner_feedback")
        assert request.headers["apikey"] == "server-only-test-key"
        inserted_rows.append(json.loads(request.content))
        return httpx.Response(201)

    repository = SupabaseSessionRepository(
        Settings(
            supabase_url="https://example.supabase.co",
            supabase_service_role_key="server-only-test-key",
        ),
        transport=httpx.MockTransport(respond),
    )

    async def submit_and_close() -> None:
        try:
            await repository.submit_feedback(
                AuthenticatedUser(user_id, "riya@example.com", "Riya"),
                "A helpful lesson.",
            )
        finally:
            await repository.close()

    asyncio.run(submit_and_close())
    assert inserted_rows == [{"user_id": user_id, "feedback": "A helpful lesson."}]


def test_supabase_admin_uses_server_key_for_user_and_feedback_management() -> None:
    learner_user_id = str(uuid4())
    feedback_id = str(uuid4())
    calls: list[tuple[str, str, dict[str, object] | None]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.headers["apikey"] == "server-only-test-key"
        assert request.headers["authorization"].startswith("Bearer ")
        body = json.loads(request.content) if request.content else None
        calls.append((request.method, request.url.path, body))
        if request.method == "GET" and request.url.path.endswith("/auth/v1/admin/users"):
            assert dict(request.url.params) == {"page": "1", "per_page": "1"}
            return httpx.Response(
                200,
                json={
                    "users": [
                        {
                            "id": learner_user_id,
                            "email": "riya@example.com",
                            "user_metadata": {"full_name": "Riya"},
                            "created_at": "2026-01-01T00:00:00Z",
                            "last_sign_in_at": None,
                            "banned_until": None,
                        }
                    ]
                },
            )
        if request.method == "GET" and request.url.path.endswith("/rest/v1/learner_feedback"):
            assert dict(request.url.params)["is_featured"] == "eq.true"
            return httpx.Response(200, json=[{"feedback": "A helpful tutor."}])
        if request.method == "PATCH" and request.url.path.endswith("/rest/v1/learner_feedback"):
            return httpx.Response(200, json=[{"id": feedback_id}])
        if request.method == "POST" and request.url.path.endswith("/rest/v1/learner_account_status"):
            return httpx.Response(201)
        if request.url.path.endswith(f"/auth/v1/admin/users/{learner_user_id}"):
            return httpx.Response(204)
        raise AssertionError(f"Unexpected Supabase request: {request.method} {request.url}")

    repository = SupabaseSessionRepository(
        Settings(
            supabase_url="https://example.supabase.co",
            supabase_service_role_key="server-only-test-key",
        ),
        transport=httpx.MockTransport(respond),
    )

    async def exercise_admin_actions() -> tuple[list[object], bool, list[str]]:
        try:
            users, has_more = await repository.list_admin_users(1, 1)
            featured = await repository.get_featured_feedback()
            await repository.set_feedback_featured(feedback_id, True)
            await repository.set_user_suspended(learner_user_id, True)
            await repository.set_user_suspended(learner_user_id, False)
            await repository.delete_user(learner_user_id)
            return users, has_more, featured
        finally:
            await repository.close()

    users, has_more, featured = asyncio.run(exercise_admin_actions())
    assert len(users) == 1
    assert users[0].user_id == learner_user_id
    assert users[0].email == "riya@example.com"
    assert has_more is True
    assert featured == ["A helpful tutor."]
    assert ("PATCH", "/rest/v1/learner_feedback", {"is_featured": True}) in calls
    suspension_updates = [
        body for method, path, body in calls
        if method == "POST" and path == "/rest/v1/learner_account_status"
    ]
    assert [body["suspended"] for body in suspension_updates if body] == [True, False]
    assert all(body and body["user_id"] == learner_user_id and body["updated_at"] for body in suspension_updates)
    assert ("PUT", f"/auth/v1/admin/users/{learner_user_id}", {"ban_duration": "876000h"}) in calls
    assert ("PUT", f"/auth/v1/admin/users/{learner_user_id}", {"ban_duration": "none"}) in calls
    assert ("DELETE", f"/auth/v1/admin/users/{learner_user_id}", None) in calls


def test_supabase_auth_validates_access_token_and_extracts_verified_identity() -> None:
    user_id = str(uuid4())

    def respond(request: httpx.Request) -> httpx.Response:
        if not request.url.path.endswith("/auth/v1/user"):
            assert request.url.path.endswith("/rest/v1/learner_account_status")
            assert request.headers["apikey"] == "server-only-test-key"
            return httpx.Response(200, json=[])
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
            supabase_service_role_key="server-only-test-key",
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


def test_supabase_secret_key_is_sent_only_as_api_key() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        assert request.headers["apikey"] == "sb_secret_test-key"
        assert "authorization" not in request.headers
        if request.url.path.endswith("/auth/v1/admin/users"):
            return httpx.Response(200, json={"users": []})
        assert request.url.path.endswith("/rest/v1/learner_account_status")
        return httpx.Response(200, json=[])

    repository = SupabaseSessionRepository(
        Settings(
            supabase_url="https://example.supabase.co",
            supabase_secret_key="sb_secret_test-key",
        ),
        transport=httpx.MockTransport(respond),
    )

    async def exercise() -> None:
        try:
            users, has_more = await repository.list_admin_users(1, 50)
            assert users == []
            assert has_more is False
            await repository.is_user_suspended(str(uuid4()))
        finally:
            await repository.close()

    asyncio.run(exercise())


def test_supabase_auth_blocks_suspended_users_with_existing_tokens() -> None:
    user_id = str(uuid4())

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/auth/v1/user"):
            return httpx.Response(
                200,
                json={"id": user_id, "email": "riya@example.com", "user_metadata": {}},
            )
        assert request.url.path.endswith("/rest/v1/learner_account_status")
        return httpx.Response(200, json=[{"suspended": True}])

    repository = SupabaseSessionRepository(
        Settings(
            supabase_url="https://example.supabase.co",
            supabase_publishable_key="public-test-key",
            supabase_service_role_key="server-only-test-key",
        ),
        transport=httpx.MockTransport(respond),
    )

    async def authenticate_and_close() -> None:
        try:
            await repository.authenticate("valid-access-token")
        finally:
            await repository.close()

    with pytest.raises(SuspendedAccount):
        asyncio.run(authenticate_and_close())


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
