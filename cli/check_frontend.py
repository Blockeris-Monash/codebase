"""Check that every script the page runs at least parses, before it reaches a browser.

    python -m cli.check_frontend

A merge commit on #159 left four missing commas in frontend/i18n.js and code twice in
index.html. The browser would have thrown on load and language switching would have
stopped; only an unrelated test happened to catch it. This runs `node --check` on every
script file and on every inline <script> in the pages, parses the translations the way
the page reads them, starts the page in a fake browser to catch anything thrown on
load, and checks the security headers are current (cli/csp.py).

Exits 1 on the first kind of failure it finds, naming the file. Needs node, which CI's
runner has; run by CI and by .githooks/pre-commit.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from cli import csp

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
SCRIPT_FILES = ("i18n.js", "store.js", "sw.js", "config.js", "scans.js")
PAGES = ("index.html", "admin.html")
# Runs the page's scripts in load order in a fake browser: a parse check cannot see a value
# read before its line has run, which broke sign-in on #168.
BOOT = Path(__file__).resolve().parents[1] / "tests" / "js" / "boot_page.mjs"
INLINE = re.compile(r"<script(?![^>]*\bsrc=)([^>]*)>(.*?)</script>", re.S)


def node_check(path: Path, node: str) -> str | None:
    """None when node parses the file, else what node said."""
    done = subprocess.run([node, "--check", str(path)], capture_output=True, text=True, check=False)
    return None if done.returncode == 0 else done.stderr.strip()


def inline_scripts(workdir: Path) -> list[tuple[str, Path]]:
    """Each inline script written to its own file, named after where it came from."""
    written = []
    for page in PAGES:
        for n, match in enumerate(INLINE.finditer((FRONTEND / page).read_text(encoding="utf-8")), 1):
            suffix = ".mjs" if "module" in match.group(1) else ".js"
            path = workdir / f"{Path(page).stem}_inline_{n}{suffix}"
            path.write_text(match.group(2), encoding="utf-8")
            written.append((f"{page}, inline script {n}", path))
    return written


def translations_parse() -> str | None:
    """The page reads i18n.js as `window.I18N = {...}`; the object must be valid JSON."""
    lines = [line for line in (FRONTEND / "i18n.js").read_text(encoding="utf-8").splitlines()
             if not line.startswith("//")]
    body = "\n".join(lines).strip().removeprefix("window.I18N =").removesuffix(";")
    try:
        json.loads(body)
    except json.JSONDecodeError as error:
        return str(error)
    return None


def main() -> int:
    node = shutil.which("node")
    if node is None:
        print("node is not installed; it is needed to check the page's scripts")
        return 1
    failures = []
    with tempfile.TemporaryDirectory() as workdir:
        targets = [(name, FRONTEND / name) for name in SCRIPT_FILES] + inline_scripts(Path(workdir))
        failures += [f"{name}: {why}" for name, path in targets if (why := node_check(path, node))]
    booted = subprocess.run([node, str(BOOT), str(FRONTEND)], capture_output=True, text=True, check=False)
    thrown = json.loads(booted.stdout.strip().splitlines()[-1]) if booted.returncode == 0 else [booted.stderr.strip()]
    failures += [f"the page throws while starting: {error}" for error in thrown]
    if (why := translations_parse()):
        failures.append(f"i18n.js is not valid JSON: {why}")
    if (FRONTEND / "vercel.json").read_text(encoding="utf-8") != csp.rendered(csp.with_headers(
            json.loads((FRONTEND / "vercel.json").read_text(encoding="utf-8")))):
        failures.append("frontend/vercel.json is out of date: run python -m cli.csp")

    for failure in failures:
        print(failure)
    print("frontend scripts: all parse" if not failures else f"frontend scripts: {len(failures)} problem(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
