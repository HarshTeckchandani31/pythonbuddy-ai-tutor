import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { tutorApi } from "./api";
import { authApi, type AuthSession } from "./auth";
import type { LearnerSession, Progress, TutorQuestion } from "./types";

vi.mock("./api", () => ({
  tutorApi: {
    createSession: vi.fn(),
    getLatestSession: vi.fn(),
    learn: vi.fn(),
    askDoubt: vi.fn(),
    createPracticeQuestion: vi.fn(),
    submitPracticeAnswer: vi.fn(),
    startQuiz: vi.fn(),
    submitQuizAnswer: vi.fn(),
    getProgress: vi.fn(),
    getSummary: vi.fn(),
    submitFeedback: vi.fn(),
  },
}));

vi.mock("./auth", () => ({
  supabaseConfigured: true,
  authApi: {
    getSession: vi.fn(),
    onAuthStateChange: vi.fn(() => () => {}),
    signUp: vi.fn(),
    signIn: vi.fn(),
    signOut: vi.fn(),
  },
}));

const emptyProgress: Progress = {
  attempted: 0,
  correct: 0,
  accuracy_percent: 0,
  strengths: [],
  needs_practice: [],
};

const session: LearnerSession = {
  session_id: "session-1",
  profile: { name: "Riya", level: "beginner", difficulty: "beginner", topic: "Python variables" },
  progress: emptyProgress,
};

const question: TutorQuestion = {
  question_id: "question-1",
  question: "What value does count store?",
  skill: "python variables",
};

const authSession = {
  access_token: "test-token",
  token_type: "bearer",
  expires_in: 3600,
  expires_at: 1_900_000_000,
  refresh_token: "test-refresh-token",
  user: {
    id: "user-1",
    app_metadata: { provider: "email", providers: ["email"] },
    aud: "authenticated",
    created_at: "2026-01-01T00:00:00Z",
    email: "riya@example.com",
    user_metadata: { full_name: "Riya" },
  },
} satisfies AuthSession;

async function startApp() {
  const user = userEvent.setup();
  render(<App />);
  await user.type(await screen.findByLabelText("Your name"), "Riya");
  await user.type(screen.getByLabelText("Email"), "riya@example.com");
  await user.type(screen.getByLabelText("Password"), "password123");
  await user.click(screen.getByRole("button", { name: "Create account" }));
  const learnerName = await screen.findByLabelText("What should we call you?");
  await user.clear(learnerName);
  await user.type(learnerName, "Riya");
  await user.click(screen.getByRole("button", { name: "Start my lesson" }));
  await screen.findByText(/A variable stores a value/);
  return user;
}

