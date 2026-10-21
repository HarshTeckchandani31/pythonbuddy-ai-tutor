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

async function request<T>(
  path: string,
  method: "GET" | "POST" | "PATCH" | "DELETE" = "GET",
  body?: unknown,
  authenticated = true,
): Promise<T> {
  const session = authenticated ? await authApi.getSession() : null;
  if (authenticated && !session) throw new Error("Please sign in again to continue.");
  const headers: Record<string, string> = {};
  if (session) headers.Authorization = `Bearer ${session.access_token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const response = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail =
      typeof payload === "object" && payload !== null && "detail" in payload && typeof payload.detail === "string"
        ? payload.detail
        : "The request could not be completed.";
    throw new Error(detail);
  }
  return payload as T;
}

export const tutorApi = {
  submitFeedback: (feedback: string) =>
    request<{ message: string }>("/feedback", "POST", { feedback }),
  createSession: (profile: LearnerProfile) => request<LearnerSession>("/sessions", "POST", profile),
  getLatestSession: () => request<LearnerSession | null>("/sessions/latest"),
  learn: (sessionId: string, topic: string) =>
    request<LessonContent>(`/sessions/${sessionId}/learn`, "POST", { topic }),
  askDoubt: (sessionId: string, question: string) =>
    request<DoubtContent>(`/sessions/${sessionId}/doubt`, "POST", { question }),
  createPracticeQuestion: (sessionId: string) =>
    request<TutorQuestion>(`/sessions/${sessionId}/practice/questions`, "POST", {}),
  submitPracticeAnswer: (sessionId: string, questionId: string, answer: string) =>
    request<PracticeAnswer>(`/sessions/${sessionId}/practice/answers`, "POST", { question_id: questionId, answer }),
  startQuiz: (sessionId: string) => request<TutorQuestion>(`/sessions/${sessionId}/quiz`, "POST", {}),
  submitQuizAnswer: (sessionId: string, questionId: string, answer: string) =>
    request<QuizAnswer>(`/sessions/${sessionId}/quiz/answers`, "POST", { question_id: questionId, answer }),
  getProgress: (sessionId: string) => request<LearnerSession["progress"]>(`/sessions/${sessionId}/progress`),
  getSummary: (sessionId: string) => request<SessionSummary>(`/sessions/${sessionId}/summary`, "POST", {}),
};

export interface AdminUser {
  user_id: string;
  email: string;
  full_name: string;
  created_at: string;
  last_sign_in_at: string | null;
  banned_until: string | null;
}

export interface AdminFeedbackEntry {
  id: string;
  user_id: string;
  feedback: string;
  created_at: string;
  is_featured: boolean;
}

export interface AdminUserProgress {
  user_id: string;
  sessions: Array<{
    session_id: string;
    profile: LearnerProfile;
    created_at: string;
    updated_at: string;
    progress: LearnerSession["progress"];
  }>;
}

export const publicApi = {
  getFeaturedFeedback: () =>
    request<{ feedback: string[] }>("/feedback/featured", "GET", undefined, false),
};

export const adminApi = {
  getStatus: () => request<{ is_admin: boolean }>("/admin/me"),
  getUsers: (page: number) =>
    request<{ users: AdminUser[]; has_more: boolean }>(`/admin/users?page=${page}&page_size=50`),
  getFeedback: () => request<{ items: AdminFeedbackEntry[] }>("/admin/feedback"),
  setFeedbackFeatured: (id: string, isFeatured: boolean) =>
    request<{ message: string }>(`/admin/feedback/${encodeURIComponent(id)}`, "PATCH", { is_featured: isFeatured }),
  getUserProgress: (id: string) =>
    request<AdminUserProgress>(`/admin/users/${encodeURIComponent(id)}/progress`),
  setUserSuspended: (id: string, suspended: boolean) =>
    request<{ message: string }>(`/admin/users/${encodeURIComponent(id)}/status`, "PATCH", { suspended }),
  deleteUser: (id: string) =>
    request<{ message: string }>(`/admin/users/${encodeURIComponent(id)}`, "DELETE"),
};
