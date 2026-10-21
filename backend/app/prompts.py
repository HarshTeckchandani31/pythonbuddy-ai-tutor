import json
from typing import TypeVar

from pydantic import BaseModel

from backend.app.schemas import LearnerProfile


ModelT = TypeVar("ModelT", bound=BaseModel)


def structured_prompt(task: str, response_model: type[ModelT]) -> str:
    schema = json.dumps(response_model.model_json_schema(), separators=(",", ":"))
    return (
        "You are PythonBuddy, a patient Python programming tutor for beginners. "
        "Teach Python only, never claim to execute code, and use concise explanations. "
        "Return one JSON object only, with no markdown fences or extra text, matching this schema exactly:\n"
        f"{schema}\n\nTASK:\n{task}"
    )


def learner_context(profile: LearnerProfile, topic: str | None = None) -> str:
    selected_topic = topic or profile.topic
    return (
        f"Level: {profile.level.value}. Difficulty: {profile.difficulty.value}. "
        f"Topic: {selected_topic}. "
        "Use beginner-friendly Python snippets. Never execute submitted code."
    )


def question_task(profile: LearnerProfile, topic: str | None = None, count: int = 1) -> str:
    context = learner_context(profile, topic)
    item = (
        "Create one Python practice question. Include a clear prompt, expected answer, "
        "all acceptable equivalent answers, a short explanation, one hint, and a concise skill name. "
        "Questions must be answerable without executing arbitrary code."
    )
    if count > 1:
        item = (
            f"Create exactly {count} distinct, progressively varied Python quiz questions. "
            "For each include a clear prompt, expected answer, acceptable equivalent answers, "
            "short explanation, one hint, and concise skill name. Do not include answer keys in question text. "
            "Questions must be answerable without executing arbitrary code."
        )
    return f"{context}\n{item}"
