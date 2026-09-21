"""Test the orchestrator pipeline with both Cached and Live Qwen AI modes."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from fastapi.testclient import TestClient
from orchestrate import app
from read_documents import read_document

client = TestClient(app)

def run_test(email_id: str, si_file: str, bl_file: str, live: bool = False):
    mode = "🔴 LIVE QWEN AI" if live else "⚡ INSTANT CACHE"
    print(f"\n{'=' * 65}")
    print(f"Testing {email_id} [{mode}]")
    print(f"{'=' * 65}")

    attachments = ROOT / "data" / "attachments"
    si_status, si_pairs = read_document(attachments / si_file)
    bl_status, bl_pairs = read_document(attachments / bl_file)

    payload = {
        "email_id": email_id,
        "si_pairs": si_pairs,
        "bl_pairs": bl_pairs
    }

    # Pass live query parameter: ?live=true or ?live=false
    response = client.post(f"/extract-clean-compare?live={str(live).lower()}", json=payload)

    if response.status_code != 200:
        print(f"❌ HTTP Error {response.status_code}: {response.text}")
        return

    report = response.json()
    print(f"Result: {report['match_status']} (Discrepancies: {report['discrepancies_count']})")
    print(f"{'-' * 65}")
    for row in report["rows"]:
        icon = "✅" if row["verdict"] == "Match" else "❌"
        print(f"  {icon} [{row['verdict']:<8}] {row['field']:<18} | SI: {row['si_norm']} | BL: {row['bl_norm']}")
        if row.get("notes"):
            print(f"     └── Note: {row['notes']}")

if __name__ == "__main__":
    # 1. Test Instant Cached Mode (using Milk's pre-extracted results)
    print("--- 1. TESTING CACHED HYBRID PATH ---")
    run_test("email_025", "email_025_SI.txt", "email_025_BL.txt", live=False)

    # 2. Test Live Qwen AI Path (Calls Milk's Qwen API on Render)
    print("\n--- 2. TESTING LIVE QWEN AI PATH ---")
    print("(Note: If Render was sleeping, this first call might take 30-40s...)")
    run_test("email_025", "email_025_SI.txt", "email_025_BL.txt", live=True)

# test with live= false
# if __name__ == "__main__":
#     # Test 1: email_025 (Expected: Mismatch on port_of_discharge & container_count)
#     run_test("email_025", "email_025_SI.txt", "email_025_BL.txt", live=False)

#     # Test 2: email_064 (Expected: Clean match)
#     run_test("email_064", "email_064_SI.txt", "email_064_BL.txt", live=False)

#     # Test 3: Mixed format (Excel SI vs Word BL)
#     run_test("email_055", "email_055_SI.xlsx", "email_055_BL.docx", live=False)