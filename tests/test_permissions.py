"""Permission mode and hard limits of the Bridge (core/permissions.py and the routes that enforce them)."""

import sys
import subprocess
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
import pytest

from core import permissions
from core.config import bridge_config
from server.app import app


@pytest.fixture
def isolated_config(monkeypatch):
    """Never touch the real ~/.antigravity_bridge/config.json while testing."""
    monkeypatch.setattr(bridge_config, "save", lambda: None)
    monkeypatch.setattr(bridge_config, "permission_mode", "ask")
    monkeypatch.setattr(bridge_config, "code_execution", "off")
    monkeypatch.delenv("BRIDGE_CODE_EXECUTION", raising=False)
    return bridge_config


def _client():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


# ---- the flags handed to the Antigravity CLI ----

def test_ask_is_the_default_and_never_skips_permissions():
    assert permissions.DEFAULT_MODE == "ask"
    assert permissions.agy_permission_flags("ask") == ["--sandbox"]
    assert permissions.agy_permission_flags(None) == ["--sandbox"]
    assert permissions.agy_permission_flags("garbage") == ["--sandbox"]


@pytest.mark.parametrize("mode", ["auto", "none"])
def test_auto_and_none_skip_prompts_but_stay_sandboxed(mode):
    flags = permissions.agy_permission_flags(mode)
    assert "--dangerously-skip-permissions" in flags
    assert "--sandbox" in flags


@pytest.mark.parametrize("mode", list(permissions.MODES) + [None, "", "garbage"])
def test_sandbox_is_on_in_every_mode(mode):
    assert "--sandbox" in permissions.agy_permission_flags(mode)


def test_engine_builds_the_cli_command_from_the_mode(monkeypatch, isolated_config):
    import asyncio
    from core.bridge_engine import bridge_engine

    seen = {}

    async def fake_exec(*cmd, **kwargs):
        seen["cmd"] = list(cmd)
        raise RuntimeError("stop here")

    monkeypatch.setattr(bridge_engine.config, "agy_binary_path", sys.executable)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    async def run(mode):
        isolated_config.permission_mode = mode
        seen.clear()
        with pytest.raises(RuntimeError, match="stop here"):
            async for _ in bridge_engine._stream_cli("hi", "gemini-3.8-flash-low", []):
                pass
        return seen["cmd"]

    assert "--dangerously-skip-permissions" not in asyncio.run(run("ask"))
    assert "--dangerously-skip-permissions" in asyncio.run(run("auto"))
    assert "--sandbox" in asyncio.run(run("ask"))
    assert "--sandbox" in asyncio.run(run("none"))


# ---- who may change the mode ----

@pytest.mark.parametrize("origin,ok", [
    (None, True),
    ("chrome-extension://abcdefghijklmnop", True),
    ("moz-extension://1234", True),
    ("https://evil.example", False),
    ("http://localhost:3000", False),
    ("null", False),
])
def test_only_extensions_may_change_the_mode(origin, ok):
    assert permissions.is_trusted_origin(origin) is ok


@pytest.mark.anyio
async def test_get_permissions_reports_default_and_hard_limits(isolated_config):
    async with _client() as c:
        data = (await c.get("/api/permissions")).json()
    assert data["mode"] == "ask"
    assert data["modes"] == ["ask", "auto", "none"]
    assert data["hard_limits"] == {"cli_sandbox": True, "shutdown": False, "hibernate": False, "code_execution": "off"}


@pytest.mark.anyio
async def test_extension_can_change_the_mode(isolated_config):
    async with _client() as c:
        res = await c.post("/api/permissions", json={"mode": "auto"}, headers={"Origin": "chrome-extension://abc"})
    assert res.status_code == 200
    assert res.json()["mode"] == "auto"
    assert isolated_config.permission_mode == "auto"


@pytest.mark.anyio
async def test_a_web_page_cannot_change_the_mode(isolated_config):
    async with _client() as c:
        res = await c.post("/api/permissions", json={"mode": "none"}, headers={"Origin": "https://evil.example"})
    assert res.status_code == 403
    assert isolated_config.permission_mode == "ask"


