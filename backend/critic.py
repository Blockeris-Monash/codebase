"""A second opinion on how an email was sorted, asked only when there is a reason to doubt it.

Sorting is the one step with no safety net behind it: a BL check filed as GENERAL is
never compared, and nobody is told. So the first answer is checked against four signals
that cost nothing to test:

- the model said it was unsure (Qwen's tiers are 1.0, 0.85, 0.65 and 0.50; below
  THRESHOLD means 0.65 or 0.50, 5 of the 520 saved answers);
- an SI and a BL are attached, but it was not filed as a BL check;
- it asks for a password or a login next to a link, but was not filed as SPAM
  (edge case a12, phishing dressed as a draft BL);
- it reads like an automatic reply, but was filed as a BL check (edge case a11).

Only then is a different model asked the same question - never the same model twice,
since asking again mostly repeats the answer. That is two tries at most. The second
answer replaces the first only when it confirms the doubt that was raised, or when the
first was unsure and the second is surer. Anything else keeps the first answer at 0.50,
because two models disagreeing is itself a measure of confidence.

Every second opinion is filed as a technical report (backend/reports.py), so the admin
can see each one and why it was asked.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from backend import reports
from backend.extract.fallback import timed

BL_COMPARISON = "BL_COMPARISON"
SPAM = "SPAM"
THRESHOLD = 0.8
UNSURE = "0.50"
SECOND = "Gemini"

ROLE_IN_NAME = re.compile(r"_(SI|BL)(?=[._])", re.I)
CREDENTIALS = re.compile(r"\b(password|passcode|log ?in|sign ?in|verify your (?:e-?mail|account|identity))\b", re.I)
LINK = re.compile(r"https?://", re.I)
AUTOMATIC = re.compile(r"\b(automatic reply|auto-?reply|out of (?:the )?office|undeliverable)\b", re.I)


class Email(Protocol):
    subject: str
    body: str
    attachments: list[str]


class Answer(Protocol):
    category: str
    confidence_tier: str
    evidence: str


@dataclass(frozen=True)
class Doubt:
    reason: str
    confirmed_by: Callable[[str], bool]  # a second category that bears the doubt out


def has_si_and_bl(attachments: list[str]) -> bool:
    roles = {m.group(1).upper() for name in attachments for m in [ROLE_IN_NAME.search(Path(name).name)] if m}
    return roles == {"SI", "BL"}


def doubts(email: Email, first: Answer) -> list[Doubt]:
    """Why the first answer might be wrong. Empty for about 99 emails in 100."""
    text = f"{email.subject}\n{email.body}"
    found = []
    if float(first.confidence_tier) < THRESHOLD:
        found.append(Doubt(f"the first model was only {first.confidence_tier} sure", lambda second: False))
    if first.category != BL_COMPARISON and has_si_and_bl(email.attachments):
        found.append(Doubt("an SI and a BL are attached, but it was not filed as a BL check",
                           lambda second: second == BL_COMPARISON))
    if first.category != SPAM and CREDENTIALS.search(text) and LINK.search(text):
        found.append(Doubt("it asks for a password or login next to a link",
                           lambda second: second == SPAM))
    if first.category == BL_COMPARISON and AUTOMATIC.search(text):
        found.append(Doubt("it reads like an automatic reply",
                           lambda second: second != BL_COMPARISON))

    return found


def decide(first: Answer, second: Answer, found: list[Doubt]) -> tuple[Answer, str, str]:
    """(the answer to keep, a title for the report, what happened and why)."""
    if second.category == first.category:
        surer = max(first, second, key=lambda answer: float(answer.confidence_tier))
        return surer, f"second opinion agreed on {first.category}", f"{SECOND} agreed."

    confirming = next((d for d in found if d.confirmed_by(second.category)), None)
    first_unsure = float(first.confidence_tier) < THRESHOLD
    if confirming or (first_unsure and float(second.confidence_tier) > float(first.confidence_tier)):
        why = f"{SECOND} agreed that {confirming.reason}" if confirming else f"{SECOND} was surer"
        return (second, f"changed from {first.category} to {second.category}",
                f"Changed to {second.category}: {why}.")

    kept = first.model_copy(update={"confidence_tier": UNSURE})
    return (kept, f"models disagreed, kept {first.category}",
            f"{SECOND} said {second.category}. Kept {first.category} at {UNSURE}, since the two disagree.")


def review(email: Email, first: Answer, prompt: str, ask: Callable[[str], Answer]) -> Answer:
    """The first answer, or a better one, after a second opinion when there is a reason to ask."""
    found = doubts(email, first)
    if not found:
        return first

    asked = "Asked because " + "; ".join(d.reason for d in found) + ". "
    if reports.answered_by() == SECOND:
        # The first answer already came from the backup, because Qwen did not answer.
        # Asking the same model again would cost quota and add nothing.
        reports.note("not double-checked", asked + f"{SECOND} gave the first answer, so it was not asked again.")
        return first

    try:
        second = timed(SECOND, ask, prompt)
    except Exception:  # the attempt, with its error, is already in the report
        reports.note(f"second opinion failed, kept {first.category}",
                     asked + f"{SECOND} did not answer, so the first answer stands.")
        return first

    kept, title, what = decide(first, second, found)
    reports.note(title, asked + what)

    return kept
