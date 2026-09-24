"""The page's half of the live mailbox (task 2): ask Google for Gmail access at
sign-in, hand the token to /mailbox and /reply, and really send only mail that
came from the person's own mailbox. Read from the source, as the other UI tests do.
"""
from __future__ import annotations

import re
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
INDEX = (FRONTEND / "index.html").read_text(encoding="utf-8")
STORE = (FRONTEND / "store.js").read_text(encoding="utf-8")


def function(source: str, name: str) -> str:
    """One function's text. store.js indents its functions inside a wrapper; index.html does not."""
    body = source[source.index(f"function {name}("):]
    return body[:body.index("\n  }" if source is STORE else "\n}")]


def test_sign_in_asks_google_to_read_and_to_send_gmail_nothing_more() -> None:
    sign_in = function(STORE, "signIn")
    scopes = set(re.findall(r"https://www\.googleapis\.com/auth/[\w.]+", sign_in))

    assert scopes == {"https://www.googleapis.com/auth/gmail.readonly",
                      "https://www.googleapis.com/auth/gmail.send"}


def test_the_google_token_is_kept_in_memory_and_never_logged() -> None:
    assert "session.provider_token" in STORE and "googleToken" in STORE
    assert not re.search(r"console\.\w+\([^)]*(provider_token|googleAccess)", STORE)
    assert not re.search(r"localStorage\.setItem\([^)]*(provider_token|googleAccess)", STORE + INDEX)


def test_the_mailbox_is_asked_for_with_the_token_not_a_user_id() -> None:
    """A user id in the URL let anyone ask for anyone's mail. Google's token proves who it is."""
    fetch = function(INDEX, "fetchLiveMailbox")

    assert "user_id" not in fetch
    assert '"Authorization": "Bearer " + token' in fetch


def test_the_page_says_when_the_mailbox_needs_a_new_sign_in() -> None:
    fetch = function(INDEX, "fetchLiveMailbox")

    assert "res.status === 401" in fetch and "S.mailboxErr" in fetch
    assert "${mailboxBarHTML()}" in INDEX


def test_only_mail_from_the_persons_own_mailbox_is_really_sent() -> None:
    """The 520 demo emails carry real companies' addresses: their Send stays a demo."""
    send = INDEX[INDEX.index('else if(a==="send")'):]
    send = send[:send.index("\n")]

    assert "isLive(id)" in send and "sendLive(id)" in send
    assert 'const isLive = id=>String(id).startsWith("gmail_");' in INDEX
    assert 'API_BASE + "/reply"' in function(INDEX, "sendLive")


def test_a_real_reply_is_marked_only_after_gmail_took_it() -> None:
    live = function(INDEX, "sendLive")

    assert live.index("if(!res.ok)") < live.index('S.marks[id]="back"')


def test_a_sent_email_offers_no_undo() -> None:
    """Undo only ever cleared the mark. Once a reply has really gone, it cannot be taken back."""
    assert "sent&&sent.real" in INDEX and "S.toast.real" in INDEX


def test_a_real_reply_is_saved_as_sent_and_as_mailbox_mail() -> None:
    push = function(STORE, "pushReply")

    assert "sent_at: reply.real ?" in push
    assert "sourceOf(emailRef)" in push and "sourceOf(emailRef)" in function(STORE, "pushMark")


def test_the_landing_page_no_longer_says_read_only_or_coming_soon_for_gmail() -> None:
    assert "Mailbox access will be read-only." not in INDEX
    assert "Your mailbox appears here in the next update." not in INDEX
    assert "Send is a demo today." not in INDEX


def test_mailbox_mail_opens_its_thread_in_gmail_not_a_mail_app() -> None:
    """mailto: does nothing on a computer with no mail app, which is most people who use Gmail
    in the browser. A live email is already in their Gmail, so the button opens it there."""
    actions = function(INDEX, "actionsHTML")

    assert 'isLive(e.id)?`<a class="btn alt" href="${gmailLink(e)}" target="_blank" rel="noopener">${t("Open in Gmail")}</a>`' in actions
    assert 'data-a="mailto"' in actions  # demo emails keep it
    link = INDEX[INDEX.index("const gmailLink"):]
    link = link[:link.index("\n")]
    assert "https://mail.google.com/mail/?authuser=" in link and "#all/" in link
    assert "encodeURIComponent" in link