@pytest.mark.anyio
async def test_unknown_mode_is_rejected(isolated_config):
    async with _client() as c:
        res = await c.post("/api/permissions", json={"mode": "yolo"})
    assert res.status_code == 422
    assert isolated_config.permission_mode == "ask"


# ---- hard limit: the computer is never shut down or hibernated ----

@pytest.mark.anyio
@pytest.mark.parametrize("body", [{}, {"action": "shutdown"}, {"action": "hibernate"}, {"action": "sleep", "delay_seconds": 0}])
@pytest.mark.parametrize("mode", ["ask", "auto", "none"])
async def test_shutdown_is_refused_in_every_mode(monkeypatch, isolated_config, mode, body):
    isolated_config.permission_mode = mode

    def boom(*a, **k):
        raise AssertionError("a shutdown process must never be started")

    monkeypatch.setattr(subprocess, "Popen", boom)
    monkeypatch.setattr(subprocess, "run", boom)
    async with _client() as c:
        res = await c.post("/api/power/shutdown", json=body)
    assert res.status_code == 403
    assert res.json()["detail"]["error"] == "blocked_by_policy"


# ---- hard limit: code runs only when turned on locally ----

@pytest.mark.anyio
@pytest.mark.parametrize("mode", ["ask", "auto", "none"])
async def test_code_execution_is_off_by_default_in_every_mode(isolated_config, mode):
    isolated_config.permission_mode = mode
    async with _client() as c:
        res = await c.post("/api/code/execute", json={"code": "print(1)"})
    assert res.status_code == 403
    assert res.json()["detail"]["error"] == "code_execution_disabled"


@pytest.mark.anyio
async def test_the_mode_endpoint_cannot_turn_code_execution_on(isolated_config):
    async with _client() as c:
        await c.post("/api/permissions", json={"mode": "none", "code_execution": "isolated"})
        res = await c.post("/api/code/execute", json={"code": "print(1)"})
    assert res.status_code == 403


def test_policy_needs_the_local_setting_or_environment(monkeypatch):
    monkeypatch.delenv("BRIDGE_CODE_EXECUTION", raising=False)
    assert permissions.code_execution_policy(None) == "off"
    assert permissions.code_execution_policy("off") == "off"
    assert permissions.code_execution_policy("anything else") == "off"
    assert permissions.code_execution_policy("isolated") == "isolated"
    monkeypatch.setenv("BRIDGE_CODE_EXECUTION", "isolated")
    assert permissions.code_execution_policy("off") == "isolated"


@pytest.mark.anyio
async def test_isolated_python_runs_without_secrets_in_an_empty_folder(monkeypatch, isolated_config):
    isolated_config.code_execution = "isolated"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-should-not-leak")
    code = "import os; print(os.environ.get('ANTHROPIC_API_KEY')); print(os.listdir('.'))"
    async with _client() as c:
        res = await c.post("/api/code/execute", json={"code": code, "language": "python"})
    data = res.json()
    assert res.status_code == 200, data
    assert data["returncode"] == 0, data
    assert "sk-test-should-not-leak" not in data["stdout"]
    assert data["stdout"].splitlines() == ["None", "[]"]


@pytest.mark.anyio
@pytest.mark.parametrize("language", ["powershell", "bash", "sh", "ps1", "cmd"])
async def test_shells_are_never_available(isolated_config, language):
    isolated_config.code_execution = "isolated"
    async with _client() as c:
        res = await c.post("/api/code/execute", json={"code": "echo hi", "language": language})
    assert res.status_code == 400


@pytest.mark.anyio
async def test_infinite_loop_is_stopped_by_the_timeout(isolated_config):
    isolated_config.code_execution = "isolated"
    async with _client() as c:
        res = await c.post("/api/code/execute", json={"code": "while True: pass", "timeout": 1})
    assert res.json()["status"] == "timeout"
