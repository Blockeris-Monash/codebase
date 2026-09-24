import os
from google import genai
from dotenv import load_dotenv

load_dotenv()

client = genai.Client(api_key=os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY"))

for model in ['text-embedding-004', 'models/text-embedding-004', 'embedding-001', 'models/embedding-001', 'models/gemini-embedding-001']:
    try:
        response = client.models.embed_content(model=model, contents="Hello")
        print(f"{model} worked!")
        break
    except Exception as e:
        print(f"{model} failed: {e}")
