"""Three page bugs from the code review (#162 A6, A7, A8).

A6: after #159, an email already marked done or replied to lost its "Marked as done" /
"Reply sent" block and its Undo once its last difference was dismissed: actionsHTML returned
early for a Verified email before it looked at the mark.
A7: a reply draft already open was not rebuilt after a dismiss or fix, so it still asked the
sender to correct a field the reviewer had just cleared. An unedited draft now follows the
corrected fields (and closes if nothing is left to ask); an edited one is left alone.
A8: after Refine, a demo reply lost its "written by Claude" label and showed none at all.
"""
from __future__ import annotations

from pathlib import Path

INDEX = (Path(__file__).resolve().parents[1] / "frontend" / "index.html").read_text(encoding="utf-8")
I18N = (Path(__file__).resolve().parents[1] / "frontend" / "i18n.js").read_text(encoding="utf-8")


def function(name: str) -> str:
    body = INDEX[INDEX.index(f"function {name}("):]
    return body[:body.index("\n}")]


def test_a_marked_email_keeps_its_done_state_whatever_its_status() -> None:
    actions = function("actionsHTML")
    assert actions.index("if(m) return") < actions.index('e.status!=="MISMATCH" && e.status!=="NEEDS_REVIEW"')


def test_an_unedited_open_draft_follows_the_corrected_fields() -> None:
    keep = function("keepCorrection")
    assert "S.draft && S.draft.id===id" in keep
    assert "S.draft.body===before" in keep                      # only when the reviewer has not edited it
    assert "draftFor(withCorrections(e))" in keep


REFINED = "Refined with Ship Happens' AI from a reply written in advance by Claude for the demo."


def test_a_refined_demo_reply_says_so() -> None:
    assert f'd.refined?(e.draft_by==="claude"?`<div class="small mute sample">${{t("{REFINED}")}}</div>`:"")' in INDEX
    assert I18N.count(f'"{REFINED}":') == 2
