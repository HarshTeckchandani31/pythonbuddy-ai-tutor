import type {
  DoubtContent,
  LearnerProfile,
  LearnerSession,
  LessonContent,
  PracticeAnswer,
  QuizAnswer,
  SessionSummary,
  TutorQuestion,
} from "./types";
import { authApi } from "./auth";

const API_BASE = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") || "/api";

async function request<T>(path: string, body?: unknown): Promise<T> {
  const session = await authApi.getSession();
  if (!session) throw new Error("Please sign in again to continue.");
  const response = await fetch(`${API_BASE}${path}`, {
    method: body === undefined ? "GET" : "POST",
    headers: {
      Authorization: `Bearer ${session.access_token}`,
      ...(body === undefined ? {} : { "Content-Type": "application/json" }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail =
      typeof payload === "object" && payload !== null && "detail" in payload && typeof payload.detail === "string"
        ? payload.detail
        : "The tutor could not complete that request.";
    throw new Error(detail);
  }
  return payload as T;
}

export const tutorApi = {
  createSession: (profile: LearnerProfile) => request<LearnerSession>("/sessions", profile),
  getLatestSession: () => request<LearnerSession | null>("/sessions/latest"),
  learn: (sessionId: string, topic: string) =>
    request<LessonContent>(`/sessions/${sessionId}/learn`, { topic }),
  askDoubt: (sessionId: string, question: string) =>
    request<DoubtContent>(`/sessions/${sessionId}/doubt`, { question }),
  createPracticeQuestion: (sessionId: string) =>
    request<TutorQuestion>(`/sessions/${sessionId}/practice/questions`, {}),
  submitPracticeAnswer: (sessionId: string, questionId: string, answer: string) =>
    request<PracticeAnswer>(`/sessions/${sessionId}/practice/answers`, { question_id: questionId, answer }),
  startQuiz: (sessionId: string) => request<TutorQuestion>(`/sessions/${sessionId}/quiz`, {}),
  submitQuizAnswer: (sessionId: string, questionId: string, answer: string) =>
    request<QuizAnswer>(`/sessions/${sessionId}/quiz/answers`, { question_id: questionId, answer }),
  getProgress: (sessionId: string) => request<LearnerSession["progress"]>(`/sessions/${sessionId}/progress`),
  getSummary: (sessionId: string) => request<SessionSummary>(`/sessions/${sessionId}/summary`, {}),
};
