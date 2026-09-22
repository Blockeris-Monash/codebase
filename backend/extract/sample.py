import json
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()  # <-- Reads .env

sys.path.insert(0, "tools")

from backend.extract.batch import extract_attachment
from backend.extract.ai import AiExtractor
from backend.extract.qwen import qwen_model


# 1. Output directory
out_dir = Path("results/extracts")
out_dir.mkdir(parents=True, exist_ok=True)

# 2. Attachments directory
attachments_dir = Path("data/attachments")
extractor = AiExtractor(qwen_model)

# 3. Target the 3 emails (SI and BL for each)
sample_files = [
    "email_025_SI.txt", "email_025_BL.txt",
    "email_064_SI.txt", "email_064_BL.txt",
    "email_055_SI.xlsx", "email_055_BL.docx"
]

print(f"Extracting {len(sample_files)} attachments with Qwen...")

for filename in sample_files:
    path = attachments_dir / filename
    out_file = out_dir / f"{path.stem}.json"

    if out_file.exists():
        print(f"⏩ {filename} already extracted, skipping.")
        continue

    print(f"⏳ Extracting {filename}...")
    result = extract_attachment(path, extractor)

    if result:
        out_file.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n")
        print(f"✅ Saved to {out_file}")
    else:
        print(f"❌ Failed to extract {filename}")

print("\nDone! Check results/extracts/ — you now have your cache for these 3 emails.")