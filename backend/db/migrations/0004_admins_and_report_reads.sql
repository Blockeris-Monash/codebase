-- The reports view needs to name who filed a report, and only the team should
-- be able to open it.
--
-- 0001 made `reports` team-visible with `auth.uid() is not null`. That reads as
-- "the team", but it actually means *any* signed-in account: sign-in is Google,
-- and nothing in the database restricts which Google accounts may sign in. It
-- was harmless while nothing read the table. A page that lists every report is
-- exactly the thing that makes it matter.
--
-- So membership becomes explicit. `admins` holds the people who may read the
-- queue, managed here rather than from the app - there is deliberately no
-- insert policy, so no signed-in session can add itself.

create table if not exists admins (
    user_id  uuid primary key references users(id) on delete cascade,
    added_at timestamptz not null default now()
);

alter table admins enable row level security;

-- A session may see whether it is an admin, and nothing else about the table.
drop policy if exists read_own_admin_row on admins;
create policy read_own_admin_row on admins for select
    using (user_id = auth.uid());

-- security definer so the check itself is not subject to the policy above,
-- which would otherwise make it true only for the row the caller can see.
create or replace function is_admin()
returns boolean language sql stable security definer set search_path = public as $$
    select exists (select 1 from admins where user_id = auth.uid());
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
