from fastapi import APIRouter, Depends, HTTPException, Request, status

from backend.app.auth import get_current_user
from backend.app.schemas import (
    HealthResponse,
    DoubtContent,
    DoubtRequest,
    InitializeSessionRequest,
    LessonContent,
    LessonRequest,
    PracticeAnswerRequest,
    PracticeAnswerResponse,
    ProgressResponse,
    QuestionResponse,
    QuizAnswerResponse,
    QuizAnswerRequest,
    SessionResponse,
    SummaryRequest,
    SummaryResponse,
)
from backend.app.sessions import SessionNotFound
from backend.app.storage import AuthenticatedUser, SessionRepository
from backend.app.services import QuestionAlreadyAnswered, QuestionNotFound, QuizConflict, TutorService


router = APIRouter(prefix="/api")


def service_from(request: Request) -> TutorService:
    return request.app.state.tutor_service


def repository_from(request: Request) -> SessionRepository:
    return request.app.state.session_repository


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    settings = request.app.state.settings
    return HealthResponse(
        status="ok",
        provider=settings.ai_provider,
        ai_configured=bool(
            settings.gemini_api_key if settings.ai_provider == "gemini" else settings.anthropic_api_key
        ),
    )


@router.post("/sessions", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def initialize_session(
    payload: InitializeSessionRequest,
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
) -> SessionResponse:
    service = service_from(request)
    session = await repository_from(request).create_session(user, payload)
    return SessionResponse(
        session_id=session.session_id,
        profile=session.profile,
        progress=service.sessions.progress(session),
    )


@router.get("/sessions/latest", response_model=SessionResponse | None)
async def latest_session(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
) -> SessionResponse | None:
    session = await repository_from(request).get_latest_session(user.user_id)
    if session is None:
        return None
    service = service_from(request)
    return SessionResponse(
        session_id=session.session_id,
        profile=session.profile,
        progress=service.sessions.progress(session),
    )


@router.post("/sessions/{session_id}/learn", response_model=LessonContent)
async def learn(
    session_id: str,
    payload: LessonRequest,
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
) -> LessonContent:
    service = service_from(request)
    session = await repository_from(request).get_session(user.user_id, session_id)
    return await service.learn(session, payload.topic)


@router.post("/sessions/{session_id}/doubt", response_model=DoubtContent)
async def answer_doubt(
    session_id: str,
    payload: DoubtRequest,
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
) -> DoubtContent:
    service = service_from(request)
    session = await repository_from(request).get_session(user.user_id, session_id)
    return await service.answer_doubt(session, payload.question)


@router.post(
    "/sessions/{session_id}/practice/questions",
    response_model=QuestionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def practice_question(
    session_id: str,
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
) -> QuestionResponse:
    service = service_from(request)
    repository = repository_from(request)
    session = await repository.get_session(user.user_id, session_id)
    question = await service.practice_question(session)
    await repository.save_session(user.user_id, session)
    return question


@router.post("/sessions/{session_id}/practice/answers", response_model=PracticeAnswerResponse)
async def practice_answer(
    session_id: str,
    payload: PracticeAnswerRequest,
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
) -> PracticeAnswerResponse:
    service = service_from(request)
    repository = repository_from(request)
    session = await repository.get_session(user.user_id, session_id)
    try:
        result = service.submit_practice(session, payload.question_id, payload.answer)
        await repository.save_session(user.user_id, session)
        return result
    except QuestionAlreadyAnswered as exc:
        raise HTTPException(status_code=409, detail="Practice question has already been answered") from exc
    except QuestionNotFound as exc:
        raise HTTPException(status_code=404, detail="Practice question not found") from exc


@router.post(
    "/sessions/{session_id}/quiz",
    response_model=QuestionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def start_quiz(
    session_id: str,
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
) -> QuestionResponse:
    service = service_from(request)
    repository = repository_from(request)
    session = await repository.get_session(user.user_id, session_id)
    question = await service.start_quiz(session)
    await repository.save_session(user.user_id, session)
    return question


@router.post("/sessions/{session_id}/quiz/answers", response_model=QuizAnswerResponse)
async def quiz_answer(
    session_id: str,
    payload: QuizAnswerRequest,
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
) -> QuizAnswerResponse:
    service = service_from(request)
    repository = repository_from(request)
    session = await repository.get_session(user.user_id, session_id)
    try:
        result = service.submit_quiz(session, payload.question_id, payload.answer)
        await repository.save_session(user.user_id, session)
        return result
    except QuizConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/sessions/{session_id}/progress", response_model=ProgressResponse)
async def progress(
    session_id: str,
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
) -> ProgressResponse:
    service = service_from(request)
    session = await repository_from(request).get_session(user.user_id, session_id)
    return service.sessions.progress(session)


@router.post("/sessions/{session_id}/summary", response_model=SummaryResponse)
async def summary(
    session_id: str,
    payload: SummaryRequest,
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
) -> SummaryResponse:
    service = service_from(request)
    session = await repository_from(request).get_session(user.user_id, session_id)
    return await service.summary(session, payload.focus_topic)
