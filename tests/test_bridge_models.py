"""Test for models endpoint."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from server.app import app


def test_models():
    client = TestClient(app)

    # 1. Test GET /v1/models
    response = client.get("/v1/models")
    assert response.status_code == 200, f"Failed: {response.text}"
    data = response.json()
    assert data["object"] == "list"
    assert len(data["data"]) > 0

    model_ids = [m["id"] for m in data["data"]]
    print(f"Verified {len(model_ids)} models in /v1/models.")
    assert "gemini-3.8-flash-medium" in model_ids or "gemini-3.8-flash-low" in model_ids
    assert "gpt-ss" in model_ids  # alias

    # 2. Test GET /v1/models/{model_id}
    model_response = client.get("/v1/models/gemini-3.8-flash-medium")
    assert model_response.status_code == 200
    model_data = model_response.json()
    assert model_data["object"] == "model"
    assert model_data["id"] == "gemini-3.8-flash-medium"
    print("Models endpoint test PASSED successfully!")


if __name__ == "__main__":
    test_models()
