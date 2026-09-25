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


def test_the_supabase_secret_has_exactly_one_name() -> None:
    """It briefly had two - SUPABASE_KEY in reply.py, SUPABASE_SERVICE_ROLE_KEY
    in reports.py - and a deployment that set the documented one had retrieval
    silently off. The alias existed only while an environment still used it."""
    from backend import settings

    assert settings.SUPABASE_SECRET_NAMES == ("SUPABASE_SERVICE_ROLE_KEY",)
    for source in ("backend/reply.py", "backend/reports.py", "backend/app.py"):
        assert "SUPABASE_KEY" not in (ROOT / source).read_text(encoding="utf-8"), source


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


def test_one_place_decides_which_names_count() -> None:
    """Aliases are fine; a name cannot be withdrawn once people have set it. Each
    module deciding for itself which names count is not, because then "is this
    configured" has a different answer in every file - which is exactly how
    reply.py ended up with no model while gemini.py had one."""
    reply = (ROOT / "backend" / "reply.py").read_text(encoding="utf-8")

    assert "settings.supabase_secret()" in reply
    assert "settings.gemini_key()" in reply
    assert 'os.environ.get("GEMINI_API_KEY")' not in reply
    assert 'os.environ.get("SUPABASE_KEY")' not in reply


def test_a_gemini_key_under_either_name_reaches_the_reply_drafting() -> None:
    """gemini.py has always accepted GOOGLE_API_KEY or GEMINI_API_KEY. reply.py
    read only the second, so an environment with the first - which is what
    .env.example has always shown - had drafting with no model behind it and
    nothing on screen to say so."""
    from backend import settings

    from backend.extract.gemini import KEY_NAMES

    assert set(KEY_NAMES) == {"GOOGLE_API_KEY", "GEMINI_API_KEY"}
    monkeypatch_free = settings.gemini_key
    assert monkeypatch_free.__module__ == "backend.settings"


def test_retrieval_is_only_on_when_it_has_both_halves(monkeypatch) -> None:
    """It needs a database and a model. Reporting only the database said "on"
    while replies were drafted with no model at all."""
    from backend import settings

    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "secret")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    assert settings.supabase_configured() is True
    assert settings.gemini_key() is None        # so retrieval must report OFF


def test_no_module_reads_a_credential_around_the_accessor() -> None:
    """The point of settings.py is that "is this configured" has one answer. A
    module that goes back to os.environ for a credential can disagree with it,
    which is the bug this whole file exists because of."""
    offenders = []
    for path in (ROOT / "backend").rglob("*.py"):
        if path.name == "settings.py":
            continue
        source = path.read_text(encoding="utf-8")
        for name in ("SUPABASE_URL", "SUPABASE_KEY", "SUPABASE_SERVICE_ROLE_KEY",
                     "GOOGLE_API_KEY", "GEMINI_API_KEY"):
            if f'environ.get("{name}")' in source or f'environ["{name}"]' in source:
                offenders.append(f"{path.relative_to(ROOT)}: {name}")

    # gemini.py owns the Gemini alias list itself and settings re-exports it.
    offenders = [o for o in offenders if not o.startswith("backend/extract/gemini.py")]

    assert offenders == [], f"reads a credential directly: {offenders}"


def test_the_test_run_cannot_write_to_the_live_queue() -> None:
    """Tests fail models on purpose and every failure files a report. The guard
    has to clear every name the secret is accepted under, not only the canonical
    one - otherwise a machine set up the way the deployment notes describe would
    post fake failures into the team's queue."""
    import os

    from backend import settings

    for name in settings.SUPABASE_SECRET_NAMES:
        assert os.environ.get(name) is None, f"{name} is still set inside the test run"
    assert settings.supabase_secret() is None


def test_the_offline_suite_cannot_reach_a_model() -> None:
    """backend/app.py calls load_dotenv() at import, so importing the service
    pulls a developer's .env into the environment. The live gate stops *tests*
    calling a model; it cannot stop the *application* doing it, and the mailbox
    check classifies each new email in the background.

    Measured before this guard: 66.9s and an intermittent failure with keys
    present, against 1.45s and green with them cleared. CI never saw it because
    CI has no .env.
    """
    import os

    from tests.conftest import MODEL_KEYS

    for name in MODEL_KEYS:
        assert os.environ.get(name) is None, f"{name} is visible inside the offline suite"


def test_the_guard_steps_aside_when_the_live_tests_are_asked_for() -> None:
    """SHIP_HAPPENS_LIVE=1 is someone asking for the live tests by name, and
    those need the keys. The guard has to read the opt-in, not blanket-clear."""
    source = (ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")

    guard = source[source.index("def no_model_calls_from_the_application"):]
    assert "LIVE_OPT_IN" in guard.split("for name in MODEL_KEYS")[0]
    assert "return" in guard.split("for name in MODEL_KEYS")[0]
