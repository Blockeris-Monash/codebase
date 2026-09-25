"""The reply drafter has the guards every other model path has (#147 B1).

Drafting and refining sent the email to Gemini, Qwen and the embedding API exactly as
written, the one model path that did not mask first. The models are faked here, so
this runs offline: each fake records the prompt it was given and answers as told.
"""
from __future__ import annotations

import pytest

from backend import reply
from backend.classify import EmailInput

PHONE = "+60 12-345 6789"
PERSONAL = "john.smith@gmail.com"
EMAIL = EmailInput(email_id="gmail_1", from_email="a@b.example", subject=f"Call {PHONE} about invoice 5250076025",
                   body=f"Is THC billed separately? Call me on {PHONE} or write to {PERSONAL}.", attachments=[])


@pytest.fixture
def seen(monkeypatch) -> dict:
    """Every text a model or the embedding API was given, and what the model answers."""
    state: dict = {"prompts": [], "systems": [], "queries": [], "answer": "Dear customer, noted."}

    def model(prompt: str, system_instruction: str) -> str:
        state["prompts"].append(prompt)
        state["systems"].append(system_instruction)
        return state["answer"]

    def retrieve(query: str, top_k: int = 3) -> list:
        state["queries"].append(query)
        return []

    monkeypatch.setattr(reply, "retrieve_policies", retrieve)
    monkeypatch.setattr(reply, "gemini_generate", model)
    monkeypatch.setattr(reply, "qwen_generate", model)
    monkeypatch.setattr(reply, "GEMINI_API_KEY", "test-key")
    return state


def everything_sent(state: dict) -> str:
    return "\n".join(state["prompts"] + state["systems"] + state["queries"])


def test_a_draft_sends_no_phone_number_or_personal_email_to_any_model(seen: dict) -> None:
    reply.generate_rag_reply(EMAIL, "INVOICE_QUERY")

    sent = everything_sent(seen)
    assert PHONE not in sent and PERSONAL not in sent
    assert seen["queries"], "retrieval was never asked"


def test_a_refinement_sends_no_phone_number_or_personal_email_to_any_model(seen: dict) -> None:
    reply.refine_rag_reply(EMAIL, f"We will call {PHONE}.", f"mention {PERSONAL} too")

    sent = everything_sent(seen)
    assert PHONE not in sent and PERSONAL not in sent


def test_a_masked_value_the_model_repeats_comes_back_real(seen: dict) -> None:
    """The draft goes to the customer, so "<PHONE_NUMBER>" in it would be a broken reply."""
    reply.generate_rag_reply(EMAIL, "INVOICE_QUERY")
    token = next(word.strip(".,") for word in seen["prompts"][0].split() if word.startswith("__PHONE_NUMBER_"))
    seen["answer"] = f"Dear customer, we will call {token}."

    drafted = reply.generate_rag_reply(EMAIL, "INVOICE_QUERY")

    assert PHONE in drafted


def test_two_values_across_the_subject_and_the_body_get_two_tokens(seen: dict) -> None:
    """Masked one by one, each text numbered its tokens from 1, so two different values
    could share __PHONE_NUMBER_1__ and be restored as the wrong one."""
    other = EmailInput(email_id="gmail_2", from_email="a@b.example", subject="Call +60 3-7721 8899",
                       body=f"Or my mobile {PHONE}.", attachments=[])

    reply.generate_rag_reply(other, "GENERAL")

    prompt = seen["prompts"][0]
    tokens = {word.strip(".,") for word in prompt.split() if word.startswith("__PHONE_NUMBER_")}
    assert len(tokens) == 2
