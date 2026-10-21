from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


PYTHON_TOPICS = frozenset(
    {
        "Python variables",
        "Data types and strings",
        "Conditionals",
        "For and while loops",
        "Lists and dictionaries",
        "Functions",
        "Input and output",
    }
)


ShortText = Annotated[str, Field(min_length=1, max_length=120)]
AnswerText = Annotated[str, Field(min_length=1, max_length=3000)]


class LearnerLevel(StrEnum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class LearnerProfile(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: Annotated[str, Field(min_length=1, max_length=40)]
    level: LearnerLevel
    difficulty: LearnerLevel
    topic: Annotated[str, Field(min_length=1, max_length=80)]

    @field_validator("topic")
    @classmethod
    def supported_topic(cls, topic: str) -> str:
        if topic not in PYTHON_TOPICS:
            raise ValueError("topic must be one of the supported Python topics")
        return topic


class InitializeSessionRequest(LearnerProfile):
    pass


class SessionResponse(BaseModel):
    session_id: str
    profile: LearnerProfile
    progress: "ProgressResponse"


class LessonRequest(BaseModel):
    topic: ShortText | None = None

    @field_validator("topic")
    @classmethod
    def supported_topic(cls, topic: str | None) -> str | None:
        if topic is not None and topic not in PYTHON_TOPICS:
            raise ValueError("topic must be one of the supported Python topics")
        return topic


class LessonContent(BaseModel):
    explanation: Annotated[str, Field(min_length=1, max_length=4000)]
    example: Annotated[str, Field(min_length=1, max_length=2000)]
    check_question: Annotated[str, Field(min_length=1, max_length=500)]


class DoubtRequest(BaseModel):
    question: Annotated[str, Field(min_length=1, max_length=1200)]


class FeedbackRequest(BaseModel):
    feedback: Annotated[str, Field(min_length=1, max_length=2000)]

    @field_validator("feedback")
    @classmethod
    def feedback_is_not_blank(cls, feedback: str) -> str:
        feedback = feedback.strip()
        if not feedback:
            raise ValueError("feedback must not be blank")
        return feedback


class DoubtContent(BaseModel):
    answer: Annotated[str, Field(min_length=1, max_length=4000)]
    follow_up_question: Annotated[str, Field(min_length=1, max_length=500)]


class FeedbackResponse(BaseModel):
    message: str


class FeaturedFeedbackResponse(BaseModel):
    feedback: list[str]


class AdminFeedbackItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    feedback: str
    created_at: str
    is_featured: bool


class AdminFeedbackListResponse(BaseModel):
    items: list[AdminFeedbackItem]


class FeedbackFeatureRequest(BaseModel):
    is_featured: bool


class AdminUserItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: str
    email: str
    full_name: str
    created_at: str
    last_sign_in_at: str | None = None
    banned_until: str | None = None


class AdminUserListResponse(BaseModel):
    users: list[AdminUserItem]
    has_more: bool


class AdminUserStatusRequest(BaseModel):
    suspended: bool


class AdminStatusResponse(BaseModel):
    is_admin: bool = True


class AdminActionResponse(BaseModel):
    message: str


class QuestionDraft(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    question: Annotated[str, Field(min_length=1, max_length=1200)]
    expected_answer: Annotated[str, Field(min_length=1, max_length=3000)]
    accepted_answers: list[Annotated[str, Field(min_length=1, max_length=3000)]] = Field(min_length=1, max_length=10)
    explanation: Annotated[str, Field(min_length=1, max_length=2000)]
    hint: Annotated[str, Field(min_length=1, max_length=600)]
    skill: Annotated[str, Field(min_length=1, max_length=80)]

    @field_validator("accepted_answers")
    @classmethod
    def strip_accepted_answers(cls, answers: list[str]) -> list[str]:
        cleaned = [answer.strip() for answer in answers if answer.strip()]
        if not cleaned:
            raise ValueError("at least one accepted answer is required")
        return cleaned

    @model_validator(mode="after")
    def include_expected_answer(self) -> "QuestionDraft":
        if self.expected_answer not in self.accepted_answers:
            self.accepted_answers.append(self.expected_answer)
        return self


class QuizDraft(BaseModel):
    questions: list[QuestionDraft] = Field(min_length=5, max_length=5)


class RecommendationContent(BaseModel):
    recommendation: Annotated[str, Field(min_length=1, max_length=600)]
    next_topic: Annotated[str, Field(min_length=1, max_length=120)]


class QuestionResponse(BaseModel):
    question_id: str
    question: str
    skill: str


class PracticeAnswerRequest(BaseModel):
    question_id: str
    answer: AnswerText


class ProgressResponse(BaseModel):
    attempted: int
    correct: int
    accuracy_percent: int
    strengths: list[str]
    needs_practice: list[str]


class AdminUserProgressItem(BaseModel):
    session_id: str
    profile: LearnerProfile
    created_at: str
    updated_at: str
    progress: ProgressResponse


class AdminUserProgressResponse(BaseModel):
    user_id: str
    sessions: list[AdminUserProgressItem]


class PracticeAnswerResponse(BaseModel):
    correct: bool
    feedback: str
    correct_answer: str
    explanation: str
    hint: str
    progress: ProgressResponse


class QuizAnswerResponse(BaseModel):
    question_id: str
    correct: bool
    feedback: str
    correct_answer: str
    explanation: str
    score: int
    answered: int
    complete: bool
    next_question: QuestionResponse | None


class QuizAnswerRequest(PracticeAnswerRequest):
    pass


class SummaryRequest(BaseModel):
    focus_topic: ShortText | None = None

    @field_validator("focus_topic")
    @classmethod
    def supported_focus_topic(cls, topic: str | None) -> str | None:
        if topic is not None and topic not in PYTHON_TOPICS:
            raise ValueError("focus topic must be one of the supported Python topics")
        return topic


class SummaryResponse(BaseModel):
    progress: ProgressResponse
    recommendation: Annotated[str, Field(min_length=1, max_length=600)]
    next_topic: Annotated[str, Field(min_length=1, max_length=120)]


class HealthResponse(BaseModel):
    status: str
    provider: str
    ai_configured: bool
    provider_timeout_seconds: float


class ErrorResponse(BaseModel):
    detail: str
