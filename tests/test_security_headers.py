"""The page and the API send security headers (#147 B2).

Neither sent a content security policy, frame-ancestors or nosniff, and supabase-js loaded
from a CDN with no integrity check on a page that holds a Gmail send token.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.middleware import MAX_BODY_BYTES
from cli import csp

ROOT = Path(__file__).resolve().parents[1]
SUPABASE_TAG = re.compile(r'<script defer src="(https://cdn\.jsdelivr\.net/npm/@supabase/supabase-js@[\d.]+/dist/umd/'
                          r'supabase\.js)" integrity="(sha384-[A-Za-z0-9+/=]+)" crossorigin="anonymous"></script>')


def test_the_headers_in_vercel_json_are_current() -> None:
    """Editing an inline script without regenerating would make the browser refuse it."""
    done = subprocess.run([sys.executable, "-m", "cli.csp", "--check"], cwd=ROOT, capture_output=True, text=True)

    assert done.returncode == 0, done.stdout + done.stderr


def test_an_edited_inline_script_is_no_longer_allowed() -> None:
    allowed = csp.policy()

    assert csp.script_hash("console.log('hi')") not in allowed
    assert "'unsafe-inline'" not in allowed.split("script-src", 1)[1].split(";", 1)[0]


def test_the_policy_keeps_the_page_from_being_framed_or_rebased() -> None:
    allowed = csp.policy()

    for directive in ("frame-ancestors 'none'", "base-uri 'none'", "object-src 'none'"):
        assert directive in allowed


@pytest.mark.parametrize("page", ["index.html", "admin.html"])
def test_supabase_js_is_pinned_and_integrity_checked(page: str) -> None:
    html = (ROOT / "frontend" / page).read_text(encoding="utf-8")

    assert "+esm" not in html, "the on-demand ESM build cannot carry an integrity hash"
    assert len(SUPABASE_TAG.findall(html)) == 1


def test_both_pages_load_the_same_supabase_file() -> None:
    tags = {SUPABASE_TAG.search((ROOT / "frontend" / page).read_text(encoding="utf-8")).groups()
            for page in ("index.html", "admin.html")}

    assert len(tags) == 1


@pytest.mark.parametrize("path, body", [("/health", None), ("/classify", "x" * (MAX_BODY_BYTES + 1))],
                         ids=["answer", "refusal"])
def test_every_api_answer_carries_the_headers(path: str, body: str | None) -> None:
    client = TestClient(app)
    answer = client.post(path, content=body) if body else client.get(path)

    assert answer.headers["X-Content-Type-Options"] == "nosniff"
    assert answer.headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in answer.headers["Content-Security-Policy"]


def test_the_api_docs_keep_their_cdn() -> None:
    answer = TestClient(app).get("/docs")

    assert answer.status_code == 200
    assert "Content-Security-Policy" not in answer.headers
