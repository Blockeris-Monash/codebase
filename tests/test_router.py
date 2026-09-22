"""Test the 1-click router endpoint (POST /process-email) across different categories."""
import json
import os
import sys
from pathlib import Path

import pytest

from tests.live_gate import needs_live

# Add project root to sys.path so 'backend' is found
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from backend.app import app

client = TestClient(app)

def load_inbox_email(email_id: str) -> dict:
    inbox_file = ROOT / "data" / "inbox" / f"{email_id}.json"
    return json.loads(inbox_file.read_text(encoding="utf-8"))


@needs_live("QWEN_API_KEY")
def test_router():
    print(f"\n{'=' * 70}")
    print("RUNNING ROUTER END-TO-END TESTS (POST /process-email)")
    print(f"{'=' * 70}")

    # 1. Test Non-Comparison: SI_REQUEST (email_007)
    email_007 = load_inbox_email("email_007")
    resp_007 = client.post("/process-email", json=email_007)
    assert resp_007.status_code == 200, f"Failed 007: {resp_007.text}"
    data_007 = resp_007.json()

    print("\n[Test 1] email_007 (Expected: SI_REQUEST -> Pass-Through)")
    print(f"  Category: {data_007['ClassificationResult']['category']}")
    print(f"  ComparisonResult: {data_007['ComparisonResult']}")
    print(f"  SubmissionEntry: {data_007['SubmissionEntry']}")
    assert data_007["ClassificationResult"]["category"] == "SI_REQUEST"
    assert data_007["ComparisonResult"] is None
    assert data_007["SubmissionEntry"]["status"] == "OK"

    # 2. Test Non-Comparison: SPAM (email_015)
    email_015 = load_inbox_email("email_015")
    resp_015 = client.post("/process-email", json=email_015)
    assert resp_015.status_code == 200, f"Failed 015: {resp_015.text}"
    data_015 = resp_015.json()

    print("\n[Test 2] email_015 (Expected: SPAM -> Pass-Through)")
    print(f"  Category: {data_015['ClassificationResult']['category']}")
    print(f"  ComparisonResult: {data_015['ComparisonResult']}")
    assert data_015["ClassificationResult"]["category"] == "SPAM"
    assert data_015["ComparisonResult"] is None

    # 3. Test Comparison with Mismatch: BL_COMPARISON (email_025)
    email_025 = load_inbox_email("email_025")
    resp_025 = client.post("/process-email", json=email_025)
    assert resp_025.status_code == 200, f"Failed 025: {resp_025.text}"
    data_025 = resp_025.json()

    print("\n[Test 3] email_025 (Expected: BL_COMPARISON -> Mismatch)")
    print(f"  Category: {data_025['ClassificationResult']['category']}")
    print(f"  Comparison Status: {data_025['ComparisonResult']['status']}")
    print(f"  Defect Fields: {data_025['ComparisonResult']['defect_fields']}")
    assert data_025["ClassificationResult"]["category"] == "BL_COMPARISON"
    assert data_025["ComparisonResult"] is not None
    assert "port_of_discharge" in data_025["ComparisonResult"]["defect_fields"]

    print(f"\n{'=' * 70}")
    print("ALL ROUTER TESTS PASSED!")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    test_router()