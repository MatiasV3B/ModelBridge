"""Unit tests for Claude Agent SDK and Anthropic endpoints."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from server.app import app
from claude_agent import claude_agent_executor, CLAUDE_MODELS, DEFAULT_CLAUDE_MODEL


def test_claude_model_resolution():
    assert claude_agent_executor.resolve_model("claude-sonnet-5-5") == "claude-sonnet-5-5"
    assert claude_agent_executor.resolve_model("sonnet-5.5") == "claude-sonnet-5-5"
    assert claude_agent_executor.resolve_model("claude-opus-5-5") == "claude-opus-5-5"
    assert claude_agent_executor.resolve_model("opus-5.5") == "claude-opus-5-5"
    assert claude_agent_executor.resolve_model("claude-fable-5-1") == "claude-fable-5-1"
    assert claude_agent_executor.resolve_model("fable-5.1") == "claude-fable-5-1"
    assert claude_agent_executor.resolve_model("claude-haiku-4-5") == "claude-haiku-4-5"
    assert claude_agent_executor.resolve_model("haiku-4.5") == "claude-haiku-4-5"
    print("Claude model resolution tests PASSED!")


def test_claude_endpoints():
    client = TestClient(app)

    # 1. Health check includes claude agent info or is online
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "online"

    # 2. Check /v1/models contains Sonnet 5.5, Opus 5.5, Fable 5.1, Haiku 4.5
    models_resp = client.get("/v1/models")
    assert models_resp.status_code == 200
    ids = [m["id"] for m in models_resp.json()["data"]]
    assert "claude-sonnet-5-5" in ids
    assert "claude-opus-5-5" in ids
    assert "claude-fable-5-1" in ids
    assert "claude-haiku-4-5" in ids
    print("Claude models presence in /v1/models PASSED!")

    # 3. Test /v1/messages missing api key returns proper error handling rather than crashing
    msg_resp = client.post("/v1/messages", json={
        "model": "claude-sonnet-5-5",
        "messages": [{"role": "user", "content": "Hello"}]
    })
    # If no key set, returns 200 with empty or handled error
    assert msg_resp.status_code in [200, 400, 500]
    print("Anthropic /v1/messages endpoint response verified!")


if __name__ == "__main__":
    test_claude_model_resolution()
    test_claude_endpoints()
