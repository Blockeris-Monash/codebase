-- Ship Happens — per-user state.
--
-- What this does NOT hold: the 520 demo emails and their comparison results.
-- Those ship inside frontend/results.js so the page opens with no backend, no
-- key and no network. Putting them here would trade that for a free-tier
-- service that pauses when idle. This database holds only what a person did:
-- what they checked, what they corrected, what reply went out, what broke.
--
-- Paste whole into the Supabase SQL editor. Safe to re-run.

create extension if not exists pgcrypto;

-- ---------------------------------------------------------------- users
-- Supabase Auth owns the identity; this is our profile row beside it.
create table if not exists users (
    id           uuid primary key references auth.users(id) on delete cascade,
    email        text unique not null,
    display_name text,
    created_at   timestamptz not null default now()
);

-- Create the profile row automatically on sign-up, so no code path can forget.
create or replace function handle_new_user()
returns trigger language plpgsql security definer set search_path = public as $$
begin
    insert into users (id, email, display_name)
    values (new.id, new.email, new.raw_user_meta_data ->> 'full_name')
    on conflict (id) do nothing;
    return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
    after insert on auth.users
    for each row execute function handle_new_user();

-- ---------------------------------------------------------------- reviews
-- One row per (person, email) they have acted on.
--
-- email_ref is TEXT, not a foreign key: the 520 demo emails have no row in
-- this database and never will, so a foreign key could not be satisfied for
-- them. `source` records which world the reference belongs to.
create table if not exists reviews (
    id         uuid primary key default gen_random_uuid(),
    user_id    uuid not null references users(id) on delete cascade,
    email_ref  text not null,
    source     text not null default 'demo' check (source in ('demo', 'mailbox')),
    mark       text check (mark in ('ok', 'back')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (user_id, email_ref)
);

create index if not exists idx_reviews_user_updated on reviews (user_id, updated_at desc);

create or replace function touch_updated_at()
returns trigger language plpgsql as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists reviews_touch on reviews;
create trigger reviews_touch before update on reviews
    for each row execute function touch_updated_at();

-- ------------------------------------------------------------ corrections
-- One row per corrected field, not a JSONB blob: the impact slide needs
--   select field, count(*) from corrections group by field
-- which says WHERE the system is wrong, not merely how often.
create table if not exists corrections (
    id         uuid primary key default gen_random_uuid(),
    review_id  uuid not null references reviews(id) on delete cascade,
    field      text not null,
    was        text,
    corrected  text,
    created_at timestamptz not null default now()
);

create index if not exists idx_corrections_review on corrections (review_id);
create index if not exists idx_corrections_field  on corrections (field);

-- --------------------------------------------------------------- replies
-- Sending is a demo today. The shape does not change when it becomes real;
-- sent_at stays null until something actually goes out.
create table if not exists replies (
    id         uuid primary key default gen_random_uuid(),
    review_id  uuid not null references reviews(id) on delete cascade,
    to_address text not null,
    subject    text not null,
    body       text not null,
    sent_at    timestamptz,
    created_at timestamptz not null default now()
);

create index if not exists idx_replies_review on replies (review_id);

-- --------------------------------------------------------------- reports
-- Human reports (the Report button) and automatic ones (circuit breaker,
-- critic retry) in one table, separated by `kind`, because the admin view
-- lists both together.
create table if not exists reports (
    id         uuid primary key default gen_random_uuid(),
    user_id    uuid references users(id) on delete set null,  -- null when automatic
    kind       text not null check (kind in ('human', 'technical')),
    email_ref  text,
    title      text not null,
    detail     text,
    rating     int check (rating between 1 and 5),
    context    jsonb,
    created_at timestamptz not null default now()
);

create index if not exists idx_reports_kind_created on reports (kind, created_at desc);

-- ---------------------------------------------------------------- emails
-- Only used once the live mailbox lands. gmail_message_id UNIQUE is the
-- idempotency backstop: ingestion is at-least-once, so without it a retried
-- webhook silently doubles every email.
create table if not exists emails (
    id               uuid primary key default gen_random_uuid(),
    user_id          uuid not null references users(id) on delete cascade,
    gmail_message_id text unique not null,
    gmail_thread_id  text,
    subject          text,
    sender_email     text,
    received_at      timestamptz,
    created_at       timestamptz not null default now()
);

create index if not exists idx_emails_user_received on emails (user_id, received_at desc);

-- ------------------------------------------------------------------- RLS
-- The anon key is public by design. Row-level security is the only thing
-- standing between a leaked key and everyone's data, so every policy needs
-- BOTH `using` (which rows are visible) and `with check` (which rows may be
-- written). A policy with `using` alone silently rejects every insert.
alter table users       enable row level security;
alter table reviews     enable row level security;
alter table corrections enable row level security;
alter table replies     enable row level security;
alter table reports     enable row level security;
alter table emails      enable row level security;

drop policy if exists own_profile on users;
create policy own_profile on users for all
    using (id = auth.uid()) with check (id = auth.uid());

drop policy if exists own_reviews on reviews;
create policy own_reviews on reviews for all
    using (user_id = auth.uid()) with check (user_id = auth.uid());

drop policy if exists own_emails on emails;
create policy own_emails on emails for all
    using (user_id = auth.uid()) with check (user_id = auth.uid());

-- Children are reached through their parent review, so ownership is inherited.
drop policy if exists own_corrections on corrections;
create policy own_corrections on corrections for all
    using (exists (select 1 from reviews r
                   where r.id = corrections.review_id and r.user_id = auth.uid()))
    with check (exists (select 1 from reviews r
                        where r.id = corrections.review_id and r.user_id = auth.uid()));

drop policy if exists own_replies on replies;
create policy own_replies on replies for all
    using (exists (select 1 from reviews r
                   where r.id = replies.review_id and r.user_id = auth.uid()))
    with check (exists (select 1 from reviews r
                        where r.id = replies.review_id and r.user_id = auth.uid()));

-- Reports are team-visible on purpose: the admin view lists everyone's, and a
-- technical report has no user_id at all, so owner-only reads would hide the
-- automatic ones from the page that exists to show them.
drop policy if exists team_reports on reports;
create policy team_reports on reports for all
    using (auth.uid() is not null) with check (auth.uid() is not null);
