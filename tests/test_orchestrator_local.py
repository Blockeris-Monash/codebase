"""Test the orchestrator pipeline against real local documents."""
import json
import sys
from pathlib import Path

# Add project root and tools/ to Python path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from fastapi.testclient import TestClient
from orchestrate import app
from read_documents import read_document

client = TestClient(app)

def test_email(email_id: str, si_filename: str, bl_filename: str):
    attachments_dir = ROOT / "data" / "attachments"
    si_path = attachments_dir / si_filename
    bl_path = attachments_dir / bl_filename

    print(f"\n{'=' * 60}")
    print(f"Testing {email_id}:")
    print(f"  SI: {si_path.name}")
    print(f"  BL: {bl_path.name}")
    print(f"{'=' * 60}")

    # 1. Read attachments into label-value pairs using read_documents.py
    si_status, si_pairs = read_document(si_path)
    bl_status, bl_pairs = read_document(bl_path)

    print(f"  Ingestion Status -> SI: {si_status} ({len(si_pairs)} pairs), BL: {bl_status} ({len(bl_pairs)} pairs)")

    # 2. Build payload
    payload = {
        "email_id": email_id,
        "si_pairs": si_pairs,
        "bl_pairs": bl_pairs
    }

    # 3. Call orchestrator
    response = client.post("/extract-clean-compare", json=payload)

    if response.status_code != 200:
        print(f"❌ Error {response.status_code}: {response.text}")
        return

    report = response.json()
    print(f"\n📊 Result: {report['match_status']} (Discrepancies: {report['discrepancies_count']})")
    print(f"{'-' * 60}")
    for row in report["rows"]:
        verdict = row["verdict"]
        icon = "✅" if verdict == "Match" else "❌"
        print(f"  {icon} [{verdict:<8}] {row['field']:<18} | SI: {row['si_norm']} | BL: {row['bl_norm']}")
        if row.get("notes"):
            print(f"     └── Note: {row['notes']}")

if __name__ == "__main__":
    # Test 1: email_025 (Expected: MISMATCH on port_of_discharge & container_count)
    test_email("email_025", "email_025_SI.txt", "email_025_BL.txt")

    # Test 2: email_064 (Expected: CLEAN_MATCH across all fields)
    test_email("email_064", "email_064_SI.txt", "email_064_BL.txt")

    # Test 3: Cross-format test (Word BL against Excel SI!)
    test_email("email_055", "email_055_SI.xlsx", "email_055_BL.docx")