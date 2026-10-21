from collections.abc import Iterable

import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.auth import get_current_user
from backend.app.main import FRONTEND_INDEX, create_app
from backend.app.providers.base import MissingCredentials, ProviderRateLimited, ProviderTimeout
from backend.app.storage import AuthenticatedUser, InMemorySessionRepository


TEST_USER_ID = "00000000-0000-0000-0000-000000000001"


def question_payload(index: int = 1) -> dict[str, object]:
    return {
        "question": f"What value does item {index} have?",
        "expected_answer": f"answer-{index}",
        "accepted_answers": [f"answer-{index}"],
        "explanation": f"The value for item {index} is answer-{index}.",
        "hint": "Read the prompt carefully.",
        "skill": "python variables",
    }


class FakeProvider:
    def __init__(self, responses: Iterable[object] = (), error: Exception | None = None) -> None:
        self.responses = list(responses)
        self.error = error
        self.prompts: list[str] = []

    async def generate_json(self, prompt: str) -> dict[str, object]:
        self.prompts.append(prompt)
        if self.error:
            raise self.error
        return self.responses.pop(0)  # type: ignore[return-value]


def make_client(
    provider: FakeProvider,
    configured: bool = True,
    repository: InMemorySessionRepository | None = None,
    user_id: str = TEST_USER_ID,
    admin_email: str = "",
) -> TestClient:
    settings = Settings(
        gemini_api_key="test-key" if configured else "",
        admin_email=admin_email,
    )
    app = create_app(
        settings=settings,
        provider=provider,
        session_repository=repository or InMemorySessionRepository(),
    )

    async def authenticated_user() -> AuthenticatedUser:
        return AuthenticatedUser(user_id=user_id, email="learner@example.com", full_name="Learner")

    app.dependency_overrides[get_current_user] = authenticated_user
    return TestClient(app)


def create_session(client: TestClient) -> str:
    response = client.post(
        "/api/sessions",
        json={
            "name": "Sam",
            "level": "beginner",
            "difficulty": "beginner",
            "topic": "Python variables",
        },
    )
    assert response.status_code == 201
    assert response.json()["progress"] == {
        "attempted": 0,
        "correct": 0,
        "accuracy_percent": 0,
        "strengths": [],
        "needs_practice": [],
    }
    return response.json()["session_id"]


def test_health_and_session_initialization() -> None:
    client = make_client(FakeProvider())
    assert client.get("/api/health").json() == {
        "status": "ok",
        "provider": "gemini",
        "ai_configured": True,
    }
    session_id = create_session(client)
    assert client.get(f"/api/sessions/{session_id}/progress").status_code == 200
    latest = client.get("/api/sessions/latest")
    assert latest.status_code == 200
    assert latest.json()["session_id"] == session_id


def test_feedback_is_saved_for_authenticated_user_and_validated() -> None:
    unauthenticated = TestClient(create_app(settings=Settings()))
    assert unauthenticated.post("/api/feedback", json={"feedback": "Hello"}).status_code == 401

    repository = InMemorySessionRepository()
    client = make_client(FakeProvider(), repository=repository)

    response = client.post("/api/feedback", json={"feedback": "  Great lesson!  "})

    assert response.status_code == 201
    assert response.json() == {"message": "Thanks for sharing your feedback."}
    assert repository.feedback_entries == [(TEST_USER_ID, "Great lesson!")]
    assert client.post("/api/feedback", json={"feedback": "   "}).status_code == 422
    assert client.post("/api/feedback", json={"feedback": "x" * 2001}).status_code == 422


def test_admin_access_is_allowlisted_and_feedback_is_published_anonymously() -> None:
    repository = InMemorySessionRepository()
    unauthorized = make_client(FakeProvider(), repository=repository, admin_email="admin@example.com")
    assert unauthorized.get("/api/admin/me").status_code == 403
    assert unauthorized.get("/api/admin/feedback").status_code == 403

    admin = make_client(
        FakeProvider(),
        repository=repository,
        admin_email=" LEARNER@example.com ",
    )
    assert admin.get("/api/admin/me").json() == {"is_admin": True}
    assert admin.get("/api/admin/users").json() == {"users": [], "has_more": False}
    assert admin.get("/api/feedback/featured").json() == {"feedback": []}
    session_id = create_session(admin)
    progress = admin.get(f"/api/admin/users/{TEST_USER_ID}/progress")
    assert progress.status_code == 200
    assert progress.json()["sessions"][0]["session_id"] == session_id

    assert admin.post("/api/feedback", json={"feedback": "Helpful lessons."}).status_code == 201
    feedback = admin.get("/api/admin/feedback").json()["items"][0]
    assert feedback["feedback"] == "Helpful lessons."
    assert feedback["is_featured"] is False

    selected = admin.patch(
        f"/api/admin/feedback/{feedback['id']}",
        json={"is_featured": True},
    )
    assert selected.status_code == 200
    assert admin.get("/api/feedback/featured").json() == {"feedback": ["Helpful lessons."]}


