"""The service's in-memory state is bounded (#147 B4).

MAILBOXES, ORIGINALS and FAILURES grew with every message ever checked and were never
evicted, bodies and all, for the life of the process.
"""
from __future__ import annotations

import logging

import pytest

from backend import app as app_module
from backend.state import BoundedStore


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_an_entry_expires_after_its_time() -> None:
    clock = Clock()
    store = BoundedStore(ttl=10, cap=5, clock=clock)
    store["a"] = 1

    clock.now = 9
    assert store.get("a") == 1
    clock.now = 20
    assert store.get("a") is None and len(store) == 0


def test_reading_an_entry_keeps_it() -> None:
    clock = Clock()
    store = BoundedStore(ttl=10, cap=5, clock=clock)
    store["a"] = 1
    for now in (8, 16, 24):
        clock.now = now
        assert store["a"] == 1


def test_past_the_cap_the_least_recently_used_goes_first() -> None:
    store = BoundedStore(ttl=100, cap=2, clock=Clock())
    store["a"], store["b"] = 1, 2
    store["a"]          # a is now more recent than b
    store["c"] = 3

    assert set(store) == {"a", "c"}


def test_a_mailbox_is_created_bounded() -> None:
    boxes: dict = {}

    box = app_module.mailbox_of(boxes, "a@ours.example")

    assert isinstance(box, BoundedStore) and boxes["a@ours.example"] is box


@pytest.mark.parametrize("workers, warned", [("1", False), ("2", True), (None, False)])
def test_a_second_worker_is_announced(monkeypatch, caplog, workers: str | None, warned: bool) -> None:
    if workers is None:
        monkeypatch.delenv("WEB_CONCURRENCY", raising=False)
    else:
        monkeypatch.setenv("WEB_CONCURRENCY", workers)

    with caplog.at_level(logging.WARNING, logger="backend.app"):
        app_module.say_what_is_switched_on()

    assert any("WEB_CONCURRENCY" in r.getMessage() for r in caplog.records) is warned
