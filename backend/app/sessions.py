from dataclasses import dataclass, field
import re
from uuid import uuid4

from backend.app.schemas import LearnerProfile, ProgressResponse, QuestionDraft


@dataclass
class Attempt:
    skill: str
    correct: bool


@dataclass
class QuizItem:
    question_id: str
    draft: QuestionDraft
    answered: bool = False
    correct: bool | None = None


@dataclass
class LearningSession:
    session_id: str
    profile: LearnerProfile
    attempts: list[Attempt] = field(default_factory=list)
    practice_questions: dict[str, QuestionDraft] = field(default_factory=dict)
    answered_practice_ids: set[str] = field(default_factory=set)
    quiz: list[QuizItem] = field(default_factory=list)
    quiz_cursor: int = 0


class SessionNotFound(Exception):
    pass


class SessionStore:
    """In-memory session state. A process restart intentionally clears all data."""

    def __init__(self) -> None:
        self._sessions: dict[str, LearningSession] = {}

    def create(self, profile: LearnerProfile) -> LearningSession:
        session = LearningSession(session_id=str(uuid4()), profile=profile)
        self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> LearningSession:
        session = self._sessions.get(session_id)
        if session is None:
            raise SessionNotFound
        return session

    def progress(self, session: LearningSession) -> ProgressResponse:
        attempted = len(session.attempts)
        correct = sum(attempt.correct for attempt in session.attempts)
        by_skill: dict[str, list[int]] = {}
        for attempt in session.attempts:
            counts = by_skill.setdefault(attempt.skill, [0, 0])
            counts[0] += 1
            counts[1] += int(attempt.correct)

        strengths = sorted(skill for skill, counts in by_skill.items() if counts[1] / counts[0] >= 0.7)
        needs_practice = sorted(skill for skill, counts in by_skill.items() if counts[1] / counts[0] < 0.7)
        return ProgressResponse(
            attempted=attempted,
            correct=correct,
            accuracy_percent=round(100 * correct / attempted) if attempted else 0,
            strengths=strengths,
            needs_practice=needs_practice,
        )


def normalize_answer(answer: str) -> str:
    return re.sub(r"\s+", "", answer.strip().casefold())


def check_answer(answer: str, draft: QuestionDraft) -> bool:
    submitted = normalize_answer(answer)
    return any(submitted == normalize_answer(candidate) for candidate in draft.accepted_answers)
