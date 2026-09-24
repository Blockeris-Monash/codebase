"""The browser rule the deployed API quietly broke.

`allow_origins=["*"]` together with `allow_credentials=True` is invalid: the
CORS spec requires a browser to reject a wildcard origin on a credentialed
request. It appeared to work only because Starlette, seeing the pair, echoes
the caller's origin back instead of sending `*`.

Nothing here sends cookies or an Authorization header, so there were never any
credentials to allow.
"""
from __future__ import annotations

from backend.app import app


def cors_middleware():
    return next(m for m in app.user_middleware if "CORS" in m.cls.__name__)


def test_a_wildcard_origin_is_not_paired_with_credentials() -> None:
    options = cors_middleware().kwargs

    assert options["allow_credentials"] is False, (
        'allow_origins=["*"] with allow_credentials=True is invalid CORS; '
        "name the origins explicitly if credentials are ever needed")


def test_the_page_can_still_reach_the_api_from_anywhere() -> None:
    """The frontend is served from Vercel and the API from Render, so the
    wildcard itself has to stay."""
    assert "*" in cors_middleware().kwargs["allow_origins"]
