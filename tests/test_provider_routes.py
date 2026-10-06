"""Test provider-specific prefixed routes (/antigravity, /claude, /openai)."""

import pytest
import httpx
from server.app import app


@pytest.mark.anyio
async def test_provider_models_routes():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Antigravity models
        res_antigravity = await client.get("/antigravity/v1/models")
        assert res_antigravity.status_code == 200
        antigravity_data = res_antigravity.json()["data"]
        assert len(antigravity_data) > 0
        # Check all models belong to antigravity / gemini / oss
        for m in antigravity_data:
            mid = m["id"].lower()
            assert mid.startswith("gemini-") or "oss" in mid or "gpt-ss" in mid or "antigravity" in mid or "claude" in mid

        # 2. Claude models
        res_claude = await client.get("/claude/v1/models")
        assert res_claude.status_code == 200
        claude_data = res_claude.json()["data"]
        assert len(claude_data) > 0
        for m in claude_data:
            mid = m["id"].lower()
            assert "claude" in mid or "sonnet" in mid or "opus" in mid or "haiku" in mid or "fable" in mid

        # 3. OpenAI models
        res_openai = await client.get("/openai/v1/models")
        assert res_openai.status_code == 200
        openai_data = res_openai.json()["data"]
        assert len(openai_data) > 0
        for m in openai_data:
            mid = m["id"].lower()
            assert "gpt" in mid or "codex" in mid or "o3" in mid

        # 4. Root /v1/models (backward compatibility)
        res_root = await client.get("/v1/models")
        assert res_root.status_code == 200
        root_data = res_root.json()["data"]
        assert len(root_data) >= len(antigravity_data)
