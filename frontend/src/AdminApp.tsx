import { useEffect, useMemo, useState, type FormEvent } from "react";
import { adminApi, type AdminFeedbackEntry, type AdminUser, type AdminUserProgress } from "./api";
import { authApi, supabaseConfigured, type AuthSession } from "./auth";

function errorMessage(cause: unknown, fallback: string): string {
  return cause instanceof Error ? cause.message : fallback;
}

function suspended(user: AdminUser): boolean {
  return Boolean(user.banned_until && Date.parse(user.banned_until) > Date.now());
}

function dateLabel(value: string | null): string {
  if (!value) return "Never";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Unknown" : date.toLocaleDateString();
}

export default function AdminApp() {
  const [authSession, setAuthSession] = useState<AuthSession | null>(null);
  const [authReady, setAuthReady] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [authError, setAuthError] = useState("");
  const [authLoading, setAuthLoading] = useState(false);
  const [isAdmin, setIsAdmin] = useState<boolean | null>(null);
  const [accessError, setAccessError] = useState("");
  const [section, setSection] = useState<"users" | "feedback">("users");
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [usersPage, setUsersPage] = useState(1);
  const [hasMoreUsers, setHasMoreUsers] = useState(false);
  const [userSearch, setUserSearch] = useState("");
  const [userError, setUserError] = useState("");
  const [loadingUsers, setLoadingUsers] = useState(false);
  const [feedbackEntries, setFeedbackEntries] = useState<AdminFeedbackEntry[]>([]);
  const [feedbackError, setFeedbackError] = useState("");
  const [loadingFeedback, setLoadingFeedback] = useState(false);
  const [updatingFeedbackId, setUpdatingFeedbackId] = useState("");
  const [expandedUserId, setExpandedUserId] = useState("");
  const [userProgress, setUserProgress] = useState<Record<string, AdminUserProgress>>({});
  const [progressError, setProgressError] = useState("");
  const [loadingProgressId, setLoadingProgressId] = useState("");
  const [actionError, setActionError] = useState("");
  const [actionUserId, setActionUserId] = useState("");

  useEffect(() => {
    if (!supabaseConfigured) {
      setAuthReady(true);
      setAuthError("Supabase sign-in is not configured for this deployment.");
      return;
    }
    let active = true;
    const unsubscribe = authApi.onAuthStateChange((nextSession) => {
      if (active) {
        setAuthSession(nextSession);
        setAuthReady(true);
        setIsAdmin(null);
      }
    });
    void authApi.getSession()
      .then((session) => {
        if (active) setAuthSession(session);
      })
      .catch((cause: unknown) => {
        if (active) setAuthError(errorMessage(cause, "Could not restore your sign-in."));
      })
      .finally(() => {
        if (active) setAuthReady(true);
      });
    return () => {
      active = false;
      unsubscribe();
    };
  }, []);

  useEffect(() => {
    if (!authSession) {
      setIsAdmin(null);
      return;
    }
    let active = true;
    setIsAdmin(null);
    setAccessError("");
    void adminApi.getStatus()
      .then(() => {
        if (active) setIsAdmin(true);
      })
      .catch((cause: unknown) => {
        if (active) {
          setIsAdmin(false);
          setAccessError(errorMessage(cause, "Administrator access could not be verified."));
        }
      });
    return () => {
      active = false;
    };
  }, [authSession?.user.id]);

  useEffect(() => {
    if (!isAdmin) return;
    let active = true;
    setLoadingUsers(true);
    setUserError("");
    void adminApi.getUsers(usersPage)
      .then((result) => {
        if (!active) return;
        setUsers(result.users);
        setHasMoreUsers(result.has_more);
      })
      .catch((cause: unknown) => {
        if (active) setUserError(errorMessage(cause, "The user list could not be loaded."));
      })
      .finally(() => {
        if (active) setLoadingUsers(false);
      });
    return () => {
      active = false;
    };
  }, [isAdmin, usersPage]);

  useEffect(() => {
    if (!isAdmin) return;
    let active = true;
    setLoadingFeedback(true);
    setFeedbackError("");
    void adminApi.getFeedback()
      .then((result) => {
        if (active) setFeedbackEntries(result.items);
      })
      .catch((cause: unknown) => {
        if (active) setFeedbackError(errorMessage(cause, "Feedback could not be loaded."));
      })
      .finally(() => {
        if (active) setLoadingFeedback(false);
      });
    return () => {
      active = false;
    };
  }, [isAdmin]);

  const authenticate = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setAuthLoading(true);
    setAuthError("");
    try {
      setAuthSession(await authApi.signIn(email.trim(), password));
      setPassword("");
    } catch (cause) {
      setAuthError(errorMessage(cause, "Sign-in failed. Please try again."));
    } finally {
      setAuthLoading(false);
    }
  };

  const signOut = async () => {
    setAuthError("");
    try {
      await authApi.signOut();
      setAuthSession(null);
      setIsAdmin(null);
      setPassword("");
    } catch (cause) {
      setAuthError(errorMessage(cause, "Could not sign out."));
    }
  };

  const changeFeedbackVisibility = async (entry: AdminFeedbackEntry) => {
    setUpdatingFeedbackId(entry.id);
    setFeedbackError("");
    try {
      await adminApi.setFeedbackFeatured(entry.id, !entry.is_featured);
      setFeedbackEntries((current) =>
        current.map((item) => item.id === entry.id ? { ...item, is_featured: !item.is_featured } : item),
      );
    } catch (cause) {
      setFeedbackError(errorMessage(cause, "The feedback display setting could not be saved."));
    } finally {
      setUpdatingFeedbackId("");
    }
  };

  const toggleProgress = async (userId: string) => {
    if (expandedUserId === userId) {
      setExpandedUserId("");
      return;
    }
    setExpandedUserId(userId);
    setProgressError("");
    if (userProgress[userId]) return;
    setLoadingProgressId(userId);
    try {
      const result = await adminApi.getUserProgress(userId);
      setUserProgress((current) => ({ ...current, [userId]: result }));
    } catch (cause) {
      setProgressError(errorMessage(cause, "Learning progress could not be loaded."));
    } finally {
      setLoadingProgressId("");
    }
  };

  const setSuspended = async (user: AdminUser) => {
    setActionUserId(user.user_id);
    setActionError("");
    try {
      await adminApi.setUserSuspended(user.user_id, !suspended(user));
      const result = await adminApi.getUsers(usersPage);
      setUsers(result.users);
      setHasMoreUsers(result.has_more);
    } catch (cause) {
      setActionError(errorMessage(cause, "The account status could not be changed."));
    } finally {
      setActionUserId("");
    }
  };

  const deleteAccount = async (user: AdminUser) => {
    const confirmed = window.confirm(
      `Permanently delete ${user.email}? This also deletes their learning progress and submitted feedback.`,
    );
    if (!confirmed) return;
    setActionUserId(user.user_id);
    setActionError("");
    try {
      await adminApi.deleteUser(user.user_id);
      setUsers((current) => current.filter((item) => item.user_id !== user.user_id));
      setUserProgress((current) => {
        const next = { ...current };
        delete next[user.user_id];
        return next;
      });
    } catch (cause) {
      setActionError(errorMessage(cause, "The account could not be deleted."));
    } finally {
      setActionUserId("");
    }
  };

  const filteredUsers = useMemo(() => {
    const query = userSearch.trim().toLocaleLowerCase();
    if (!query) return users;
    return users.filter((user) =>
      user.email.toLocaleLowerCase().includes(query) || user.full_name.toLocaleLowerCase().includes(query),
    );
  }, [userSearch, users]);

  if (!authReady) {
    return <main className="auth-status" role="status">Checking administrator sign-in...</main>;
  }

  if (!authSession) {
    return (
      <div className="app-shell">
        <header className="topbar wrap">
          <a className="brand" href="/">Python<span className="brand-light">Buddy</span></a>
          <a className="admin-home-link" href="/">Learner sign in</a>
        </header>
        <main className="admin-login wrap">
          <form className="setup-form" onSubmit={(event) => void authenticate(event)}>
            <div className="form-heading"><span className="step-label">RESTRICTED ACCESS</span><span className="step-number">ADMIN</span></div>
            <h1>Administrator sign in.</h1>
            <p className="form-sub">Sign in with the account configured for administrator access.</p>
            {!supabaseConfigured && <p className="error-banner" role="alert">Set the Supabase browser settings before signing in.</p>}
            <label htmlFor="admin-email">Email</label>
            <input id="admin-email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" required />
            <label htmlFor="admin-password">Password</label>
            <input id="admin-password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" required />
            {authError && <p className="error-banner" role="alert">{authError}</p>}
            <button className="primary-button start-button admin-submit" disabled={authLoading || !supabaseConfigured} type="submit">
              {authLoading ? "Signing in..." : "Sign in as administrator"}
            </button>
          </form>
        </main>
      </div>
    );
  }

  if (isAdmin === null) {
    return <main className="auth-status" role="status">Verifying administrator access...</main>;
  }

  if (!isAdmin) {
    return (
      <main className="auth-status">
        <h1>Administrator access denied.</h1>
        <p>{accessError || "This account is not authorized to manage PythonBuddy."}</p>
        {authError && <p className="error-banner" role="alert">{authError}</p>}
        <div className="admin-toolbar"><a className="admin-home-link" href="/">Learner home</a><button type="button" onClick={() => void signOut()}>Sign out</button></div>
      </main>
    );
  }

  return (
    <div className="app-shell">
      <header className="topbar wrap">
        <a className="brand" href="/">Python<span className="brand-light">Buddy</span><span className="admin-badge">ADMIN</span></a>
        <div className="auth-user-actions"><span>{authSession.user.email}</span><button type="button" onClick={() => void signOut()}>Sign out</button></div>
      </header>
      <main className="admin-dashboard wrap">
        <section className="admin-heading">
          <div><div className="eyebrow"><span className="eyebrow-line" /> ADMINISTRATION</div><h1>Manage PythonBuddy.</h1><p>Review learner activity and choose which feedback appears publicly.</p></div>
          <a className="admin-home-link" href="/">View learner site</a>
        </section>
        <nav className="admin-tabs" aria-label="Admin sections">
          <button type="button" className={section === "users" ? "active" : ""} aria-pressed={section === "users"} onClick={() => setSection("users")}>Users</button>
          <button type="button" className={section === "feedback" ? "active" : ""} aria-pressed={section === "feedback"} onClick={() => setSection("feedback")}>Feedback</button>
        </nav>
        {actionError && <p className="error-banner" role="alert">{actionError}</p>}
        {section === "users" ? (
          <section className="admin-panel" aria-labelledby="admin-users-title">
            <div className="admin-panel-heading">
              <div><h2 id="admin-users-title">Signed-up users</h2><p>Review learning progress, suspend, reactivate, or permanently delete an account.</p></div>
              <input aria-label="Search users on this page" className="admin-search" placeholder="Search this page" value={userSearch} onChange={(event) => setUserSearch(event.target.value)} />
            </div>
            {userError && <p className="error-banner" role="alert">{userError}</p>}
            {loadingUsers ? <p className="admin-empty" role="status">Loading users...</p> : filteredUsers.length === 0 ? (
              <p className="admin-empty">{users.length ? "No users on this page match your search." : "No signed-up users found."}</p>
            ) : (
              <div className="admin-table-wrap">
                <table className="admin-table">
                  <thead><tr><th>User</th><th>Joined</th><th>Last sign in</th><th>Status</th><th>Actions</th></tr></thead>
                  <tbody>
                    {filteredUsers.map((user) => (
                      <tr key={user.user_id}>
                        <td><strong>{user.full_name || "Learner"}</strong><span className="admin-secondary">{user.email}</span></td>
                        <td>{dateLabel(user.created_at)}</td>
                        <td>{dateLabel(user.last_sign_in_at)}</td>
                        <td><span className={suspended(user) ? "admin-status suspended" : "admin-status"}>{suspended(user) ? "Suspended" : "Active"}</span></td>
                        <td><div className="admin-row-actions">
                          <button type="button" onClick={() => void toggleProgress(user.user_id)}>{expandedUserId === user.user_id ? "Hide progress" : "Review progress"}</button>
                          <button type="button" disabled={actionUserId === user.user_id || user.user_id === authSession.user.id} onClick={() => void setSuspended(user)}>{suspended(user) ? "Reactivate" : "Suspend"}</button>
                          <button className="danger-action" type="button" disabled={actionUserId === user.user_id || user.user_id === authSession.user.id} onClick={() => void deleteAccount(user)}>Delete</button>
                        </div></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {loadingProgressId && <p className="admin-empty" role="status">Loading learning progress...</p>}
            {progressError && <p className="error-banner" role="alert">{progressError}</p>}
            {expandedUserId && userProgress[expandedUserId] && (
              <div className="admin-progress">
                <h3>Learning progress</h3>
                {userProgress[expandedUserId].sessions.length === 0 ? <p>No learning sessions recorded yet.</p> : userProgress[expandedUserId].sessions.map((item) => (
                  <article className="admin-progress-card" key={item.session_id}>
                    <div><strong>{item.profile.topic}</strong><span className="admin-secondary">{item.profile.level} · {dateLabel(item.created_at)}</span></div>
                    <span>{item.progress.attempted} attempts</span>
                    <span>{item.progress.correct} correct · {item.progress.accuracy_percent}% accuracy</span>
                    {item.progress.needs_practice.length > 0 && <span>Needs practice: {item.progress.needs_practice.join(", ")}</span>}
                  </article>
                ))}
              </div>
            )}
            <div className="admin-pagination">
              <button type="button" disabled={usersPage <= 1 || loadingUsers} onClick={() => setUsersPage((page) => page - 1)}>Previous</button>
              <span>Page {usersPage}</span>
              <button type="button" disabled={!hasMoreUsers || loadingUsers} onClick={() => setUsersPage((page) => page + 1)}>Next</button>
            </div>
          </section>
        ) : (
          <section className="admin-panel" aria-labelledby="admin-feedback-title">
            <div className="admin-panel-heading"><div><h2 id="admin-feedback-title">Learner feedback</h2><p>Selected feedback is shown anonymously on the login and signup page.</p></div></div>
            {feedbackError && <p className="error-banner" role="alert">{feedbackError}</p>}
            {loadingFeedback ? <p className="admin-empty" role="status">Loading feedback...</p> : feedbackEntries.length === 0 ? (
              <p className="admin-empty">No learner feedback has been submitted yet.</p>
            ) : (
              <div className="admin-feedback-list">
                {feedbackEntries.map((entry) => (
                  <article className="admin-feedback-item" key={entry.id}>
                    <div><p>{entry.feedback}</p><span className="admin-secondary">{dateLabel(entry.created_at)}</span></div>
                    <label className="admin-feature-toggle">
                      <input
                        type="checkbox"
                        checked={entry.is_featured}
                        disabled={updatingFeedbackId === entry.id}
                        onChange={() => void changeFeedbackVisibility(entry)}
                      />
                      <span>{updatingFeedbackId === entry.id ? "Saving..." : "Display on login page"}</span>
                    </label>
                  </article>
                ))}
              </div>
            )}
          </section>
        )}
      </main>
    </div>
  );
}
