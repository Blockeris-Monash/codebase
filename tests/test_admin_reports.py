"""The reports queue, and the row-level security it leans on.

The page is a list. The part worth testing is what stops it being readable by
whoever asks: the gate is the `admins` table and the policies in migration
0004, never the page, because anyone can open the page and read its source.

These are static checks - the live database is not reachable from CI, and would
not be a unit test if it were. They hold the shape of the SQL and the shape of
the calls, so the two cannot drift apart silently.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADMIN = (ROOT / "frontend" / "admin.html").read_text(encoding="utf-8")
STORE = (ROOT / "frontend" / "store.js").read_text(encoding="utf-8")
MIGRATION = (ROOT / "backend" / "db" / "migrations"
             / "0004_admins_and_report_reads.sql").read_text(encoding="utf-8")


def test_nothing_can_add_itself_to_the_admins_table() -> None:
    """Membership is the whole gate. An insert policy on `admins` would let any
    signed-in session grant itself the queue, so there deliberately is none -
    RLS denies what no policy permits."""
    assert "alter table admins enable row level security" in MIGRATION
    assert not re.search(r"create policy \w+ on admins for (insert|update|delete|all)", MIGRATION)


def test_membership_is_keyed_on_email_not_user_id() -> None:
    """A `users` row only exists after a first sign-in, so keying on user_id
    cannot grant access to a teammate who has not signed in yet - they would be
    excluded with nothing on screen to say why."""
    assert re.search(r"create table if not exists admins\s*\(\s*email\s+text primary key", MIGRATION)
    assert "auth.jwt() ->> 'email'" in MIGRATION
    sql = "\n".join(line for line in MIGRATION.splitlines() if not line.lstrip().startswith("--"))
    assert "user_id" not in sql.split("create policy read_profiles")[0]


def test_the_email_comparison_ignores_case() -> None:
    """Google addresses are case-insensitive. A capital letter pasted into the
    seed must not quietly remove someone's access."""
    check = MIGRATION[MIGRATION.index("create or replace function is_admin"):]
    assert check.count("lower(") >= 2


def test_no_addresses_are_committed() -> None:
    """Membership is data, not schema. The migration creates the table; who is
    in it is pasted into the SQL editor, because a repository that may be made
    public is no place for the team's personal addresses."""
    assert "@" not in MIGRATION
    assert "insert into admins" not in MIGRATION.lower()


def test_the_admin_check_runs_as_definer() -> None:
    """is_admin() reads `admins`, which is itself behind RLS. Without
    `security definer` the function would only ever see the caller's own row,
    which happens to give the right answer for the caller and the wrong one
    everywhere else it is used."""
    function = MIGRATION[MIGRATION.index("create or replace function is_admin"):]
    assert "security definer" in function.split("$$")[0]
    assert "set search_path = public" in function.split("$$")[0]


def test_widening_reads_did_not_widen_writes() -> None:
    """`own_profile` was one FOR ALL policy. Reads had to widen to admins so a
    report can show a name; a single policy cannot do that without also letting
    an admin rewrite other people's profiles, so it is split."""
    assert "drop policy if exists own_profile on users" in MIGRATION
    assert "create policy read_profiles on users for select" in MIGRATION
    for verb in ("insert", "update", "delete"):
        assert f"on users for {verb}" in MIGRATION, verb
    assert "id = auth.uid()" in MIGRATION


def test_reports_are_no_longer_readable_by_anyone_signed_in() -> None:
    """0001 shipped `using (auth.uid() is not null)`, which reads as "the team"
    but means any Google account that can sign in at all. Filing stays open;
    reading everybody's is what needs membership."""
    assert "drop policy if exists team_reports on reports" in MIGRATION
    assert "create policy file_a_report on reports for insert" in MIGRATION

    read = re.search(r"create policy read_reports on reports for select(.*?);", MIGRATION, re.S)
    assert read, "no select policy on reports"
    assert "is_admin()" in read.group(1)
    assert "auth.uid() is not null" not in read.group(1)


def test_the_page_tells_an_empty_queue_apart_from_a_failed_one() -> None:
    """listReports returns null on failure and [] when there is nothing, because
    "no reports" and "the database did not answer" must not look the same on a
    page whose whole job is to show what was reported."""
    assert "return null;" in STORE
    assert "state.rows === null" in ADMIN
    assert "did not load" in ADMIN


def test_a_failed_admin_check_refuses_rather_than_assumes() -> None:
    """An exception in the membership query must not fall through to a truthy
    value. Catching and returning false is the safe direction."""
    check = STORE[STORE.index("async function isAdmin"):STORE.index("async function listReports")]
    assert "return false;" in check.split("catch")[1]


def test_the_queue_is_capped() -> None:
    """An unbounded select is a page that gets slower every week and eventually
    does not render at all."""
    assert re.search(r"REPORT_LIMIT\s*=\s*\d+", STORE)
    assert ".limit(REPORT_LIMIT)" in STORE


def test_every_value_from_the_database_is_escaped() -> None:
    """Report titles and details are typed by people and rendered as HTML. The
    only interpolations allowed in a row are esc(...) or values this file built
    itself."""
    row = ADMIN[ADMIN.index("function row(r)"):ADMIN.index("function screenList")]

    # Every field a person can type must reach the page through esc().
    for field in ("r.title", "r.detail"):
        assert f"esc({field})" in row, field
        assert f"${{{field}}}" not in row, f"{field} interpolated raw"

    # And the two indirect ones: the filer's name, and the email reference,
    # which is escaped inside emailCell for the branch that is not a link.
    assert "esc(who(r))" in row and "esc(when(r.created_at))" in row
    assert "${esc(ref)}" in ADMIN[ADMIN.index("function emailCell"):ADMIN.index("function card")]


def test_a_gmail_reference_is_not_turned_into_a_link() -> None:
    """A demo id resolves in the inbox; a gmail_<id> means nothing without that
    person's mailbox, so linking it would be a link that always fails."""
    assert r"/^email_\d+$/.test(ref)" in ADMIN


def test_the_page_asks_to_be_left_out_of_search_results() -> None:
    """It sits on the same public deploy as the reviewer app."""
    assert '<meta name="robots" content="noindex,nofollow">' in ADMIN


def test_the_supabase_client_is_pinned_here_too() -> None:
    """Same reason index.html pins it: `@2` floats, and a release during judging
    would change this page with nothing in the repository changing."""
    assert "@supabase/supabase-js@2.117.1/+esm" in ADMIN
    assert "supabase-js@2/+esm" not in ADMIN


def test_the_page_script_runs_after_the_supabase_import() -> None:
    """`type="module"` is deferred; a classic script runs during parsing. As a
    classic script the page ran before `window.supabase` existed, so `sb()`
    returned null, `currentUser()` reported nobody signed in, and a reviewer who
    was already signed in on the inbox was asked to sign in again here."""
    import_at = ADMIN.index('<script type="module">')
    store_at = ADMIN.index('<script src="store.js">')
    page_at = ADMIN.index("(function(){", store_at)
    opener = ADMIN.rindex("<script", store_at, page_at)

    assert import_at < store_at, "the supabase import must be declared first"
    assert ADMIN[opener:page_at].startswith('<script type="module">'), (
        "the page script must be a module, or it runs before window.supabase exists")


def test_store_reads_the_client_lazily() -> None:
    """store.js is a classic script, so it still runs before the import. That is
    only safe while it touches `window.supabase` inside a function rather than
    at load."""
    head = STORE[:STORE.index("function sb(")]

    assert "window.supabase" not in head, "store.js reads window.supabase at load time"
