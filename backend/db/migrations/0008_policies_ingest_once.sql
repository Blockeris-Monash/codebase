-- Loading the policy manual twice left two copies of every chunk (#147 B1).
--
-- tools/ingest_policies.py used a plain insert, so each run doubled the table and
-- retrieval's top three held the same paragraph more than once. Each row now has
-- an identity, the sha256 of its source and its text, and ingest upserts on it.
--
-- The hash below is the recipe tools/ingest_policies.py uses (content_hash), so
-- rows already loaded are recognised by the next run instead of duplicated once more.
-- Safe to run again.

alter table policies add column if not exists source text;
alter table policies add column if not exists content_hash text;

update policies set source = metadata->>'source' where source is null;

update policies
   set content_hash = encode(sha256(convert_to(coalesce(source, '') || E'\n' || content, 'UTF8')), 'hex')
 where content_hash is null;

-- The copies earlier runs left: keep the oldest row of each.
delete from policies newer
 using policies older
 where newer.content_hash = older.content_hash
   and newer.id > older.id;

create unique index if not exists policies_content_hash_key on policies (content_hash);
create index if not exists policies_source_idx on policies (source);