def test_admin_cannot_suspend_or_delete_its_own_account() -> None:
    admin = make_client(FakeProvider(), admin_email="learner@example.com")
    status = admin.patch(
        f"/api/admin/users/{TEST_USER_ID}/status",
        json={"suspended": True},
    )
    assert status.status_code == 400
    deleted = admin.delete(f"/api/admin/users/{TEST_USER_ID}")
    assert deleted.status_code == 400


def test_frontend_and_api_share_one_origin() -> None:
    client = make_client(FakeProvider())
    response = client.get("/")
    if FRONTEND_INDEX.is_file():
        assert response.status_code == 200
        assert '<div id="root"></div>' in response.text
        account = client.get("/account", headers={"accept": "text/html"})
        assert account.status_code == 200
        assert account.text == response.text
        admin = client.get("/admin", headers={"accept": "text/html"})
        assert admin.status_code == 200
        assert admin.text == response.text
        assert client.get("/api/health").status_code == 200
    else:
        assert response.status_code == 503


def test_api_requires_auth_and_sessions_are_private_to_their_owner() -> None:
    unauthenticated = TestClient(create_app(settings=Settings()))
    assert unauthenticated.get("/api/sessions/latest").status_code == 401

    repository = InMemorySessionRepository()
    owner = make_client(FakeProvider(), repository=repository)
    session_id = create_session(owner)
    another_user = make_client(
        FakeProvider(),
        repository=repository,
        user_id="00000000-0000-0000-0000-000000000002",
    )
    assert another_user.get(f"/api/sessions/{session_id}/progress").status_code == 404


def test_practice_feedback_and_progress_use_recorded_attempts() -> None:
    provider = FakeProvider([question_payload(1), question_payload(2)])
    client = make_client(provider)
    session_id = create_session(client)

    generated = client.post(f"/api/sessions/{session_id}/practice/questions")
    assert generated.status_code == 201
    question = generated.json()
    assert "expected_answer" not in question
    assert "answer-1" not in str(question)

    wrong = client.post(
        f"/api/sessions/{session_id}/practice/answers",
        json={"question_id": question["question_id"], "answer": "not it"},
    )
    assert wrong.status_code == 200
    assert wrong.json()["correct"] is False
    assert wrong.json()["progress"]["attempted"] == 1
    assert wrong.json()["progress"]["correct"] == 0

    repeated = client.post(
        f"/api/sessions/{session_id}/practice/answers",
        json={"question_id": question["question_id"], "answer": " ANSWER-1 "},
    )
    assert repeated.status_code == 409

    next_question = client.post(f"/api/sessions/{session_id}/practice/questions").json()
    correct = client.post(
        f"/api/sessions/{session_id}/practice/answers",
        json={"question_id": next_question["question_id"], "answer": " ANSWER-2 "},
    )
    assert correct.status_code == 200
    assert correct.json()["correct"] is True
    assert correct.json()["progress"]["attempted"] == 2
    assert correct.json()["progress"]["correct"] == 1
    assert correct.json()["progress"]["accuracy_percent"] == 50


