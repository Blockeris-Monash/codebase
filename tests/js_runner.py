"""Run a piece of the page's JavaScript in node, for behaviour no Python test can reach.

node ships on the CI runner (ubuntu-latest) and needs no package here. A test that needs
it skips with a reason when node is absent, rather than passing without running.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
NODE = shutil.which("node")
NODE_SECONDS = 20


def needs_node() -> None:
    if NODE is None:
        pytest.skip("node is not installed; the JavaScript behaviour tests need it")


def page_function(name: str, page: str = "index.html") -> str:
    """The source of one top-level `function name(...){...}` in a page, braces balanced."""
    source = (FRONTEND / page).read_text(encoding="utf-8")
    start = re.search(rf"^function {name}\(", source, re.M)
    assert start, f"{name} is not a top-level function in {page}"
    depth, i = 0, source.index("{", start.start())
    for i in range(i, len(source)):
        depth += {"{": 1, "}": -1}.get(source[i], 0)
        if depth == 0:
            return source[start.start():i + 1]
    raise AssertionError(f"{name} never closes")


def run_node(script: str) -> object:
    """Run `script` as an ES module; it prints one JSON value, which is returned."""
    needs_node()
    done = subprocess.run([NODE, "--input-type=module", "-e", script], capture_output=True, text=True,
                          timeout=NODE_SECONDS, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])
