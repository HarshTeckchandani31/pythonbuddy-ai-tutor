# PythonBuddy: Personalized Python Tutor

PythonBuddy helps beginner programmers learn Python through personalized explanations, generated practice, five-question quizzes, answer feedback, and recommendations. Learners can choose a level and one of seven topics: variables, data types and strings, conditionals, loops, lists and dictionaries, functions, or input and output.

## Requirements
- Python 3.11 or newer
- Node.js 20.19+ or 22.12+
- A Gemini API key for AI-powered lessons
- A Supabase project for email authentication and saved learner data

## Local setup
From the workspace root in PowerShell:

```powershell
Copy-Item .env.example .env
Copy-Item frontend\.env.example frontend\.env.local
```

1. Create a Supabase project. In its SQL Editor, run the latest [`supabase/schema.sql`](./supabase/schema.sql). Rerun it after updates to add features such as feedback moderation and account suspension.
2. In Supabase **Project Settings → API Keys**, copy the project URL, publishable key, and **service_role** key. The service-role key is secret; never put it in the frontend or share it.
3. In the workspace-root `.env`, set `AI_PROVIDER=gemini`, `GEMINI_API_KEY`, `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, and `SUPABASE_SERVICE_ROLE_KEY`. Set `ADMIN_EMAIL` to the exact email of your administrator account; leave it blank to disable administrator access. Set `GEMINI_MODEL=gemini-3.8-flash`.
4. In `frontend/.env.local`, set `VITE_SUPABASE_URL` and `VITE_SUPABASE_PUBLISHABLE_KEY` to the same project URL and publishable key. The publishable key is intended for browser use; database tables deny direct access to browser roles.
5. In Supabase **Authentication → URL Configuration**, set the local Site URL to `http://localhost:3000` and add it to the redirect URLs. Email/password sign-up uses Supabase email confirmation when enabled in **Authentication → Providers → Email**.

Install backend dependencies (if they are not already installed):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
```

Install frontend dependencies:

```powershell
npm --prefix frontend install
```

Build the React UI and run the complete app on one port:

```powershell
.\.venv\Scripts\Activate.ps1
npm start
```

Open http://localhost:3000. The React frontend and FastAPI `/api` routes share this origin and port. API documentation is available at http://127.0.0.1:3000/docs. For frontend-only development with hot reload, run `npm run dev:frontend` and the API separately with `npm run dev:api`; that optional workflow uses two ports. The old root-level Node prototype is no longer the recommended entry point.

## Environment variables
| Variable | Default | Purpose |
| --- | --- | --- |
| `AI_PROVIDER` | `gemini` | Provider adapter selected by the backend (`gemini` or `anthropic`) |
| `GEMINI_API_KEY` | empty | Server-side Gemini API credential |
| `GEMINI_MODEL` | `gemini-3.8-flash` | Gemini model identifier |
| `SUPABASE_URL` | empty | Supabase project URL used by the backend |
| `SUPABASE_PUBLISHABLE_KEY` | empty | Backend key used to verify Supabase user access tokens |
| `SUPABASE_SERVICE_ROLE_KEY` | empty | Server-only key for the backend's protected database operations |
| `ADMIN_EMAIL` | empty | Exact email allowlisted for the sole administrator; server-side only |
| `ANTHROPIC_API_KEY` | empty | Optional server-side Anthropic credential |
| `ANTHROPIC_MODEL` | `claude-haiku-4-5-20251001` | Anthropic model identifier |
| `AI_TIMEOUT_SECONDS` | `55` | Provider request timeout (keep below the Vercel function's 60-second maximum) |
| `MAX_REQUEST_BYTES` | `65536` | Maximum JSON request size |
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated allowed frontend origins |
| `VITE_API_BASE_URL` | `/api` | Frontend API base; set to `https://your-api.example/api` when deployed separately |
| `VITE_SUPABASE_URL` | empty | Supabase project URL for browser sign-in |
| `VITE_SUPABASE_PUBLISHABLE_KEY` | empty | Supabase publishable key for browser sign-in |

## Accounts and saved data
Email and password registration/sign-in are provided by Supabase Auth. Supabase manages account credentials and email confirmation; the app stores the account email and learner preferences in `learner_profiles`. Each learner's sessions, progress, and private answer keys are stored in `learning_sessions`. Signed-in learners can submit feedback from the bottom-of-page feedback form; feedback is stored with the authenticated account in `learner_feedback`.

The `/admin` page is sign-in only; backend access is restricted to the exact email in the server-only `ADMIN_EMAIL` variable. The dashboard can review users' progress, suspend/reactivate accounts, permanently delete learner accounts and their associated data, and select feedback for anonymous display on the signup page. Rerun `supabase/schema.sql` to add the moderation and immediate-suspension tables. All application tables have RLS enabled and deny access to `anon` and `authenticated`; only the backend uses the server-only service-role key, after verifying the user's access token. Do not expose the service-role key. Sessions created before this Supabase setup are not migrated.

## API contract
All routes are prefixed with `/api`; request and response schemas are defined in `backend/app/schemas.py`.

