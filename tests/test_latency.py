"""Latency measurement: the pipeline call is faked, so this runs offline."""
from __future__ import annotations

import asyncio

from cli import latency


def entry(email_id: str, status: str) -> dict:
    doc = {"pairs": [["Shipper", "A"]], "title": "SHIPPING INSTRUCTION", "parse_status": "ok"}
    return {"id": email_id, "status": status, "defect_fields": [], "docs": {"SI": doc, "BL": {**doc, "title": "BILL OF LADING"}}}


def test_times_each_email_and_compares_the_live_status_with_the_saved_one() -> None:
    class Live:
        status = "OK"
        defect_fields: list = []

    async def fake_pipeline(payload, live):
        assert live is True
        return Live()

    runs = asyncio.run(latency.measure([entry("email_001", "OK"), entry("email_002", "MISMATCH")], fake_pipeline))

    assert [r["email_id"] for r in runs] == ["email_001", "email_002"]
    assert [r["same"] for r in runs] == [True, False]
    assert all(r["seconds"] >= 0 for r in runs)


def test_picks_a_repeatable_spread_of_ok_and_mismatch_emails() -> None:
    results = [entry(f"email_{n:03d}", "OK" if n % 2 else "MISMATCH") for n in range(1, 21)] + [entry("email_900", "NEEDS_REVIEW")]

    picked = latency.pick(results, 6)

    assert len(picked) == 6 and {e["status"] for e in picked} == {"OK", "MISMATCH"}
    assert [e["id"] for e in picked] == [e["id"] for e in latency.pick(results, 6)]
