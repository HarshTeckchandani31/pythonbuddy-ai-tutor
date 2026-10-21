from uuid import uuid4

from pydantic import BaseModel, ValidationError
from typing import TypeVar

from backend.app.prompts import learner_context, question_task, structured_prompt
from backend.app.providers.base import AIProvider, InvalidProviderResponse
from backend.app.schemas import (
    LessonContent,
    DoubtContent,
    LearnerProfile,
    PracticeAnswerResponse,
    ProgressResponse,
    QuestionDraft,
    QuestionResponse,
    QuizAnswerResponse,
    QuizDraft,
    RecommendationContent,
    SummaryResponse,
)
from backend.app.sessions import (
    Attempt,
    LearningSession,
    QuizItem,
    SessionStore,
    check_answer,
)

ModelT = TypeVar("ModelT", bound=BaseModel)


class QuestionNotFound(Exception):
    pass


class QuestionAlreadyAnswered(Exception):
    pass


class QuizConflict(Exception):
    pass


class TutorService:
    def __init__(self, provider: AIProvider, sessions: SessionStore) -> None:
        self.provider = provider
        self.sessions = sessions

    async def _generate(self, response_model: type[ModelT], task: str) -> ModelT:
        prompt = structured_prompt(task, response_model)
        try:
            output = await self.provider.generate_json(prompt)
            return response_model.model_validate(output)
        except ValidationError as exc:
            raise InvalidProviderResponse from exc

    @staticmethod
    def _question_view(question_id: str, draft: QuestionDraft) -> QuestionResponse:
        return QuestionResponse(question_id=question_id, question=draft.question, skill=draft.skill)

    async def learn(self, session: LearningSession, topic: str | None = None) -> LessonContent:
        selected_topic = topic or session.profile.topic
        task = (
            f"{learner_context(session.profile, selected_topic)}\n"
            "Teach this Python topic in a concise beginner-friendly explanation. Include one short, correct Python code example "
            "and one check-for-understanding question. Do not claim the code was executed."
        )
        result = await self._generate(LessonContent, task)
        return result

    async def answer_doubt(self, session: LearningSession, question: str) -> DoubtContent:
        task = (
            f"{learner_context(session.profile)}\n"
            f"Answer this learner's Python doubt clearly and briefly: {question!r}. "
            "Use a small code snippet when useful. If it is unrelated to Python, gently redirect to Python. "
            "Never execute or claim to verify code. End with one helpful follow-up question."
        )
        return await self._generate(DoubtContent, task)

    async def practice_question(self, session: LearningSession) -> QuestionResponse:
        draft = await self._generate(
            QuestionDraft,
            question_task(session.profile),
        )
        question_id = str(uuid4())
        session.practice_questions[question_id] = draft  # answer key remains in the session store
        return self._question_view(question_id, draft)

    def submit_practice(self, session: LearningSession, question_id: str, answer: str) -> PracticeAnswerResponse:
        if question_id in session.answered_practice_ids:
            raise QuestionAlreadyAnswered
        draft = session.practice_questions.get(question_id)
        if draft is None:
            raise QuestionNotFound
        correct = check_answer(answer, draft)
        session.answered_practice_ids.add(question_id)
        session.attempts.append(Attempt(skill=draft.skill, correct=correct))
        return PracticeAnswerResponse(
            correct=correct,
            feedback="Correct. Nice work." if correct else "Not quite yet. Review the hint, then compare with the solution.",
            correct_answer=draft.expected_answer,
            explanation=draft.explanation,
            hint=draft.hint,
            progress=self.sessions.progress(session),
        )

    async def start_quiz(self, session: LearningSession) -> QuestionResponse:
        result = await self._generate(
            QuizDraft,
            question_task(session.profile, count=5),
        )
        session.quiz = [QuizItem(question_id=str(uuid4()), draft=item) for item in result.questions]
        session.quiz_cursor = 0
        current = session.quiz[0]
        return self._question_view(current.question_id, current.draft)

    def submit_quiz(self, session: LearningSession, question_id: str, answer: str) -> QuizAnswerResponse:
        if not session.quiz:
            raise QuizConflict("quiz has not started")
        if session.quiz_cursor >= len(session.quiz):
            raise QuizConflict("quiz is already complete")
        current = session.quiz[session.quiz_cursor]
        if current.question_id != question_id or current.answered:
            raise QuizConflict("answer does not match the active quiz question")

        correct = check_answer(answer, current.draft)
        current.answered = True
        current.correct = correct
        session.attempts.append(Attempt(skill=current.draft.skill, correct=correct))
        session.quiz_cursor += 1
        completed_items = session.quiz[:session.quiz_cursor]
        score = sum(item.correct is True for item in completed_items)
        complete = session.quiz_cursor == len(session.quiz)
        next_item = None if complete else session.quiz[session.quiz_cursor]
        return QuizAnswerResponse(
            question_id=question_id,
            correct=correct,
            feedback="Correct. Nice work." if correct else "That answer does not match. Review the explanation before the next question.",
            correct_answer=current.draft.expected_answer,
            explanation=current.draft.explanation,
            score=score,
            answered=session.quiz_cursor,
            complete=complete,
            next_question=self._question_view(next_item.question_id, next_item.draft) if next_item else None,
        )

    async def summary(self, session: LearningSession, focus_topic: str | None = None) -> SummaryResponse:
        progress = self.sessions.progress(session)
        topic = focus_topic or session.profile.topic
        task = (
            f"{learner_context(session.profile, topic)}\n"
            f"Recorded results only: attempted={progress.attempted}, correct={progress.correct}, "
            f"accuracy_percent={progress.accuracy_percent}, strengths={progress.strengths}, "
            f"needs_practice={progress.needs_practice}. "
            "Recommend one specific next Python topic and one brief action. If there are no attempts, "
            "recommend a suitable first step. Do not invent performance data."
        )
        recommendation = await self._generate(RecommendationContent, task)
        return SummaryResponse(
            progress=progress,
            recommendation=recommendation.recommendation,
            next_topic=recommendation.next_topic,
        )
