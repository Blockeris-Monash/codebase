-- reports.user_id is a foreign key with no index on it.
--
-- 0001 indexed reports on (kind, created_at) for the admin view and stopped
-- there. That leaves `on delete set null` scanning the whole table whenever a
-- user is removed, and any "my reports" read doing the same.
--
-- A separate migration rather than an edit to 0001, because 0001 is already
-- applied: a schema that is live is appended to, not rewritten.
create index if not exists idx_reports_user_created
    on reports (user_id, created_at desc);
