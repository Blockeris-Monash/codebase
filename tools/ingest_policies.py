"""Load the company policy manual into Supabase, where reply drafting retrieves it.

Run from the repository root, after migration 0008:

    python -m tools.ingest_policies

Safe to run again. Each chunk is keyed by a hash of its source and its text, so a
re-run updates rows in place instead of adding a second copy, and chunks that are no
longer in the manual are removed.
"""
import hashlib
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader
from supabase import Client, create_client

from backend.embeddings import EmbeddingTask, embed

ROOT = Path(__file__).resolve().parents[1]
MANUAL = ROOT / "data" / "policies" / "GlobeTrans-International-Policy-and-Procedures-Manual-update-Nov2017.pdf"
SOURCE = "GlobeTrans-International-Policy-and-Procedures-Manual"
TABLE = "policies"
CHUNK_CHARS = 1000
CHUNK_OVERLAP_CHARS = 200
# Rows per request: each carries a 768-number vector, and one request for the whole manual is megabytes.
BATCH = 50


def content_hash(source: str, chunk: str) -> str:
    """The row's identity. Migration 0008 backfills old rows with this same recipe."""
    return hashlib.sha256(f"{source}\n{chunk}".encode("utf-8")).hexdigest()


def text_of(pdf: Path) -> str:
    pages = (page.extract_text() for page in PdfReader(str(pdf)).pages)
    return "".join(f"{text}\n" for text in pages if text)


def chunks_of(text: str) -> list[str]:
    splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_CHARS, chunk_overlap=CHUNK_OVERLAP_CHARS,
                                              length_function=len, is_separator_regex=False)
    # A chunk repeated in the manual is one row; twice in one upsert, Postgres refuses the batch.
    return list(dict.fromkeys(splitter.split_text(text)))


def batches(items: list, size: int = BATCH) -> list[list]:
    return [items[start:start + size] for start in range(0, len(items), size)]


def store(model: genai.Client, db: Client, text: str, source: str) -> int:
    """Embed every chunk of `text`, upsert them, and delete this source's stale chunks."""
    rows = [{"content": chunk, "source": source, "content_hash": content_hash(source, chunk),
             "metadata": {"source": source, "chunk_index": index},
             "embedding": embed(model, chunk, EmbeddingTask.Document)}
            for index, chunk in enumerate(chunks_of(text))]
    for batch in batches(rows):
        db.table(TABLE).upsert(batch, on_conflict="content_hash").execute()

    kept = {row["content_hash"] for row in rows}
    stored = db.table(TABLE).select("content_hash").eq("source", source).execute().data
    stale = [row["content_hash"] for row in stored if row["content_hash"] not in kept]
    for batch in batches(stale):
        db.table(TABLE).delete().in_("content_hash", batch).execute()

    return len(rows)


def main() -> None:
    load_dotenv()
    url, key, gemini_key = (os.environ.get(name) for name in ("SUPABASE_URL", "SUPABASE_KEY", "GEMINI_API_KEY"))
    if not (url and key and gemini_key):
        sys.exit("Set SUPABASE_URL, SUPABASE_KEY and GEMINI_API_KEY in .env first.")
    if not MANUAL.exists():
        sys.exit(f"{MANUAL} not found.")

    stored = store(genai.Client(api_key=gemini_key), create_client(url, key), text_of(MANUAL), SOURCE)
    print(f"{stored} chunks of {MANUAL.name} are in {TABLE}.")


if __name__ == "__main__":
    main()
