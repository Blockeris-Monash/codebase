"""The embedding is the size the policies column holds (#147 B1).

`0003` declares vector(768) and gemini-embedding-001 returns 3072 dimensions unless
asked for fewer, so every insert and every query failed, retrieval returned [] and
every draft said no policy was found.
"""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend import embeddings, reply
from backend.embeddings import EMBEDDING_DIMENSIONS, EmbeddingTask, embed

ROOT = Path(__file__).resolve().parents[1]
VECTOR_COLUMN = re.compile(r"embedding\s+vector\((\d+)\)", re.I)


class Models:
    """Records what embed_content was asked for, and answers with `size` numbers."""

    def __init__(self, size: int = EMBEDDING_DIMENSIONS) -> None:
        self.size = size
        self.calls: list[dict] = []

    def embed_content(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(embeddings=[SimpleNamespace(values=[0.1] * self.size)])


def client(size: int = EMBEDDING_DIMENSIONS) -> SimpleNamespace:
    return SimpleNamespace(models=Models(size))


def test_the_dimension_matches_the_column_the_migration_declares() -> None:
    migration = next(ROOT.rglob("*_rag_embeddings.sql")).read_text(encoding="utf-8")

    assert {int(n) for n in VECTOR_COLUMN.findall(migration)} == {EMBEDDING_DIMENSIONS}


@pytest.mark.parametrize("task", list(EmbeddingTask))
def test_the_model_is_asked_for_the_column_size_and_the_task(task: EmbeddingTask) -> None:
    fake = client()

    vector = embed(fake, "free storage days", task)

    config = fake.models.calls[0]["config"]
    assert len(vector) == EMBEDDING_DIMENSIONS
    assert config.output_dimensionality == EMBEDDING_DIMENSIONS
    assert config.task_type == task.value
    assert fake.models.calls[0]["model"] == embeddings.EMBEDDING_MODEL


def test_a_vector_of_the_wrong_size_is_refused_before_it_reaches_the_database() -> None:
    with pytest.raises(embeddings.WrongEmbeddingSize):
        embed(client(size=3072), "free storage days", EmbeddingTask.Query)


def test_retrieval_embeds_the_query_at_the_column_size(monkeypatch) -> None:
    fake, asked = client(), {}

    class Rpc:
        def execute(self):
            return SimpleNamespace(data=[])

    def rpc(name: str, params: dict) -> Rpc:
        asked.update(params)
        return Rpc()

    monkeypatch.setattr(reply, "client", fake)
    monkeypatch.setattr(reply, "supabase", SimpleNamespace(rpc=rpc))

    reply.retrieve_policies("how many free storage days")

    assert fake.models.calls[0]["config"].task_type == EmbeddingTask.Query.value
    assert len(asked["query_embedding"]) == EMBEDDING_DIMENSIONS
