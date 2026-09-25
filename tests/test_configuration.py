"""Every switch the service reads should be written down, and say when it is off.

Each optional feature here fails quietly when its variable is unset. No Supabase
key and the company guidelines are never retrieved, so replies are drafted from
nothing. No Gemini key and there is no second provider when Qwen stalls. Nothing
appears on screen in either case.

That is how the reports queue stayed empty: `backend/reports.py` reads
SUPABASE_SERVICE_ROLE_KEY, `backend/reply.py` read SUPABASE_KEY, and only the
first was ever written down - so a deployment that followed the documentation
had retrieval silently switched off.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = (ROOT / ".env.example").read_text(encoding="utf-8")
SOURCE_DIRS = ("backend", "cli", "tools")

# Upper-case strings that are dictionary keys or status values, not environment
# variables. Matched exactly, so a real variable can never hide behind one.
NOT_SETTINGS = {"MISMATCH", "NEEDS_REVIEW", "OK", "SPAM", "GENERAL", "SI", "BL",
                "L0", "N1", "N7", "R4", "W0", "W1", "P4", "ISA", "GS", "ST"}


def environment_names() -> set[str]:
    """Every name passed to os.environ.get / os.getenv / os.environ[...], including
    the ones passed as a module constant rather than a literal."""
    found: set[str] = set()
    for folder in SOURCE_DIRS:
        for path in (ROOT / folder).rglob("*.py"):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:
                continue

            constants = {
                target.id: node.value.value
                for node in ast.walk(tree)
                if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
                for target in node.targets if isinstance(target, ast.Name)
            }

            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                        and node.func.attr in ("get", "getenv"):
                    arguments = node.args[:1]
                elif isinstance(node, ast.Subscript):
                    arguments = [node.slice]
                else:
                    continue

                for argument in arguments:
                    if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                        name = argument.value
                    elif isinstance(argument, ast.Name):
                        name = constants.get(argument.id, "")
                    else:
                        continue
                    if re.fullmatch(r"[A-Z][A-Z0-9_]{3,}", name) and name not in NOT_SETTINGS:
                        found.add(name)

    return found


def test_every_setting_the_code_reads_is_written_down() -> None:
    """A variable that is read but documented nowhere is one nobody can set on
    purpose - and one nobody knows to set when a feature is silently off."""
    undocumented = sorted(name for name in environment_names() if name not in EXAMPLE)

    assert undocumented == [], f"read by the code, missing from .env.example: {undocumented}"


def test_the_two_names_for_the_supabase_secret_both_work() -> None:
    """One credential had two names across two modules, and only one was
    documented. Both are accepted now, the documented one first, so neither a
    new deployment nor an existing one is left without a client."""
    source = (ROOT / "backend" / "reply.py").read_text(encoding="utf-8")

    assert "SUPABASE_SERVICE_ROLE_KEY" in source
    assert source.index("SUPABASE_SERVICE_ROLE_KEY") < source.index('os.environ.get("SUPABASE_KEY")')


def test_the_service_says_which_optional_features_are_off() -> None:
    """Every one of these fails quietly. A deployment missing a variable should
    say so once, at the top of the log, rather than be found out during judging."""
    source = (ROOT / "backend" / "app.py").read_text(encoding="utf-8")

    assert "def say_what_is_switched_on" in source
    assert "say_what_is_switched_on()" in source.split("def say_what_is_switched_on")[-1]
    for feature in ("reports", "retrieval", "gemini-backup", "critic", "vision"):
        assert feature in source, feature


def test_the_guidelines_corpus_is_not_readable_with_the_public_key() -> None:
    """0003 creates `policies` and never enables row-level security, while every
    table in 0001 enables it explicitly. The live project has it on because
    somebody set it by hand - so the migrations stopped describing the database,
    and a fresh deploy would leave all of it readable by anyone holding the
    publishable key, which is committed in frontend/config.js.
    """
    migrations = ROOT / "backend" / "db" / "migrations"
    combined = "\n".join(p.read_text(encoding="utf-8") for p in sorted(migrations.glob("*.sql")))

    assert "alter table policies enable row level security" in combined

    # And no policy may grant it back: RLS denies what no policy permits, which
    # leaves the corpus reachable only by the service role the server holds.
    assert not re.search(r"create policy \w+ on policies", combined)
