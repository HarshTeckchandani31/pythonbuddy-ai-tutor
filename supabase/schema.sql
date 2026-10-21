create table if not exists public.learner_profiles (
    user_id uuid primary key references auth.users (id) on delete cascade,
    email text not null,
    full_name text not null default '',
    level text not null check (level in ('beginner', 'intermediate', 'advanced')),
    difficulty text not null check (difficulty in ('beginner', 'intermediate', 'advanced')),
    topic text not null,
    updated_at timestamptz not null default now()
);

create table if not exists public.learning_sessions (
    id uuid primary key,
    user_id uuid not null references auth.users (id) on delete cascade,
    profile jsonb not null,
    attempts jsonb not null default '[]'::jsonb,
    practice_questions jsonb not null default '{}'::jsonb,
    answered_practice_ids jsonb not null default '[]'::jsonb,
    quiz jsonb not null default '[]'::jsonb,
    quiz_cursor integer not null default 0 check (quiz_cursor >= 0),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists learning_sessions_user_created_idx
    on public.learning_sessions (user_id, created_at desc);

alter table public.learner_profiles enable row level security;
alter table public.learning_sessions enable row level security;

revoke all on table public.learner_profiles from anon, authenticated;
revoke all on table public.learning_sessions from anon, authenticated;
grant all on table public.learner_profiles to service_role;
grant all on table public.learning_sessions to service_role;
