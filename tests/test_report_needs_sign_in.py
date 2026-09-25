"""Signed out, "Report a problem with this result" opened the report form, and Send said the
report was sent. It only reached the browser: the reports queue takes rows from signed-in
accounts alone. A visitor on the demo emails now gets a popup saying reporting needs a
sign-in, with a button to sign in. Signed in, the button opens the form as before."""
from __future__ import annotations

from pathlib import Path

INDEX = (Path(__file__).resolve().parents[1] / "frontend" / "index.html").read_text(encoding="utf-8")


def report_click() -> str:
    handler = INDEX[INDEX.index('else if(a==="report"){'):]
    return handler[:handler.index("\n")]


def popup() -> str:
    body = INDEX[INDEX.index("function reportSignInHTML(){"):]
    return body[:body.index("\n}\n")]


def test_signed_out_the_report_button_opens_the_sign_in_popup() -> None:
    click = report_click()
    assert "if(!S.user){ S.reportDlg=true; }" in click
    assert click.index("if(!S.user)") < click.index("S.help=true")


def test_signed_in_the_report_button_still_opens_the_form() -> None:
    click = report_click()
    assert 'else{ S.help=true; S.tab="support"; S.fb={kind:"problem"' in click


def test_the_popup_says_why_and_offers_sign_in() -> None:
    body = popup()
    assert 't("Sign in to report a problem")' in body
    assert ('t("These are demo emails, so a report sent from here is not saved or seen by '
            'the team. Reporting is only available when you sign in with Google.")') in body
    assert 'data-a="reportsignin"' in body and 't("Sign in with Google")' in body
    assert 'data-a="reportclose"' in body and 'role="dialog"' in body


def test_the_popup_is_drawn_and_can_be_closed() -> None:
    assert '${S.reportDlg?reportSignInHTML():""}' in INDEX
    assert 'else if(a==="reportclose"){ S.reportDlg=false; }' in INDEX
    assert 'else if(a==="reportsignin"){ S.reportDlg=false; startSignIn(); return; }' in INDEX
    assert "S.reportDlg=false; S.mailDlg=false; S.langMenu=false; render(); return; }" in INDEX


def test_the_general_support_form_is_unchanged() -> None:
    """Only the button on an email asks for a sign-in; Help, Contact support does not."""
    assert 'if(a==="help"){ S.help=true; S.tab="guide"; S.tabChanged=true; }' in INDEX
    assert "reportDlg" not in INDEX[INDEX.index("function supportHTML("):INDEX.index("function helpHTML(")]
