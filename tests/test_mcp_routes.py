"""Unit tests for Model Bridge MCP endpoints."""

import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
import pytest
from server.app import app


@pytest.mark.anyio
async def test_mcp_initialize():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        req = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {}
        }
        res = await client.post("/mcp", json=req)
        assert res.status_code == 200
        data = res.json()
        assert data["id"] == 1
        assert "result" in data
        assert data["result"]["serverInfo"]["name"] == "autono-browser-mcp"
        assert "protocolVersion" in data["result"]


@pytest.mark.anyio
async def test_mcp_tools_list():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        req = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {}
        }
        res = await client.post("/mcp", json=req)
        assert res.status_code == 200
        data = res.json()
        assert data["id"] == 2
        tools = data["result"]["tools"]
        tool_names = [t["name"] for t in tools]
        assert "browser_task" in tool_names
        assert "browser_navigate" in tool_names
        assert "browser_get_active_tab" in tool_names
        assert "browser_screenshot" in tool_names


@pytest.mark.anyio
async def test_mcp_status_endpoint():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/mcp/status")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "online"
        assert "browser_connected" in data
        assert "tools_count" in data
