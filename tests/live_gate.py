"""The gate on every test that reaches a model over the network.

A key alone is not consent. Someone with a Gemini key from another project, or
a Qwen key for a different gateway, had unrelated tests unskip themselves,
fire live calls and fail - a red suite that says nothing about this repository.
QWEN_BASE_URL defaults to a proxy only this team can reach, so a judge's own key
fails against infrastructure they have no access to.

So these run only when someone asks for them by name.
"""
from __future__ import annotations

import os

import pytest

OPT_IN = "SHIP_HAPPENS_LIVE"
REASON = (f"live model test - set {OPT_IN}=1 and the matching key to run it. "
          "Skipped by default so an unrelated key in the environment cannot "
          "turn this into a network call.")


def needs_live(*keys: str) -> pytest.MarkDecorator:
    """Skip unless the opt-in is set and at least one of `keys` has a value."""
    wanted = os.environ.get(OPT_IN) == "1" and any(os.environ.get(k) for k in keys)
    return pytest.mark.skipif(not wanted, reason=REASON)
