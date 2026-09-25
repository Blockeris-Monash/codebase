"""POST /refine: rewrite a drafted reply the way the person asks (#156)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app import app
from backend.middleware import LIMITED_PATHS

client = TestClient(app)

EMAIL = {"email_id": "test_id", "from_email": "sender@test.com", "subject": "Test Subject",
         "body": "Test Body", "attachments": []}


def refine(instruction: str = "Make it shorter.", draft: str = "This is a draft.") -> object:
    return client.post("/refine", json={"email": EMAIL, "current_draft": draft, "instruction": instruction})


@patch("backend.reply.refine_rag_reply", return_value="This is a refined AI reply.")
def test_the_refined_draft_comes_back(refine_rag_reply) -> None:
    response = refine()

    assert response.status_code == 200
    assert response.json() == {"draft_reply": "This is a refined AI reply."}
    refine_rag_reply.assert_called_once()


@patch("backend.reply.refine_rag_reply", return_value=None)
def test_a_failed_refinement_is_a_502_not_an_empty_draft(_refine_rag_reply) -> None:
    """The page would otherwise replace the draft with nothing, or keep it and say nothing."""
    response = refine()

    assert response.status_code == 502
    assert "could not refine" in response.json()["detail"]


@patch("backend.reply.refine_rag_reply", return_value="unused")
def test_an_empty_or_oversized_instruction_is_refused_before_the_model(refine_rag_reply) -> None:
    assert refine(instruction="").status_code == 422
    assert refine(instruction="x" * 501).status_code == 422
    assert refine(draft="x" * 20_001).status_code == 422
    refine_rag_reply.assert_not_called()


def test_refining_is_rate_limited_because_it_spends_model_quota() -> None:
    assert "/refine" in LIMITED_PATHS


def test_a_page_on_localhost_calls_the_local_backend_and_nothing_else_can_move_it() -> None:
    """A local page used to call the deployed backend, where a new route answered 404 (#156).
    The switch reads only the page's own host: the Google token goes to this address."""
    config = (Path(__file__).resolve().parent.parent / "frontend" / "config.js").read_text(encoding="utf-8")

    assert '"http://localhost:8000"' in config
    assert "location.hostname" in config
    assert "location.search" not in config and "localStorage" not in config