beforeEach(() => {
  vi.mocked(authApi.getSession).mockResolvedValue(null);
  vi.mocked(authApi.signUp).mockResolvedValue(authSession);
  vi.mocked(tutorApi.getLatestSession).mockResolvedValue(null);
  vi.mocked(tutorApi.submitFeedback).mockResolvedValue({ message: "Thanks for sharing your feedback." });
  vi.mocked(tutorApi.createSession).mockResolvedValue(session);
  vi.mocked(tutorApi.learn).mockResolvedValue({
    explanation: "A variable stores a value.",
    example: "```python\ncount = 3\n```",
    check_question: "What value does count store?",
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("PythonBuddy workspace", () => {
  it("supports signing in with an existing account", async () => {
    const user = userEvent.setup();
    vi.mocked(authApi.signIn).mockResolvedValue(authSession);
    render(<App />);
    await user.click(await screen.findByRole("button", { name: "Already have an account? Sign in" }));
    await user.type(screen.getByLabelText("Email"), "riya@example.com");
    await user.type(screen.getByLabelText("Password"), "password123");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByLabelText("What should we call you?")).toBeInTheDocument();
    expect(authApi.signIn).toHaveBeenCalledWith("riya@example.com", "password123");
  });

  it("asks users to verify their email before signing in", async () => {
    vi.mocked(authApi.signUp).mockResolvedValue(null);
    const user = userEvent.setup();
    render(<App />);
    await user.type(await screen.findByLabelText("Your name"), "Riya");
    await user.type(screen.getByLabelText("Email"), "riya@example.com");
    await user.type(screen.getByLabelText("Password"), "password123");
    await user.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByRole("status")).toHaveTextContent("Check your email for a confirmation link");
    expect(authApi.signUp).toHaveBeenCalledWith("riya@example.com", "password123", "Riya");
  });

  it("restores the latest saved session after sign-in", async () => {
    vi.mocked(authApi.getSession).mockResolvedValue(authSession);
    vi.mocked(tutorApi.getLatestSession).mockResolvedValue(session);
    render(<App />);

    expect(await screen.findByRole("heading", { name: /python variables/i })).toBeInTheDocument();
    expect(screen.getByText("Welcome back. Your last session was python variables. Your saved progress is restored.")).toBeInTheDocument();
    expect(screen.getByText("0 attempts")).toBeInTheDocument();
  });

  it("creates a personalized session and loads Learn mode", async () => {
    await startApp();
    expect(tutorApi.createSession).toHaveBeenCalledWith({
      name: "Riya",
      level: "beginner",
      difficulty: "beginner",
      topic: "Python variables",
    });
    expect(screen.getByRole("heading", { name: /python variables/i })).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "0");
    expect(screen.getByText("0 attempts")).toBeInTheDocument();
  });

  it("submits feedback and confirms it was received", async () => {
    const user = await startApp();
    const feedback = screen.getByLabelText("What’s working well, or what could be better?");
    await user.type(feedback, "More examples would help.");
    await user.click(screen.getByRole("button", { name: "Send feedback" }));

    expect(await screen.findByRole("status")).toHaveTextContent("Thanks for sharing your feedback.");
    expect(tutorApi.submitFeedback).toHaveBeenCalledWith("More examples would help.");
    expect(feedback).toHaveValue("");
  });

  it("uses the recorded practice response to update progress", async () => {
    const user = await startApp();
    vi.mocked(tutorApi.createPracticeQuestion).mockResolvedValue(question);
    vi.mocked(tutorApi.submitPracticeAnswer).mockResolvedValue({
      correct: true,
      feedback: "Correct. Nice work.",
      correct_answer: "3",
      explanation: "count is assigned the integer 3.",
      hint: "Look at the value after the equals sign.",
      progress: {
        attempted: 1,
        correct: 1,
        accuracy_percent: 100,
        strengths: ["python variables"],
        needs_practice: [],
      },
    });

    await user.click(screen.getByRole("tab", { name: "Practice" }));
    await screen.findAllByText("What value does count store?");
    await user.type(screen.getByLabelText("Your message"), "3");
    await user.click(screen.getByRole("button", { name: "Send answer" }));

    expect(await screen.findByText("Correct. Nice work.")).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "100");
    expect(screen.getByText("python variables")).toBeInTheDocument();
  });

  it("shows the server-provided hint after an incorrect practice answer", async () => {
    const user = await startApp();
    vi.mocked(tutorApi.createPracticeQuestion).mockResolvedValue(question);
    vi.mocked(tutorApi.submitPracticeAnswer).mockResolvedValue({
      correct: false,
      feedback: "Not quite yet.",
      correct_answer: "3",
      explanation: "The assignment stores the value on the right.",
      hint: "Look at the value after the equals sign.",
      progress: {
        attempted: 1,
        correct: 0,
        accuracy_percent: 0,
        strengths: [],
        needs_practice: ["python variables"],
      },
    });

    await user.click(screen.getByRole("tab", { name: "Practice" }));
    await screen.findAllByText("What value does count store?");
    await user.type(screen.getByLabelText("Your message"), "4");
    await user.click(screen.getByRole("button", { name: "Send answer" }));

    expect(await screen.findByText(/Look at the value after the equals sign/)).toBeInTheDocument();
    expect(screen.getByText("python variables")).toBeInTheDocument();
  });

  it("advances to the server-provided next quiz question", async () => {
    const user = await startApp();
    vi.mocked(tutorApi.startQuiz).mockResolvedValue(question);
    vi.mocked(tutorApi.submitQuizAnswer).mockResolvedValue({
      question_id: question.question_id,
      correct: true,
      feedback: "Correct. Nice work.",
      correct_answer: "3",
      explanation: "count is assigned the integer 3.",
      score: 1,
      answered: 1,
      complete: false,
      next_question: { question_id: "question-2", question: "What type is 'hello'?", skill: "python strings" },
    });
    vi.mocked(tutorApi.getProgress).mockResolvedValue({
      attempted: 1,
      correct: 1,
      accuracy_percent: 100,
      strengths: ["python variables"],
      needs_practice: [],
    });

    await user.click(screen.getByRole("tab", { name: "Quiz" }));
    await screen.findByText("Question 1 of 5");
    await user.type(screen.getByLabelText("Your message"), "3");
    await user.click(screen.getByRole("button", { name: "Send answer" }));

    expect(await screen.findByText("Question 2 of 5")).toBeInTheDocument();
    expect(screen.getByText("What type is 'hello'?" )).toBeInTheDocument();
    expect(tutorApi.getProgress).toHaveBeenCalledWith("session-1");
  });

  it("shows backend errors without inventing progress", async () => {
    const user = userEvent.setup();
    vi.mocked(tutorApi.createSession).mockRejectedValue(new Error("AI provider credentials are not configured"));
    render(<App />);
    await user.type(await screen.findByLabelText("Your name"), "Riya");
    await user.type(screen.getByLabelText("Email"), "riya@example.com");
    await user.type(screen.getByLabelText("Password"), "password123");
    await user.click(screen.getByRole("button", { name: "Create account" }));
    await user.click(await screen.findByRole("button", { name: "Start my lesson" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("credentials are not configured");
    expect(screen.getByRole("heading", { name: /python that finally clicks/i })).toBeInTheDocument();
  });
});
