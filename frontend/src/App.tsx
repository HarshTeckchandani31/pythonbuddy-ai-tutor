import { useEffect, useState, type FormEvent } from "react";
import ReactMarkdown from "react-markdown";
import {
  ArrowRight,
  ArrowUp,
  BookOpen,
  Braces,
  Check,
  CircleHelp,
  Code2,
  LoaderCircle,
  RotateCcw,
  Sparkles,
  Target,
  X,
  Zap,
} from "lucide-react";
import { tutorApi } from "./api";
import { authApi, supabaseConfigured, type AuthSession } from "./auth";
import type {
  DoubtContent,
  LearnerLevel,
  LearnerProfile,
  LearnerSession,
  LearningMode,
  LessonContent,
  Progress,
  QuizAnswer,
  SessionSummary,
  TutorQuestion,
} from "./types";

const TOPICS = [
  "Python variables",
  "Data types and strings",
  "Conditionals",
  "For and while loops",
  "Lists and dictionaries",
  "Functions",
  "Input and output",
];

const MODES: { id: LearningMode; label: string; icon: typeof BookOpen; description: string }[] = [
  { id: "learn", label: "Learn", icon: BookOpen, description: "Understand a concept" },
  { id: "practice", label: "Practice", icon: Code2, description: "Try a coding question" },
  { id: "quiz", label: "Quiz", icon: Target, description: "Test what you know" },
  { id: "doubt", label: "Ask a doubt", icon: CircleHelp, description: "Get help with a question" },
];

type Message = { id: string; role: "assistant" | "learner"; content: string; tone?: "correct" | "incorrect" };

function makeMessage(role: Message["role"], content: string, tone?: Message["tone"]): Message {
  return { id: crypto.randomUUID(), role, content, tone };
}

function lessonText(lesson: LessonContent): string {
  return `${lesson.explanation}\n\n${lesson.example}\n\n**Quick check:** ${lesson.check_question}`;
}

function answerText(answer: { correct: boolean; feedback: string; correct_answer: string; explanation: string; hint?: string }): string {
  const hint = !answer.correct && answer.hint ? `\n\n**Hint:** ${answer.hint}` : "";
  return `**${answer.feedback}**\n\n${answer.explanation}${hint}\n\n**Answer:**\n\n\`${answer.correct_answer}\``;
}

