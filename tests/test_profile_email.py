"""A profile's email is the sign-in email, so nobody can block another person's sign-up (#147 A2).

0004 let a user set their own `users.email` to anyone's address. `users.email` is unique,
so that person's first Google sign-in then failed inside the `handle_new_user` trigger.

Checked against a real Postgres 16 with a stub of Supabase's auth schema: before 0007 the
squatted address made the victim's sign-up fail; after it the update is refused, the
victim signs in, display names can still be edited, and an already-squatted row is put
back. These tests pin the three parts of the migration that do that.
"""
from __future__ import annotations

import re
from pathlib import Path

MIGRATION = (Path(__file__).resolve().parents[1] / "backend" / "db" / "migrations"
             / "0007_a_profile_email_is_the_sign_in_email.sql").read_text(encoding="utf-8")
SIGN_IN_EMAIL = "lower(email) = lower(coalesce(auth.jwt() ->> 'email', ''))"


def policy(name: str) -> str:
    return re.search(rf"create policy {name} on users.*?;", MIGRATION, re.S).group(0)


def test_a_profile_cannot_be_written_with_someone_elses_email() -> None:
    for name in ("own_profile_insert", "own_profile_update"):
        assert SIGN_IN_EMAIL in " ".join(policy(name).split()), name


def test_a_sign_up_never_fails_on_a_profile_row() -> None:
    trigger = MIGRATION[MIGRATION.index("create or replace function handle_new_user"):]

    assert "on conflict do nothing" in trigger


def test_a_profile_already_squatted_is_put_back() -> None:
    assert re.search(r"update users u\s+set email = a\.email\s+from auth\.users a", MIGRATION)
