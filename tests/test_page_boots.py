"""The review page starts without an error, with its scripts run in the order the browser runs them.

#168 made render() end with syncPolling(), which reads constants declared further down the
script; the first render() ran before their lines, threw, and stopped everything after it,
Google sign-in included. Tests of single functions cannot see load order, so this boots the
whole page in node (tests/js/boot_page.mjs) and fails on anything thrown.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from tests.js_runner import NODE, needs_node

ROOT = Path(__file__).resolve().parents[1]


def test_the_page_starts_without_an_error() -> None:
    needs_node()
    done = subprocess.run([NODE, str(ROOT / "tests" / "js" / "boot_page.mjs"), str(ROOT / "frontend")],
                          capture_output=True, text=True, timeout=60, check=False)

    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout.strip().splitlines()[-1]) == []
