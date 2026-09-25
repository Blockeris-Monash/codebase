"""One place that answers "is this configured", for settings that have more
than one accepted name.

Two credentials in this service ended up with two names each, both by ordinary
accident: people added them in parallel, hours apart, and neither could have
known about the other.

- The Supabase secret was `SUPABASE_SERVICE_ROLE_KEY` in `backend/reports.py`
  and `SUPABASE_KEY` in `backend/reply.py`. It is the first name everywhere now.
- The Gemini key is `GOOGLE_API_KEY` or `GEMINI_API_KEY`, which
  `backend/extract/gemini.py` has always accepted either of - but `reply.py`
  read only the second, so a deployment with the first had retrieval-backed
  drafting silently switched off with no model behind it.

Aliases themselves are fine; a name cannot be withdrawn once people have set it.
What is not fine is each module deciding for itself which names count, because
then "is it configured" has a different answer in every file. These functions
are that decision, made once.
"""
from __future__ import annotations

import os
from typing import Optional

from backend.extract.gemini import api_key as gemini_api_key

# One name. SUPABASE_KEY was briefly accepted as well, while the deployment still
# had it set; it is gone now that every environment uses the canonical name. A
# tuple rather than a bare string because the guard in tests/conftest.py clears
# every name in it, and that has to keep working if one is ever added back.
SUPABASE_SECRET_NAMES = ("SUPABASE_SERVICE_ROLE_KEY",)


def first_set(*names: str) -> Optional[str]:
    """The value of the first of `names` that has one, or None."""
    return next((os.environ[name] for name in names if os.environ.get(name)), None)


def supabase_url() -> Optional[str]:
    return os.environ.get("SUPABASE_URL") or None


def supabase_secret() -> Optional[str]:
    """The service role key, under whichever name it was set.

    It bypasses row-level security, so it belongs on a server and never in
    `frontend/config.js`. The browser gets the publishable key instead.
    """
    return first_set(*SUPABASE_SECRET_NAMES)


def gemini_key() -> Optional[str]:
    """Re-exported so callers have one import for "is this configured", rather
    than some reading the environment directly and disagreeing with the rest."""
    return gemini_api_key()


def supabase_configured() -> bool:
    return bool(supabase_url() and supabase_secret())
