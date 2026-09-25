import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from backend.app import app

client = TestClient(app)

@patch("backend.reply.refine_rag_reply")
def test_refine_endpoint(mock_refine_rag_reply):
    mock_refine_rag_reply.return_value = "This is a refined AI reply."
    
    payload = {
        "email": {
            "email_id": "test_id",
            "from_email": "sender@test.com",
            "subject": "Test Subject",
            "body": "Test Body",
            "attachments": []
        },
        "current_draft": "This is a draft.",
        "instruction": "Make it better."
    }
    
    response = client.post("/refine", json=payload)
    assert response.status_code == 200
    assert response.json() == {"draft_reply": "This is a refined AI reply."}
