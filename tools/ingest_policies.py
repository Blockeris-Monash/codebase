import os
import sys
from pathlib import Path
from pypdf import PdfReader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from supabase import create_client, Client
from google import genai
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("Error: SUPABASE_URL and SUPABASE_KEY must be set in .env")
    sys.exit(1)

if not GEMINI_API_KEY:
    print("Error: GEMINI_API_KEY must be set in .env")
    sys.exit(1)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
client = genai.Client(api_key=GEMINI_API_KEY)

def extract_text_from_pdf(pdf_path: str) -> str:
    print(f"Reading {pdf_path}...")
    reader = PdfReader(pdf_path)
    text = ""
    for page in reader.pages:
        extracted = page.extract_text()
        if extracted:
            text += extracted + "\n"
    return text

def ingest():
    # 1. Extract text
    pdf_path = Path(__file__).resolve().parents[1] / "data" / "policies" / "GlobeTrans-International-Policy-and-Procedures-Manual-update-Nov2017.pdf"
    if not pdf_path.exists():
        print(f"Error: {pdf_path} not found.")
        return
    text = extract_text_from_pdf(str(pdf_path))

    # 2. Chunk text using Recursive/Mixed Chunking
    print("Chunking text...")
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        length_function=len,
        is_separator_regex=False,
    )
    chunks = text_splitter.split_text(text)
    print(f"Created {len(chunks)} chunks.")

    # 3. Embed and store
    print("Embedding and storing in Supabase...")
    for i, chunk in enumerate(chunks):
        response = client.models.embed_content(
            model='gemini-embedding-001',
            contents=chunk,
        )
        embedding = response.embeddings[0].values
        
        # Insert into Supabase
        data, count = supabase.table('policies').insert({
            'content': chunk,
            'metadata': {'source': 'GlobeTrans-International-Policy-and-Procedures-Manual', 'chunk_index': i},
            'embedding': embedding
        }).execute()
        
    print("Ingestion complete.")

if __name__ == "__main__":
    ingest()
