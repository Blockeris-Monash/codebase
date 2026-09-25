-- A report could be filed as somebody else, or as the pipeline.
--
-- 0004 fixed reading, editing and deleting. The insert policy it shipped,
-- `with check (auth.uid() is not null)`, checks that a caller is signed in but
-- not what they write. So any signed-in account could post a row carrying
-- another person's user_id, or `kind = 'technical'`, which the admin queue
-- renders as "Automatic" with no name against it - a report that reads as
-- something the pipeline logged about itself.
--
-- The row must now name its author and say it came from a person.
--
-- Neither real writer changes. frontend/store.js already sends
-- `user_id: <the signed-in id>, kind: 'human'`. backend/reports.py writes with
-- the service role key, and row-level security does not apply to it at all, so
-- the technical reports it files are unaffected.

drop policy if exists file_a_report on reports;

create policy file_a_report on reports for insert
    with check (user_id = auth.uid() and kind = 'human');
