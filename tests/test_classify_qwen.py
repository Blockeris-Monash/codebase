"""cli.classify_qwen: batch classification on Qwen, saved for the UI. No network in these tests."""
import json

import pytest

from cli.classify_qwen import build_prompt, classify_with_qwen, run_batch

EMAIL = {"email_id": "email_013", "from": "a@b.com", "subject": "TO CONFIRM DOCS",
         "body": "Please check the draft BL against the SI.",
         "attachments": ["attachments/email_013_SI.txt", "attachments/email_013_BL.txt"]}


def reply(text: str):
    """A fake `post` that answers like the gateway does."""
    return lambda url, headers, body: {"content": [{"type": "text", "text": text}]}


GOOD = json.dumps({"category": "BL_COMPARISON", "confidence_tier": "0.85", "evidence": "check the draft BL against the SI"})


def test_result_follows_contract_02():
    result = classify_with_qwen(EMAIL, post=reply(GOOD), key="k", base_url="http://x")
    assert result == {"email_id": "email_013", "category": "BL_COMPARISON", "decided_by": "llm",
                      "confidence": 0.85, "evidence": "check the draft BL against the SI"}


def test_reply_wrapped_in_a_code_fence_still_parses():
    result = classify_with_qwen(EMAIL, post=reply("```json\n" + GOOD + "\n```"), key="k", base_url="http://x")
    assert result["category"] == "BL_COMPARISON"


def test_unknown_category_is_rejected():
    bad = json.dumps({"category": "PHISHING", "confidence_tier": "1.0", "evidence": "x"})
    with pytest.raises(ValueError):
        classify_with_qwen(EMAIL, post=reply(bad), key="k", base_url="http://x")


def test_prompt_tells_the_model_which_files_are_attached():
    assert "email_013_SI.txt" in build_prompt(EMAIL)
    assert "none" in build_prompt({**EMAIL, "attachments": []}).lower()


def test_batch_skips_saved_results_and_saves_new_ones(tmp_path):
    inbox = tmp_path / "data" / "inbox"
    inbox.mkdir(parents=True)
    for n in ("013", "014"):
        (inbox / f"email_{n}.json").write_text(json.dumps({**EMAIL, "email_id": f"email_{n}"}))
    out = tmp_path / "out"
    out.mkdir()
    (out / "email_013.json").write_text("{}")  # already done

    calls = []
    def post(url, headers, body):
        calls.append(1)
        return {"content": [{"type": "text", "text": GOOD}]}

    done, failed = run_batch(tmp_path / "data", out, post=post, key="k", base_url="http://x", workers=1)
    assert (done, failed) == (1, 0) and len(calls) == 1
    assert json.loads((out / "email_014.json").read_text())["category"] == "BL_COMPARISON"
    assert json.loads((out / "email_013.json").read_text()) == {}  # untouched
