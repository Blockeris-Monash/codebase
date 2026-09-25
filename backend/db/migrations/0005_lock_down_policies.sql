-- Make the schema say what the live database already does.
--
-- 0003 creates `policies` - the company guidelines corpus the reply drafting
-- retrieves from - and never enables row-level security on it. Every other
-- table in 0001 enables it explicitly. The live project has it on because
-- somebody turned it on in the dashboard, which means the migrations no longer
-- describe the database: a fresh deploy from this folder would create the table
-- unprotected, and the publishable key is committed in `frontend/config.js`, so
-- all 74 rows would be readable by anyone who opened the page and read its
-- source.
--
-- Turning it on with no policy is the intent, not an oversight. RLS denies what
-- no policy permits, so the corpus is reachable only by the service role, which
-- bypasses RLS - and that is exactly the key `backend/reply.py` holds on the
-- server. No browser session has any business reading it.

alter table policies enable row level security;

-- match_policies runs `language sql stable` without `security definer`, so it
-- executes as the caller and is therefore subject to the policy above: an
-- anonymous caller gets nothing back rather than a silent read-through. Stated
-- here because that is load-bearing, and a later `security definer` added for
-- convenience would quietly undo this whole migration.