function App() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [authMode, setAuthMode] = useState<"signin" | "signup">("signup");
  const [authSession, setAuthSession] = useState<AuthSession | null>(null);
  const [authReady, setAuthReady] = useState(false);
  const [authNotice, setAuthNotice] = useState("");
  const [level, setLevel] = useState<LearnerLevel>("beginner");
  const [difficulty, setDifficulty] = useState<LearnerLevel>("beginner");
  const [topic, setTopic] = useState(TOPICS[0]);
  const [session, setSession] = useState<LearnerSession | null>(null);
  const [mode, setMode] = useState<LearningMode>("learn");
  const [messages, setMessages] = useState<Message[]>([]);
  const [activeQuestion, setActiveQuestion] = useState<TutorQuestion | null>(null);
  const [answer, setAnswer] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [summary, setSummary] = useState<SessionSummary | null>(null);
  const [quizResult, setQuizResult] = useState<QuizAnswer | null>(null);
  const [feedback, setFeedback] = useState("");
  const [feedbackNotice, setFeedbackNotice] = useState("");
  const [feedbackError, setFeedbackError] = useState("");
  const [submittingFeedback, setSubmittingFeedback] = useState(false);

  const addMessage = (message: Message) => setMessages((current) => [...current, message]);

  useEffect(() => {
    if (!supabaseConfigured) {
      setAuthReady(true);
      return;
    }
    let active = true;
    const unsubscribe = authApi.onAuthStateChange((nextSession) => {
      if (active) {
        setAuthSession(nextSession);
        setAuthReady(true);
      }
    });
    void authApi.getSession()
      .then((currentSession) => {
        if (active) setAuthSession(currentSession);
      })
      .catch((cause: unknown) => {
        if (active) setError(cause instanceof Error ? cause.message : "Could not restore your sign-in.");
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
      setSession(null);
      setMessages([]);
      return;
    }
    let active = true;
    setName(
      typeof authSession.user.user_metadata.full_name === "string"
        ? authSession.user.user_metadata.full_name
        : "",
    );
    setLoading(true);
    void tutorApi.getLatestSession()
      .then((latest) => {
        if (active && latest) {
          setSession(latest);
          setName(latest.profile.name);
          setMode("learn");
          setMessages([
            makeMessage(
              "assistant",
              `Welcome back. Your last session was ${latest.profile.topic.toLowerCase()}. Your saved progress is restored.`,
            ),
          ]);
        }
      })
      .catch((cause: unknown) => {
        if (active) setError(cause instanceof Error ? cause.message : "Could not load your saved session.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [authSession?.user.id]);

  const authenticate = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLoading(true);
    setError("");
    setAuthNotice("");
    try {
      if (authMode === "signup") {
        const createdSession = await authApi.signUp(email.trim(), password, name.trim());
        if (createdSession) {
          setAuthSession(createdSession);
        } else {
          setAuthNotice("Check your email for a confirmation link, then sign in.");
          setAuthMode("signin");
        }
      } else {
        setAuthSession(await authApi.signIn(email.trim(), password));
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Authentication failed. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const signOut = async () => {
    setError("");
    try {
      await authApi.signOut();
      setAuthSession(null);
      setEmail("");
      setPassword("");
      setAuthNotice("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not sign out.");
    }
  };

  const beginSession = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLoading(true);
    setError("");
    const profile: LearnerProfile = { name: name.trim() || "Learner", level, difficulty, topic };
    try {
      const created = await tutorApi.createSession(profile);
      setSession(created);
      setMessages([makeMessage("assistant", `Welcome, ${created.profile.name}. We’ll take ${created.profile.topic.toLowerCase()} one step at a time.`)]);
      await loadMode("learn", created);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not create your learning session.");
    } finally {
      setLoading(false);
    }
  };

  const loadMode = async (nextMode: LearningMode, activeSession = session) => {
    if (!activeSession) return;
    setMode(nextMode);
    setLoading(true);
    setError("");
    setSummary(null);
    setQuizResult(null);
    setActiveQuestion(null);
    setMessages((current) => [...current, makeMessage("assistant", `${MODES.find((item) => item.id === nextMode)?.label} mode`)]);
    try {
      if (nextMode === "learn") {
        const lesson = await tutorApi.learn(activeSession.session_id, activeSession.profile.topic);
        addMessage(makeMessage("assistant", lessonText(lesson)));
      } else if (nextMode === "practice") {
        const question = await tutorApi.createPracticeQuestion(activeSession.session_id);
        setActiveQuestion(question);
        addMessage(makeMessage("assistant", `**Try this:**\n\n${question.question}`));
      } else if (nextMode === "quiz") {
        const question = await tutorApi.startQuiz(activeSession.session_id);
        setActiveQuestion(question);
        addMessage(makeMessage("assistant", `**Question 1 of 5**\n\n${question.question}`));
      } else {
        addMessage(makeMessage("assistant", "What would you like to untangle? Ask me a Python question."));
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The tutor could not load this mode.");
    } finally {
      setLoading(false);
    }
  };

  const refreshProgress = async (sessionId: string) => {
    const progress = await tutorApi.getProgress(sessionId);
    setSession((current) => current ? { ...current, progress } : current);
  };

  const submitAnswer = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const value = answer.trim();
    if (!value || !session || loading) return;
    setAnswer("");
    setError("");
    addMessage(makeMessage("learner", value));
    setLoading(true);
    try {
      if ((mode === "practice" || mode === "quiz") && activeQuestion) {
        if (mode === "practice") {
          const result = await tutorApi.submitPracticeAnswer(session.session_id, activeQuestion.question_id, value);
          setSession((current) => current ? { ...current, progress: result.progress } : current);
          setActiveQuestion(null);
          addMessage(makeMessage("assistant", answerText(result), result.correct ? "correct" : "incorrect"));
        } else {
          const result = await tutorApi.submitQuizAnswer(session.session_id, activeQuestion.question_id, value);
          setQuizResult(result);
          setActiveQuestion(result.next_question);
          await refreshProgress(session.session_id);
          const questionLabel = result.complete ? `**Quiz complete: ${result.score}/5**` : `**Question ${result.answered + 1} of 5**`;
          addMessage(makeMessage("assistant", `${answerText(result)}\n\n${questionLabel}${result.next_question ? `\n\n${result.next_question.question}` : ""}`, result.correct ? "correct" : "incorrect"));
        }
      } else {
        const response: DoubtContent = await tutorApi.askDoubt(session.session_id, value);
        addMessage(makeMessage("assistant", `${response.answer}\n\n**Think about this:** ${response.follow_up_question}`));
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Your answer could not be checked.");
    } finally {
      setLoading(false);
    }
  };

  const askDoubt = async (question: string) => {
    if (!session || loading) return;
    addMessage(makeMessage("learner", question));
    setLoading(true);
    setError("");
    try {
      const response = await tutorApi.askDoubt(session.session_id, question);
      addMessage(makeMessage("assistant", `${response.answer}\n\n**Think about this:** ${response.follow_up_question}`));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The tutor could not answer that just now.");
    } finally {
      setLoading(false);
    }
  };

  const createAnotherPractice = async () => {
    if (!session || loading) return;
    setLoading(true);
    setError("");
    try {
      const question = await tutorApi.createPracticeQuestion(session.session_id);
      setActiveQuestion(question);
      addMessage(makeMessage("assistant", `**Try another:**\n\n${question.question}`));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "A new question could not be created.");
    } finally {
      setLoading(false);
    }
  };

  const finishSession = async () => {
    if (!session || loading) return;
    setLoading(true);
    setError("");
    try {
      const report = await tutorApi.getSummary(session.session_id);
      setSummary(report);
      addMessage(makeMessage("assistant", `**Your session so far**\n\n${report.recommendation}\n\n**Recommended next:** ${report.next_topic}`));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Your summary could not be created.");
    } finally {
      setLoading(false);
    }
  };

  const sendFeedback = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const value = feedback.trim();
    if (!value || submittingFeedback) return;
    setSubmittingFeedback(true);
    setFeedbackError("");
    setFeedbackNotice("");
    try {
      const result = await tutorApi.submitFeedback(value);
      setFeedback("");
      setFeedbackNotice(result.message);
    } catch (cause) {
      setFeedbackError(cause instanceof Error ? cause.message : "Your feedback could not be sent.");
    } finally {
      setSubmittingFeedback(false);
    }
  };

  const progress: Progress = session?.progress ?? {
    attempted: 0,
    correct: 0,
    accuracy_percent: 0,
    strengths: [],
    needs_practice: [],
  };

  if (!authReady) {
    return <main className="auth-status" role="status">Checking your sign-in...</main>;
  }

  return (
    <div className="app-shell">
      <header className="topbar wrap">
        <a className="brand" href="#top" aria-label="PythonBuddy home">
          <span className="brand-mark"><Braces size={17} strokeWidth={2.4} /></span>
          <span>python<span className="brand-light">buddy</span></span>
        </a>
        {authSession ? (
          <div className="auth-user-actions">
            <span>{authSession.user.email}</span>
            <button type="button" onClick={() => void signOut()}>Sign out</button>
          </div>
        ) : (
          <div className="top-note"><span className="live-dot" /> BEGINNER PYTHON STUDIO</div>
        )}
      </header>

      {!authSession ? (
        <main id="top" className="setup-shell wrap">
          <section className="setup-copy">
            <div className="eyebrow"><span className="eyebrow-line" /> YOUR LEARNING SPACE</div>
            <h1>Python that<br />finally <em>clicks.</em></h1>
            <p className="intro">Create an account to save your learner profile and progress across visits.</p>
            <div className="promise-row"><span className="promise-icon">01</span><span>Your lessons stay with your account.</span></div>
            <div className="promise-row"><span className="promise-icon">02</span><span>Sign in anywhere to pick up again.</span></div>
          </section>
          <form className="setup-form" onSubmit={(event) => void authenticate(event)}>
            <div className="form-heading"><span className="step-label">ACCOUNT</span><span className="step-number">SUPABASE AUTH</span></div>
            <h2>{authMode === "signup" ? "Create your account." : "Welcome back."}</h2>
            <p className="form-sub">Use your email and password to save your learning progress.</p>
            {authMode === "signup" && (
              <>
                <label htmlFor="account-name">Your name</label>
                <input id="account-name" value={name} onChange={(event) => setName(event.target.value)} placeholder="Your first name" maxLength={40} autoComplete="name" />
              </>
            )}
            <label htmlFor="account-email">Email</label>
            <input id="account-email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@example.com" autoComplete="email" required />
            <label htmlFor="account-password">Password</label>
            <input id="account-password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="At least 8 characters" minLength={8} autoComplete={authMode === "signup" ? "new-password" : "current-password"} required />
            {authNotice && <p className="auth-notice" role="status">{authNotice}</p>}
            {!supabaseConfigured && <p className="error-banner" role="alert">To enable account registration, add <code>VITE_SUPABASE_URL</code> and <code>VITE_SUPABASE_PUBLISHABLE_KEY</code> to <code>frontend/.env.local</code>, then rebuild the app.</p>}
            {error && <p className="error-banner" role="alert">{error}</p>}
            <button className="primary-button start-button" disabled={loading} type="submit">
              <span>{loading ? "Please wait..." : authMode === "signup" ? "Create account" : "Sign in"}</span>
              {loading ? <LoaderCircle className="spin" size={18} /> : <ArrowRight size={19} />}
            </button>
            <button className="auth-switch" type="button" disabled={loading} onClick={() => { setAuthMode(authMode === "signup" ? "signin" : "signup"); setError(""); setAuthNotice(""); }}>
              {authMode === "signup" ? "Already have an account? Sign in" : "New here? Create an account"}
            </button>
          </form>
        </main>
      ) : !session ? (
        <main id="top" className="setup-shell wrap">
          <section className="setup-copy">
            <div className="eyebrow"><span className="eyebrow-line" /> A LITTLE HELP GOES A LONG WAY</div>
            <h1>Python that<br />finally <em>clicks.</em></h1>
            <p className="intro">A patient coding tutor that meets you where you are, works through the tricky bits, and helps you build confidence one small program at a time.</p>
            <div className="promise-row"><span className="promise-icon">01</span><span>Small snippets. Real understanding.</span></div>
            <div className="promise-row"><span className="promise-icon">02</span><span>Practice that adapts to you.</span></div>
          </section>
          <form className="setup-form" onSubmit={beginSession}>
            <div className="form-heading"><span className="step-label">YOUR LEARNING SPACE</span><span className="step-number">01 / 01</span></div>
            <h2>Let’s make this yours.</h2>
            <p className="form-sub">Choose a starting point and we’ll shape the lesson around it.</p>
            <label htmlFor="learner-name">What should we call you?</label>
            <input id="learner-name" value={name} onChange={(event) => setName(event.target.value)} placeholder="Your first name" maxLength={40} autoComplete="given-name" />
            <div className="form-pair">
              <div><label htmlFor="level">Your starting point</label><select id="level" value={level} onChange={(event) => setLevel(event.target.value as LearnerLevel)}><option value="beginner">I’m new to coding</option><option value="intermediate">I’ve tried a little Python</option><option value="advanced">I can write small programs</option></select></div>
              <div><label htmlFor="difficulty">Challenge level</label><select id="difficulty" value={difficulty} onChange={(event) => setDifficulty(event.target.value as LearnerLevel)}><option value="beginner">Beginner</option><option value="intermediate">Intermediate</option><option value="advanced">Advanced</option></select></div>
            </div>
            <label htmlFor="topic">What are we learning?</label>
            <select id="topic" value={topic} onChange={(event) => setTopic(event.target.value)}>{TOPICS.map((item) => <option key={item}>{item}</option>)}</select>
            {error && <p className="error-banner" role="alert">{error}</p>}
            <button className="primary-button start-button" disabled={loading} type="submit"><span>{loading ? "Opening your session..." : "Start my lesson"}</span>{loading ? <LoaderCircle className="spin" size={18} /> : <ArrowRight size={19} />}</button>
            <div className="privacy-note"><span>●</span> Progress stays in this session.</div>
          </form>
        </main>
      ) : (
        <main className="workspace wrap">
          <section className="lesson-head">
            <div><div className="eyebrow"><span className="eyebrow-line" /> YOUR LEARNING SPACE</div><h1>Let’s work on {session.profile.topic.toLowerCase()}.</h1><p>{session.profile.level} learner <span>·</span> {session.profile.difficulty} challenge</p></div>
            <div className="learner-pill"><span className="avatar">{session.profile.name.charAt(0).toUpperCase()}</span><span>{session.profile.name}</span></div>
          </section>
          <div className="workspace-grid">
            <section className="lesson-panel" aria-label="Python tutor">
              <div className="modebar"><span className="mode-label">CHOOSE A MODE</span><div className="mode-tabs" role="tablist" aria-label="Learning mode">{MODES.map(({ id, label, icon: Icon }) => <button key={id} type="button" role="tab" aria-selected={mode === id} className={mode === id ? "active" : ""} onClick={() => void loadMode(id)} disabled={loading}><Icon size={15} /><span>{label}</span></button>)}</div></div>
              <div className="chat-topline"><span><span className="live-dot" /> YOUR TUTOR IS HERE</span><span>{mode.toUpperCase()} MODE</span></div>
              <div className="conversation" aria-live="polite" aria-label="Tutor conversation">
                {messages.map((message) => <article key={message.id} className={`message ${message.role === "learner" ? "learner-message" : "tutor-message"} ${message.tone ?? ""}`}>
                  {message.role === "assistant" && <span className="message-icon"><Sparkles size={13} /></span>}
                  <div className="message-content"><ReactMarkdown>{message.content}</ReactMarkdown></div>
                  {message.tone === "correct" && <Check className="result-icon" size={16} aria-label="Correct" />}
                  {message.tone === "incorrect" && <X className="result-icon" size={16} aria-label="Needs another try" />}
                </article>)}
                {loading && <div className="loading-line" role="status"><LoaderCircle className="spin" size={15} /> Your tutor is thinking...</div>}
                {activeQuestion && mode === "practice" && <button className="text-action" type="button" onClick={() => void askDoubt(activeQuestion.question)} disabled={loading}><Zap size={14} /> Ask for help with this question</button>}
              </div>
              {mode === "practice" && !activeQuestion && progress.attempted > 0 && <div className="action-row"><button className="outline-button" onClick={() => void createAnotherPractice()} disabled={loading}><RotateIcon /> Try another question</button></div>}
              {mode === "quiz" && quizResult?.complete && <div className="quiz-finish"><Check size={16} /> Quiz complete: {quizResult.score} / 5</div>}
              {error && <div className="error-inline" role="alert">{error}</div>}
              {mode !== "learn" && mode !== "doubt" && !activeQuestion ? <div className="input-hint">{mode === "quiz" ? "Start a quiz to get your first question." : "Get a question to begin practicing."}</div> : null}
              <form className="composer" onSubmit={submitAnswer}>
                <input value={answer} onChange={(event) => setAnswer(event.target.value)} placeholder={activeQuestion ? "Type your answer here..." : mode === "learn" || mode === "doubt" ? "Ask a Python question..." : "Your answer will appear here..."} aria-label="Your message" maxLength={3000} disabled={loading || ((mode === "practice" || mode === "quiz") && !activeQuestion)} />
                <button type="submit" className="primary-button send-button" aria-label="Send answer" disabled={loading || !answer.trim()}>{loading ? <LoaderCircle className="spin" size={16} /> : <><span>Send</span><ArrowUp size={16} /></>}</button>
              </form>
              <div className="quick-prompts">{mode === "learn" && <><button onClick={() => void askDoubt("Can you explain this topic more simply?")} disabled={loading}>Explain it more simply</button><button onClick={() => void loadMode("practice")} disabled={loading}>Give me a practice task</button></>}{mode === "practice" && <><button onClick={() => void createAnotherPractice()} disabled={loading}>Another question</button><button onClick={() => void loadMode("learn")} disabled={loading}>Review this topic</button></>}{mode === "quiz" && !activeQuestion && !quizResult?.complete && <button onClick={() => void loadMode("quiz")} disabled={loading}>Start the five-question quiz</button>}{mode === "doubt" && <><button onClick={() => void askDoubt("What is a Python variable?")} disabled={loading}>What is a variable?</button><button onClick={() => void askDoubt("How does a for loop work?")} disabled={loading}>How does a for loop work?</button></>}</div>
            </section>
            <aside className="progress-panel">
              <div className="panel-kicker">YOUR PROGRESS <Sparkles size={15} /></div>
              <div className="score-row"><div><strong>{progress.correct}<span> / {progress.attempted}</span></strong><small>correct answers</small></div><div className="score-ring"><span>{progress.attempted ? progress.accuracy_percent : "--"}</span><small>%</small></div></div>
              <div className="progress-track" role="progressbar" aria-label="Correct answer rate" aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress.accuracy_percent}><span style={{ width: `${progress.accuracy_percent}%` }} /></div>
              <div className="progress-caption"><span>Session accuracy</span><span>{progress.attempted} {progress.attempted === 1 ? "attempt" : "attempts"}</span></div>
              <SkillList title="Getting confident" items={progress.strengths} tone="strong" />
              <SkillList title="Worth another look" items={progress.needs_practice} tone="needs" />
              {summary && <div className="recommendation"><span>NEXT STEP</span><p>{summary.next_topic}</p><small>{summary.recommendation}</small></div>}
              {!summary && <div className="recommendation"><span>NEXT STEP</span><p>Your next step takes shape as you practice.</p></div>}
              <button className="finish-button" onClick={() => void finishSession()} disabled={loading}><span>{summary ? "Refresh summary" : "Finish session"}</span><ArrowRight size={16} /></button>
            </aside>
          </div>
          <footer className="app-footer"><span>PYTHON, ONE SMALL WIN AT A TIME.</span><span>PYTHON BASICS</span></footer>
        </main>
      )}
      {authSession && (
        <section className="feedback-section wrap" aria-labelledby="feedback-title">
          <div className="feedback-copy">
            <div className="eyebrow"><span className="eyebrow-line" /> HELP US IMPROVE</div>
            <h2 id="feedback-title">Share your feedback.</h2>
            <p>Your comments help us make PythonBuddy better for learners.</p>
          </div>
          <form className="feedback-form" onSubmit={(event) => void sendFeedback(event)}>
            <label htmlFor="learner-feedback">What’s working well, or what could be better?</label>
            <textarea
              id="learner-feedback"
              value={feedback}
              onChange={(event) => setFeedback(event.target.value)}
              placeholder="Share a suggestion or tell us about your experience..."
              maxLength={2000}
              rows={4}
              required
              disabled={submittingFeedback}
            />
            {feedbackError && <p className="error-banner" role="alert">{feedbackError}</p>}
            {feedbackNotice && <p className="auth-notice" role="status">{feedbackNotice}</p>}
            <button className="primary-button feedback-submit" type="submit" disabled={submittingFeedback || !feedback.trim()}>
              {submittingFeedback ? "Sending..." : "Send feedback"}
            </button>
          </form>
        </section>
      )}
    </div>
  );
}

function SkillList({ title, items, tone }: { title: string; items: string[]; tone: "strong" | "needs" }) {
  return <div className="skill-section"><span className="skill-title"><i className={`skill-dot ${tone}`} />{title}</span>{items.length ? <ul>{items.map((item) => <li key={item}>{item}</li>)}</ul> : <p className="empty-skill">Not enough attempts yet</p>}</div>;
}

function RotateIcon() {
  return <RotateCcw size={15} aria-hidden="true" />;
}

export default App;
