-- The reports view needs to name who filed a report, and only the team should
-- be able to open it.
--
-- 0001 made `reports` team-visible with `auth.uid() is not null`. That reads as
-- "the team", but it actually means *any* signed-in account: sign-in is Google,
-- and nothing in the database restricts which Google accounts may sign in. It
-- was harmless while nothing read the table. A page that lists every report is
-- exactly the thing that makes it matter.
--
-- Membership is therefore explicit, and keyed on **email, not user id**. A row
-- in `users` only exists after someone has signed in once, so a table keyed on
-- user_id cannot grant access to a teammate who has not signed in yet - they
-- would be silently excluded, and the fix would be invisible until they
-- complained. Email is what the team is identified by anyway.
--
-- Membership itself is data, not schema, so the inserts are deliberately not in
-- this file: addresses do not belong in a repository that may be made public.

create table if not exists admins (
    email    text primary key,
    added_at timestamptz not null default now()
);

alter table admins enable row level security;

-- A session may see its own membership and nothing else about the table. There
-- is deliberately no insert, update or delete policy: RLS denies what no policy
-- permits, so no signed-in session can add itself or anybody else.
drop policy if exists read_own_admin_row on admins;
create policy read_own_admin_row on admins for select
    using (lower(email) = lower(coalesce(auth.jwt() ->> 'email', '')));

-- security definer so the check is not itself subject to the policy above,
-- which would otherwise make it answerable only for the row the caller can see.
-- Compared case-insensitively: Google addresses are, and a capital letter
-- pasted into the seed should not quietly remove someone's access.
create or replace function is_admin()
returns boolean language sql stable security definer set search_path = public as $$
    select exists (
        select 1 from admins
        where lower(email) = lower(coalesce(auth.jwt() ->> 'email', ''))
    );
$$;

-- ---------------------------------------------------------------- users
-- Reads widen to admins so a report can carry a name instead of a raw uuid.
-- Writes stay owner-only, which is why the single FOR ALL policy has to be
-- split: one policy cannot widen `select` without widening `insert`, `update`
-- and `delete` along with it.
drop policy if exists own_profile on users;

create policy read_profiles on users for select
    using (id = auth.uid() or is_admin());

create policy own_profile_insert on users for insert
    with check (id = auth.uid());

create policy own_profile_update on users for update
    using (id = auth.uid()) with check (id = auth.uid());

create policy own_profile_delete on users for delete
    using (id = auth.uid());

-- ---------------------------------------------------------------- reports
-- Anyone signed in may still file one, and may read their own back. Reading
-- everybody's is what the admin list does, and that now requires membership.
-- A technical report has no user_id at all, so only an admin ever sees those.
drop policy if exists team_reports on reports;

create policy file_a_report on reports for insert
    with check (auth.uid() is not null);

create policy read_reports on reports for select
    using (user_id = auth.uid() or is_admin());

create policy admins_update_reports on reports for update
    using (is_admin()) with check (is_admin());

create policy admins_delete_reports on reports for delete
    using (is_admin());
