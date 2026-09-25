"""One way to embed text for the policies table, shared by ingest and retrieval.

The column is vector(768) (migration 0003), and gemini-embedding-001 answers with 3072
numbers unless it is asked for fewer, so both sides must ask for the same size. 768
rather than migrating the column: pgvector cannot index more than 2,000 dimensions, and
the model is trained so a shortened vector keeps most of its quality.
"""
from __future__ import annotations

from enum import StrEnum

from google import genai
from google.genai import types

EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_DIMENSIONS = 768


class EmbeddingTask(StrEnum):
    """What the vector is for; Google tunes a stored passage and a question differently."""
    Document = "RETRIEVAL_DOCUMENT"
    Query = "RETRIEVAL_QUERY"


class WrongEmbeddingSize(ValueError):
    """The model answered with a vector the policies column cannot hold."""


def embed(client: genai.Client, text: str, task: EmbeddingTask) -> list[float]:
    response = client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=text,
        config=types.EmbedContentConfig(output_dimensionality=EMBEDDING_DIMENSIONS, task_type=task.value),
    )
    vector = list(response.embeddings[0].values)
    if len(vector) != EMBEDDING_DIMENSIONS:
        raise WrongEmbeddingSize(f"{EMBEDDING_MODEL} returned {len(vector)} dimensions, "
                                 f"the policies column holds {EMBEDDING_DIMENSIONS}")

    return vector
