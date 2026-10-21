from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from backend.app.auth import get_admin_user, get_current_user
from backend.app.schemas import (
    AdminActionResponse,
    AdminFeedbackListResponse,
    AdminStatusResponse,
    AdminUserListResponse,
    AdminUserProgressResponse,
    AdminUserStatusRequest,
    FeaturedFeedbackResponse,
    DoubtContent,
    DoubtRequest,
    FeedbackFeatureRequest,
    FeedbackRequest,
    FeedbackResponse,
    HealthResponse,
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
        provider_timeout_seconds=settings.provider_timeout_seconds,
    )


@router.post("/feedback", response_model=FeedbackResponse, status_code=status.HTTP_201_CREATED)
async def submit_feedback(
    payload: FeedbackRequest,
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
) -> FeedbackResponse:
    await repository_from(request).submit_feedback(user, payload.feedback)
    return FeedbackResponse(message="Thanks for sharing your feedback.")


@router.get("/feedback/featured", response_model=FeaturedFeedbackResponse)
async def featured_feedback(request: Request) -> FeaturedFeedbackResponse:
    return FeaturedFeedbackResponse(feedback=await repository_from(request).get_featured_feedback())


@router.get("/admin/me", response_model=AdminStatusResponse)
async def admin_status(user: AuthenticatedUser = Depends(get_admin_user)) -> AdminStatusResponse:
    return AdminStatusResponse()


@router.get("/admin/feedback", response_model=AdminFeedbackListResponse)
async def admin_feedback(
    request: Request,
    user: AuthenticatedUser = Depends(get_admin_user),
) -> AdminFeedbackListResponse:
    return AdminFeedbackListResponse(items=await repository_from(request).list_feedback())


@router.patch("/admin/feedback/{feedback_id}", response_model=AdminActionResponse)
async def feature_feedback(
    feedback_id: str,
    payload: FeedbackFeatureRequest,
    request: Request,
    user: AuthenticatedUser = Depends(get_admin_user),
) -> AdminActionResponse:
    try:
        await repository_from(request).set_feedback_featured(feedback_id, payload.is_featured)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid feedback ID") from exc
    except SessionNotFound as exc:
        raise HTTPException(status_code=404, detail="Feedback not found") from exc
    return AdminActionResponse(message="Feedback display setting updated.")


@router.get("/admin/users", response_model=AdminUserListResponse)
async def admin_users(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    user: AuthenticatedUser = Depends(get_admin_user),
) -> AdminUserListResponse:
    users, has_more = await repository_from(request).list_admin_users(page, page_size)
    return AdminUserListResponse(users=users, has_more=has_more)


@router.get("/admin/users/{user_id}/progress", response_model=AdminUserProgressResponse)
async def admin_user_progress(
    user_id: UUID,
    request: Request,
    user: AuthenticatedUser = Depends(get_admin_user),
) -> AdminUserProgressResponse:
    try:
        sessions = await repository_from(request).get_admin_sessions(str(user_id))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid user ID") from exc
    service = service_from(request)
    return AdminUserProgressResponse(
        user_id=str(user_id),
        sessions=[
            {
                "session_id": item.session.session_id,
                "profile": item.session.profile,
                "created_at": item.created_at,
                "updated_at": item.updated_at,
                "progress": service.sessions.progress(item.session),
            }
            for item in sessions
        ],
    )


@router.patch("/admin/users/{user_id}/status", response_model=AdminActionResponse)
async def update_user_status(
    user_id: UUID,
    payload: AdminUserStatusRequest,
    request: Request,
    user: AuthenticatedUser = Depends(get_admin_user),
) -> AdminActionResponse:
    normalized_user_id = str(user_id)
    if normalized_user_id == user.user_id:
        raise HTTPException(status_code=400, detail="The administrator account cannot be suspended here.")
    try:
        await repository_from(request).set_user_suspended(normalized_user_id, payload.suspended)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid user ID") from exc
    except SessionNotFound as exc:
        raise HTTPException(status_code=404, detail="User not found") from exc
    action = "suspended" if payload.suspended else "reactivated"
    return AdminActionResponse(message=f"User account {action}.")


@router.delete("/admin/users/{user_id}", response_model=AdminActionResponse)
async def delete_user(
    user_id: UUID,
    request: Request,
    user: AuthenticatedUser = Depends(get_admin_user),
) -> AdminActionResponse:
    normalized_user_id = str(user_id)
    if normalized_user_id == user.user_id:
        raise HTTPException(status_code=400, detail="The administrator account cannot be deleted here.")
    try:
        await repository_from(request).delete_user(normalized_user_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid user ID") from exc
    except SessionNotFound as exc:
        raise HTTPException(status_code=404, detail="User not found") from exc
    return AdminActionResponse(message="User account and associated learning data deleted.")


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
