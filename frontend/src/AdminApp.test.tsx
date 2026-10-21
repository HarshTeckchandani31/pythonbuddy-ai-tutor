import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import AdminApp from "./AdminApp";
import { adminApi, type AdminFeedbackEntry } from "./api";
import { authApi, type AuthSession } from "./auth";

vi.mock("./api", () => ({
  adminApi: {
    getStatus: vi.fn(),
    getUsers: vi.fn(),
    getFeedback: vi.fn(),
    setFeedbackFeatured: vi.fn(),
    getUserProgress: vi.fn(),
    setUserSuspended: vi.fn(),
    deleteUser: vi.fn(),
  },
}));

vi.mock("./auth", () => ({
  supabaseConfigured: true,
  authApi: {
    getSession: vi.fn(),
    onAuthStateChange: vi.fn(() => () => {}),
    signIn: vi.fn(),
    signOut: vi.fn(),
  },
}));

const adminSession = {
  access_token: "test-token",
  token_type: "bearer",
  expires_in: 3600,
  expires_at: 1_900_000_000,
  refresh_token: "test-refresh-token",
  user: {
    id: "admin-user",
    app_metadata: { provider: "email", providers: ["email"] },
    aud: "authenticated",
    created_at: "2026-01-01T00:00:00Z",
    email: "admin@example.com",
    user_metadata: { full_name: "Admin" },
  },
} satisfies AuthSession;

const feedback = {
  id: "feedback-1",
  user_id: "learner-1",
  feedback: "The lessons are clear.",
  created_at: "2026-01-01T00:00:00Z",
  is_featured: false,
} satisfies AdminFeedbackEntry;

const learner = {
  user_id: "learner-1",
  email: "learner@example.com",
  full_name: "Riya",
  created_at: "2026-01-01T00:00:00Z",
  last_sign_in_at: "2026-02-01T00:00:00Z",
  banned_until: null,
};

beforeEach(() => {
  vi.mocked(authApi.getSession).mockResolvedValue(null);
  vi.mocked(authApi.signIn).mockResolvedValue(adminSession);
  vi.mocked(adminApi.getStatus).mockResolvedValue({ is_admin: true });
  vi.mocked(adminApi.getUsers).mockResolvedValue({ users: [], has_more: false });
  vi.mocked(adminApi.getFeedback).mockResolvedValue({ items: [feedback] });
  vi.mocked(adminApi.setFeedbackFeatured).mockResolvedValue({ message: "Feedback display setting updated." });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("admin dashboard", () => {
  it("uses sign-in only and allows the authorized admin to feature feedback", async () => {
    const user = userEvent.setup();
    render(<AdminApp />);

    expect(await screen.findByRole("heading", { name: "Administrator sign in." })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /create account/i })).not.toBeInTheDocument();
    await user.type(screen.getByLabelText("Email"), "admin@example.com");
    await user.type(screen.getByLabelText("Password"), "password123");
    await user.click(screen.getByRole("button", { name: "Sign in as administrator" }));

    expect(await screen.findByRole("heading", { name: "Manage PythonBuddy." })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Feedback" }));
    const featureToggle = await screen.findByRole("checkbox", { name: "Display on login page" });
    await user.click(featureToggle);

    expect(adminApi.setFeedbackFeatured).toHaveBeenCalledWith("feedback-1", true);
    expect(featureToggle).toBeChecked();
  });

  it("does not show the dashboard to an account rejected by the server", async () => {
    const user = userEvent.setup();
    vi.mocked(adminApi.getStatus).mockRejectedValue(new Error("Administrator access required."));
    render(<AdminApp />);

    await user.type(await screen.findByLabelText("Email"), "learner@example.com");
    await user.type(screen.getByLabelText("Password"), "password123");
    await user.click(screen.getByRole("button", { name: "Sign in as administrator" }));

    expect(await screen.findByRole("heading", { name: "Administrator access denied." })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Manage PythonBuddy." })).not.toBeInTheDocument();
  });

  it("shows user accounts and loads their progress on demand", async () => {
    const user = userEvent.setup();
    vi.mocked(adminApi.getUsers).mockResolvedValue({ users: [learner], has_more: false });
    vi.mocked(adminApi.getUserProgress).mockResolvedValue({
      user_id: learner.user_id,
      sessions: [{
        session_id: "session-1",
        profile: { name: "Riya", level: "beginner", difficulty: "beginner", topic: "Python variables" },
        created_at: "2026-01-05T00:00:00Z",
        updated_at: "2026-01-05T00:00:00Z",
        progress: {
          attempted: 2,
          correct: 1,
          accuracy_percent: 50,
          strengths: [],
          needs_practice: ["python variables"],
        },
      }],
    });
    render(<AdminApp />);
    await user.type(await screen.findByLabelText("Email"), "admin@example.com");
    await user.type(screen.getByLabelText("Password"), "password123");
    await user.click(screen.getByRole("button", { name: "Sign in as administrator" }));

    await user.click(await screen.findByRole("button", { name: "Review progress" }));
    expect(await screen.findByText("Needs practice: python variables")).toBeInTheDocument();
    expect(adminApi.getUserProgress).toHaveBeenCalledWith(learner.user_id);
  });
});
