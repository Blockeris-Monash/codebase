"""Every script the page runs parses, checked the way CI and the git hook check it (#147 B4)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from tests.js_runner import needs_node

ROOT = Path(__file__).resolve().parents[1]


def test_every_page_script_parses() -> None:
    needs_node()
    done = subprocess.run([sys.executable, "-m", "cli.check_frontend"], cwd=ROOT, capture_output=True, text=True)

    assert done.returncode == 0, done.stdout + done.stderr
