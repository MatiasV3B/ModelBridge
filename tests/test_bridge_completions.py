"""Test for chat completions and responses endpoints."""

import sys
import json
import asyncio
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
import pytest
from server.app import app


@pytest.mark.anyio
async def test_completions():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Non-streaming Chat Completion
        print("Testing POST /v1/chat/completions (non-streaming)...")
        payload = {
            "model": "gemini-3.8-flash-low",
            "messages": [
                {"role": "user", "content": "Say the exact word 'PONG' and nothing else."}
            ],
            "stream": False,
        }
        res = await client.post("/v1/chat/completions", json=payload, timeout=30.0)
        assert res.status_code == 200, f"Error: {res.text}"
        data = res.json()
        assert data["object"] == "chat.completion"
        assert len(data["choices"]) > 0
        content = data["choices"][0]["message"]["content"]
        print(f"Non-streaming response: {content.strip()!r}")
        assert "usage" in data
        print("[PASS] Non-streaming chat completion PASSED.")

        # 2. Streaming Chat Completion
        print("Testing POST /v1/chat/completions (streaming SSE)...")
        payload["stream"] = True
        payload["messages"] = [{"role": "user", "content": "Count '1 2 3' and nothing else."}]

        stream_text = ""
        received_done = False
        async with client.stream("POST", "/v1/chat/completions", json=payload, timeout=30.0) as stream_res:
            assert stream_res.status_code == 200
            async for line in stream_res.aiter_lines():
                if not line:
                    continue
                if line == "data: [DONE]":
                    received_done = True
                    break
                if line.startswith("data: "):
                    raw_json = line[6:]
                    chunk = json.loads(raw_json)
                    assert chunk["object"] == "chat.completion.chunk"
                    delta = chunk["choices"][0]["delta"]
                    if "content" in delta:
                        stream_text += delta["content"]

        print(f"Streaming accumulated text: {stream_text.strip()!r}")
        assert received_done, "Stream did not end with [DONE]"
        print("[PASS] Streaming chat completion PASSED.")

        # 3. Responses API
        print("Testing POST /v1/responses...")
        resp_payload = {
            "model": "gemini-3.8-flash-low",
            "input": "Say 'OK' and nothing else.",
            "stream": False,
        }
        resp_res = await client.post("/v1/responses", json=resp_payload, timeout=30.0)
        assert resp_res.status_code == 200, f"Error: {resp_res.text}"
        r_data = resp_res.json()
        assert r_data["object"] == "response"
        assert r_data["status"] == "completed"
        output_txt = r_data["output"][0]["content"][0]["text"]
        print(f"Responses API output: {output_txt.strip()!r}")
        print("[PASS] Responses API PASSED.")

    print("\nAll chat completion tests PASSED successfully!")


if __name__ == "__main__":
    asyncio.run(test_completions())