def test_quiz_hides_answer_keys_and_scores_submissions() -> None:
    provider = FakeProvider([{"questions": [question_payload(index) for index in range(1, 6)]}])
    client = make_client(provider)
    session_id = create_session(client)

    started = client.post(f"/api/sessions/{session_id}/quiz")
    assert started.status_code == 201
    question = started.json()
    assert "expected_answer" not in question
    assert "accepted_answers" not in question

    wrong = client.post(
        f"/api/sessions/{session_id}/quiz/answers",
        json={"question_id": question["question_id"], "answer": "wrong"},
    )
    result = wrong.json()
    assert result["correct"] is False
    assert result["score"] == 0
    assert result["answered"] == 1
    assert result["complete"] is False
    assert result["next_question"] is not None
    assert "answer-2" not in str(result["next_question"])

    repeated = client.post(
        f"/api/sessions/{session_id}/quiz/answers",
        json={"question_id": question["question_id"], "answer": "answer-1"},
    )
    assert repeated.status_code == 409

    next_question = result["next_question"]
    correct = client.post(
        f"/api/sessions/{session_id}/quiz/answers",
        json={"question_id": next_question["question_id"], "answer": "answer-2"},
    )
    assert correct.json()["correct"] is True
    assert correct.json()["score"] == 1
    assert correct.json()["answered"] == 2
    active = correct.json()["next_question"]
    for index in range(3, 6):
        result = client.post(
            f"/api/sessions/{session_id}/quiz/answers",
            json={"question_id": active["question_id"], "answer": f"answer-{index}"},
        ).json()
        active = result["next_question"]
    assert result["complete"] is True
    assert result["next_question"] is None
    assert result["score"] == 4
    assert result["answered"] == 5


def test_learn_and_summary_return_validated_ai_content() -> None:
    provider = FakeProvider(
        [
            {
                "explanation": "A variable stores a value.",
                "example": "```python\ncount = 3\n```",
                "check_question": "What value does count store?",
            },
            {
                "recommendation": "Practice changing a variable and predict its value.",
                "next_topic": "Python data types",
            },
        ]
    )
    client = make_client(provider)
    session_id = create_session(client)
    lesson = client.post(f"/api/sessions/{session_id}/learn", json={})
    assert lesson.status_code == 200
    assert "count = 3" in lesson.json()["example"]
    assert all("Sam" not in prompt for prompt in provider.prompts)

    summary = client.post(f"/api/sessions/{session_id}/summary", json={})
    assert summary.status_code == 200
    assert summary.json()["progress"]["attempted"] == 0
    assert summary.json()["next_topic"] == "Python data types"


@pytest.mark.parametrize(
    ("provider_error", "expected_status"),
    [(ProviderRateLimited(), 429), (ProviderTimeout(), 504)],
)
def test_provider_failures_map_to_safe_http_errors(provider_error: Exception, expected_status: int) -> None:
    client = make_client(FakeProvider(error=provider_error))
    session_id = create_session(client)
    response = client.post(f"/api/sessions/{session_id}/practice/questions")
    assert response.status_code == expected_status
    assert "test-key" not in response.text


def test_missing_credentials_and_invalid_structured_output() -> None:
    no_credentials = make_client(
        FakeProvider(error=MissingCredentials()),
        configured=False,
    )
    session_id = create_session(no_credentials)
    unavailable = no_credentials.post(f"/api/sessions/{session_id}/practice/questions")
    assert unavailable.status_code == 503

    invalid = make_client(FakeProvider([{"question": "missing fields"}]))
    session_id = create_session(invalid)
    response = invalid.post(f"/api/sessions/{session_id}/practice/questions")
    assert response.status_code == 502
    assert response.json()["detail"] == "AI provider returned an invalid response"


def test_invalid_learner_input_is_rejected() -> None:
    client = make_client(FakeProvider())
    response = client.post(
        "/api/sessions",
        json={"name": "", "level": "newbie", "difficulty": "beginner", "topic": "Python"},
    )
    assert response.status_code == 422

    unsupported = client.post(
        "/api/sessions",
        json={"name": "Sam", "level": "beginner", "difficulty": "beginner", "topic": "Algebra"},
    )
    assert unsupported.status_code == 422


def test_doubt_endpoint_and_request_size_limit() -> None:
    provider = FakeProvider(
        [{"answer": "A variable is a named value.", "follow_up_question": "What name would you give it?"}]
    )
    client = make_client(provider)
    session_id = create_session(client)
    response = client.post(
        f"/api/sessions/{session_id}/doubt",
        json={"question": "What is a variable?"},
    )
    assert response.status_code == 200
    assert response.json()["answer"] == "A variable is a named value."

    limited = TestClient(
        create_app(settings=Settings(max_request_bytes=32), provider=FakeProvider())
    )
    oversized = limited.post(
        "/api/sessions",
        json={"name": "Sam", "level": "beginner", "difficulty": "beginner", "topic": "Python variables"},
    )
    assert oversized.status_code == 413


def test_deployment_limits_are_validated() -> None:
    with pytest.raises(ValueError, match="AI_TIMEOUT_SECONDS"):
        Settings(provider_timeout_seconds=0)
    with pytest.raises(ValueError, match="MAX_REQUEST_BYTES"):
        Settings(max_request_bytes=0)
