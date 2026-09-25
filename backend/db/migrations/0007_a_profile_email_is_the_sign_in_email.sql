-- A profile's email is the one the person signed in with, and cannot be set to anyone else's.
--
-- 0004 let a signed-in user update their own `users` row freely, email included, and
-- `users.email` is unique. So anyone could set their profile email to someone else's
-- address. That person's first Google sign-in then hit a unique violation inside
-- `handle_new_user`, a trigger on `auth.users`, and failed: nothing on the page could
-- recover it. Insert had the same hole, after deleting one's own row (#147 A2).
--
-- 1. Insert and update must leave `email` equal to the email in the caller's JWT.
-- 2. The trigger ignores any conflict, not only one on `id`, so a sign-up never fails
--    on a profile row, whatever state the table is in.
-- 3. Any profile already pointing at an address that is not its owner's is put back.
--
-- Run once in the Supabase SQL editor. Safe to run again.

drop policy if exists own_profile_insert on users;
create policy own_profile_insert on users for insert
    with check (id = auth.uid()
                and lower(email) = lower(coalesce(auth.jwt() ->> 'email', '')));

drop policy if exists own_profile_update on users;
create policy own_profile_update on users for update
    using (id = auth.uid())
    with check (id = auth.uid()
                and lower(email) = lower(coalesce(auth.jwt() ->> 'email', '')));

create or replace function handle_new_user()
returns trigger language plpgsql security definer set search_path = public as $$
begin
    insert into users (id, email, display_name)
    values (new.id, new.email, new.raw_user_meta_data ->> 'full_name')
    on conflict do nothing;
    return new;
end;
$$;

update users u
   set email = a.email
  from auth.users a
 where u.id = a.id
   and lower(u.email) is distinct from lower(a.email);
