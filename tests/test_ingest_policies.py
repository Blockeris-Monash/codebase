"""Loading the policy manual twice leaves one copy of it (#147 B1).

Ingest used a plain insert, so every run doubled every chunk: retrieval then returned
one paragraph three times and the top three held fewer distinct passages. The model
and the database are faked, so this runs offline.
"""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

from backend.embeddings import EMBEDDING_DIMENSIONS
from tools import ingest_policies as ingest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "Test-Manual"
MANUAL = "Storage is free for five days.\n\n" * 3 + "Demurrage is billed daily after that.\n\n" * 3


class Table:
    """An in-memory policies table with just the calls ingest makes."""

    def __init__(self) -> None:
        self.rows: dict[str, dict] = {}   # content_hash -> row
        self._pending: tuple = ()

    def upsert(self, rows: list[dict], on_conflict: str = ""):
        assert on_conflict == "content_hash", "a plain insert duplicates on every run"
        self._pending = ("upsert", rows)
        return self

    def select(self, *_columns: str):
        self._pending = ("select",)
        return self

    def delete(self):
        self._pending = ("delete",)
        return self

    def eq(self, column: str, value: str):
        self._pending += (("eq", column, value),)
        return self

    def in_(self, column: str, values: list):
        self._pending += (("in", column, list(values)),)
        return self

    def execute(self):
        kind = self._pending[0]
        if kind == "upsert":
            for row in self._pending[1]:
                self.rows[row["content_hash"]] = row
            return SimpleNamespace(data=self._pending[1])
        if kind == "select":
            source = self._pending[1][2]
            return SimpleNamespace(data=[{"content_hash": h} for h, r in self.rows.items() if r["source"] == source])
        hashes = self._pending[1][2]
        for content_hash in hashes:
            self.rows.pop(content_hash, None)
        return SimpleNamespace(data=[])


def model() -> SimpleNamespace:
    def embed_content(**_kwargs):
        return SimpleNamespace(embeddings=[SimpleNamespace(values=[0.0] * EMBEDDING_DIMENSIONS)])
    return SimpleNamespace(models=SimpleNamespace(embed_content=embed_content))


def test_the_hash_is_stable_and_differs_by_source() -> None:
    assert ingest.content_hash(SOURCE, "a") == ingest.content_hash(SOURCE, "a")
    assert ingest.content_hash(SOURCE, "a") != ingest.content_hash("Other", "a")


def test_running_ingest_twice_keeps_one_copy_of_each_chunk() -> None:
    table = Table()
    db = SimpleNamespace(table=lambda _name: table)

    ingest.store(model(), db, MANUAL, SOURCE)
    first = dict(table.rows)
    ingest.store(model(), db, MANUAL, SOURCE)

    assert table.rows.keys() == first.keys()


def test_chunks_no_longer_in_the_manual_are_removed() -> None:
    table = Table()
    db = SimpleNamespace(table=lambda _name: table)

    ingest.store(model(), db, MANUAL + "Old rule: storage is free for ten days.", SOURCE)
    ingest.store(model(), db, MANUAL, SOURCE)

    assert not any("ten days" in row["content"] for row in table.rows.values())


def test_the_hash_in_the_migration_is_the_one_ingest_computes() -> None:
    """The migration backfills existing rows; a different recipe would duplicate them all once."""
    migration = next(ROOT.rglob("*_policies_ingest_once.sql")).read_text(encoding="utf-8")

    assert re.search(r"sha256\(convert_to\(coalesce\(source, ''\) \|\| E'\\n' \|\| content, 'UTF8'\)\)", migration)
