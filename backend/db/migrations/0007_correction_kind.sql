-- What a reviewer did to a field, not only what they typed.
--
-- 0001 made `corrections` one row per corrected field, holding `was` and
-- `corrected`. The review screen now offers three things on a field the check
-- flagged, and only one of them is a new value:
--
--   confirm   the check was right.         was/corrected: the verdict, unchanged
--   dismiss   not a real difference.       was: the verdict, corrected: 'match'
--   fix       the AI misread one document. was/corrected: the old and new reading
--   undo      one of the above taken back. was: what was undone
--
-- `side` says which document a fix was made to, so the impact query can tell
-- a misread Shipping Instruction from a misread draft Bill of Lading:
--   select field, side, count(*) from corrections where kind = 'fix' group by 1, 2
--
-- Nullable, so the rows written before this migration stay valid. The policy
-- from 0001 (a row belongs to the reviewer who owns its review) is unchanged.
--
-- Paste whole into the Supabase SQL editor. Safe to re-run.

alter table corrections add column if not exists kind text
    check (kind in ('confirm', 'dismiss', 'fix', 'undo'));

alter table corrections add column if not exists side text
    check (side in ('SI', 'BL'));