| Method and path | Request | Response |
| --- | --- | --- |
| `GET /health` | none | Service and AI configuration status |
| `POST /feedback` | `{feedback}` (authenticated; 1-2000 characters) | Confirmation; stored with the signed-in user's ID |
| `GET /feedback/featured` | none | Selected feedback, with no author identifiers |
| `GET /admin/me` | none (administrator only) | Confirms server-side administrator authorization |
| `GET /admin/feedback` | none (administrator only) | Feedback queue with display-selection state |
| `PATCH /admin/feedback/{id}` | `{is_featured}` (administrator only) | Select or unselect anonymous public display |
| `GET /admin/users` | `page`, `page_size` (administrator only) | Paginated Supabase Auth user directory |
| `GET /admin/users/{id}/progress` | none (administrator only) | Learning sessions and progress summary |
| `PATCH /admin/users/{id}/status` | `{suspended}` (administrator only) | Suspend or reactivate account and app access |
| `DELETE /admin/users/{id}` | none (administrator only) | Permanently deletes the account and related app data |
| `POST /sessions` | `{name, level, difficulty, topic}` | Session ID, profile, zeroed progress |
| `POST /sessions/{id}/learn` | `{topic?}` | Explanation, Python example, check question |
| `POST /sessions/{id}/doubt` | `{question}` | Answer and follow-up question |
| `POST /sessions/{id}/practice/questions` | `{}` | One question; no answer key |
| `POST /sessions/{id}/practice/answers` | `{question_id, answer}` | Feedback, answer, explanation, updated progress |
| `POST /sessions/{id}/quiz` | `{}` | First of five questions; answer keys stay server-side |
| `POST /sessions/{id}/quiz/answers` | `{question_id, answer}` | Feedback, running quiz score, next question or completion |
| `GET /sessions/{id}/progress` | none | Progress derived from accepted submissions |
| `POST /sessions/{id}/summary` | `{focus_topic?}` | Recorded progress and next-topic recommendation |

Invalid input returns `422`; unknown sessions/questions return `404`; repeated or out-of-order answers return `409`; missing credentials return `503`; provider rate limits return `429`; timeouts return `504`; invalid provider output and upstream failures return `502`.

## Checks
Run from the workspace root with `.venv` active:

```powershell
python -m pytest backend/tests -q
npm --prefix frontend test
npm --prefix frontend run build
npm audit --prefix frontend
```

The API tests use mocked provider responses; no API key is required. The React tests cover session setup, practice feedback/progress, quiz progression, and provider errors.

## Deployment
### Deploy the combined app to Vercel

The repository is configured for Vercel's FastAPI runtime. The Vercel build script installs the frontend dependencies and builds `frontend/dist`; FastAPI serves the API, while its frontend integration lets Vercel serve the built app and SPA routes.

1. Push this project to a GitHub repository and import that repository in Vercel. Set the project root to the repository root and the Framework Preset to **Other** so Vercel uses the Python entrypoint in `pyproject.toml`.
2. Add these environment variables in Vercel **Project Settings → Environment Variables**. Set them for Production and Preview environments as needed:
   - Server-only: `AI_PROVIDER=gemini`, `GEMINI_API_KEY`, `GEMINI_MODEL=gemini-3.8-flash`, `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, and `ADMIN_EMAIL` (the exact email for your Supabase administrator account).
   - Frontend build-time: `VITE_SUPABASE_URL` and `VITE_SUPABASE_PUBLISHABLE_KEY`, using the same Supabase project URL and publishable key. `VITE_API_BASE_URL` can be omitted; the default `/api` uses the same Vercel domain.
   - Never add `SUPABASE_SERVICE_ROLE_KEY` or `GEMINI_API_KEY` as `VITE_` variables. Do not commit `.env` files.
3. Redeploy after adding or changing environment variables. The frontend variables are embedded at build time, so a new deployment is needed for frontend changes to take effect.
4. In Supabase **Authentication → URL Configuration**, set the production Site URL to your Vercel domain and add that domain to the allowed redirect URLs. Run the latest [`supabase/schema.sql`](./supabase/schema.sql) in the same Supabase project's SQL Editor; rerun it after this update to add feedback moderation and account suspension support.

The Vercel API and frontend share one origin. `CORS_ORIGINS` is only needed if you separately host a frontend; for a separate frontend deployment, include its exact origin. To run locally instead, use the steps above and `npm start`.

### Deploy the backend separately

Alternatively, deploy `backend` as a Python web service with start command `python -m uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT`. Set server-side variables, including `GEMINI_API_KEY`, `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, and `SUPABASE_SERVICE_ROLE_KEY`, and configure the production frontend URL in `CORS_ORIGINS`. Build `frontend` with `npm run build` and host `frontend/dist` as a static site; set `VITE_API_BASE_URL`, `VITE_SUPABASE_URL`, and `VITE_SUPABASE_PUBLISHABLE_KEY` at build time. Add the production URL to Supabase's allowed authentication redirect URLs.

## Limitations and safety
- Supabase persists learner profiles, session progress, and quiz state across restarts. Conversation text shown in the tutor UI is not persisted.
- Answers are compared against normalized expected answers; free-form code is not executed or sandboxed. Python execution is intentionally not implemented.
- Generated content is schema-validated, but AI explanations and answer keys can still be mistaken; review generated teaching material before using it for high-stakes assessment.
- Root-level `index.html`, `app.js`, `style.css`, and `server.js` are preserved as the original prototype. The React application lives in `frontend/`, and its API is in `backend/`.
