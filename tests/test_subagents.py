"""Sub-agent orchestration: protocol parsing, parallelism, nesting and the HTTP endpoint."""

import asyncio
import json

import httpx
import pytest

from core.subagents import (
    build_subagent_prompt,
    normalize_specs,
    parse_spawn_blocks,
    run_subagents,
)
from server.app import app


def spawn(*agents):
    return "<spawn_agents>" + json.dumps(list(agents)) + "</spawn_agents>"


def agent(name, task="do it", role=""):
    return {"name": name, "role": role, "task": task}


async def collect(specs, runner, **kwargs):
    events = []
    async for event in run_subagents(specs, runner, **kwargs):
        events.append(event)
    return events


# ───────────── parsing ─────────────

def test_parse_extracts_agents_and_cleans_text():
    text = "Plan first.\n" + spawn(agent("A"), agent("B", "other")) + "\nTrailing"
    clean, specs = parse_spawn_blocks(text)
    assert [s["name"] for s in specs] == ["A", "B"]
    assert "spawn_agents" not in clean
    assert clean.startswith("Plan first.") and clean.endswith("Trailing")


def test_parse_accepts_fenced_json_and_aliases():
    text = '<spawn_agents>\n```json\n[{"title": "Researcher", "persona": "You research", "prompt": "Find X"}]\n```\n</spawn_agents>'
    _, specs = parse_spawn_blocks(text)
    assert specs == [{"name": "Researcher", "role": "You research", "task": "Find X"}]


def test_parse_ignores_malformed_and_taskless_agents():
    assert parse_spawn_blocks("<spawn_agents>not json</spawn_agents>")[1] == []
    assert parse_spawn_blocks(spawn({"name": "NoTask"}))[1] == []
    assert parse_spawn_blocks("no block at all") == ("no block at all", [])


def test_normalize_dedupes_names_and_caps_count():
    specs = normalize_specs([agent("Same"), agent("Same"), agent("Same")], max_agents=2)
    assert [s["name"] for s in specs] == ["Same", "Same 2"]


def test_prompt_allows_delegation_only_below_max_depth():
    spec = {"name": "Dev", "role": "You write code", "task": "x"}
    assert "<spawn_agents>" in build_subagent_prompt(spec, "goal", depth=1, max_depth=2)
    low = build_subagent_prompt(spec, "goal", depth=2, max_depth=2)
    assert "<spawn_agents>" not in low and "cannot delegate" in low
    assert "You write code" in low and "goal" in low


# ───────────── orchestration ─────────────

@pytest.mark.anyio
async def test_agents_run_in_parallel_up_to_the_limit():
    running = peak = 0

    async def runner(messages, model):
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.05)
        running -= 1
        return {"text": "ok", "prompt_tokens": 10, "completion_tokens": 5}

    events = await collect([agent(f"A{i}") for i in range(4)], runner, max_concurrency=2)
    done = events[-1]
    assert done["type"] == "run_done"
    assert peak == 2
    assert len(done["results"]) == 4 and all(r["status"] == "done" for r in done["results"])
    assert done["usage"] == {"prompt_tokens": 40, "completion_tokens": 20}


@pytest.mark.anyio
async def test_each_agent_gets_its_own_prompt_and_task():
    seen = []

    async def runner(messages, model):
        seen.append(messages)
        return {"text": "fine"}

    await collect([agent("Writer", "write intro", "You are a writer")], runner)
    system, user = seen[0]
    assert system["role"] == "system" and "Writer" in system["content"] and "You are a writer" in system["content"]
    assert user == {"role": "user", "content": "write intro"}


@pytest.mark.anyio
async def test_one_failure_does_not_sink_the_others():
    async def runner(messages, model):
        if "Bad" in messages[0]["content"]:
            raise RuntimeError("boom")
        return {"text": "good"}

    events = await collect([agent("Good"), agent("Bad")], runner)
    results = {r["name"]: r for r in events[-1]["results"]}
    assert results["Good"]["status"] == "done"
    assert results["Bad"]["status"] == "error" and "boom" in results["Bad"]["error"]


@pytest.mark.anyio
async def test_timeout_is_reported_per_agent():
    async def runner(messages, model):
        await asyncio.sleep(30)
        return {"text": "late"}

    events = await collect([agent("Slow")], runner, timeout=0.3)
    assert events[-1]["results"][0]["status"] == "error"
    assert "Timed out" in events[-1]["results"][0]["error"]


@pytest.mark.anyio
async def test_empty_answer_counts_as_error():
    async def runner(messages, model):
        return {"text": "   "}

    events = await collect([agent("Silent")], runner)
    assert events[-1]["results"][0]["status"] == "error"


@pytest.mark.anyio
async def test_nested_agents_rewind_to_their_parent():
    calls = []

    async def runner(messages, model):
        system = messages[0]["content"]
        calls.append(messages)
        if '"Lead"' in system and len(messages) == 2:
            return {"text": "Splitting. " + spawn(agent("Helper", "small job"))}
        if '"Helper"' in system:
            return {"text": "helper result"}
        # Lead's second pass must have received the helper's answer
        assert "helper result" in messages[-1]["content"]
        return {"text": "lead final"}

    events = await collect([agent("Lead")], runner, max_depth=2)
    results = {r["name"]: r for r in events[-1]["results"]}
    assert results["Lead"]["text"] == "lead final"
    assert results["Lead"]["children"] == ["1.1"]
    started = [e for e in events if e["type"] == "agent_start"]
    assert [(e["id"], e["parent"], e["depth"]) for e in started] == [("1", None, 1), ("1.1", "1", 2)]
    assert len(calls) == 3


@pytest.mark.anyio
async def test_delegation_stops_at_max_depth():
    async def runner(messages, model):
        return {"text": "Result. " + spawn(agent("Deeper"))}

    events = await collect([agent("Top")], runner, max_depth=1)
    result = events[-1]["results"][0]
    assert result["text"] == "Result."  # block stripped, nothing spawned
    assert [e["name"] for e in events if e["type"] == "agent_start"] == ["Top"]


@pytest.mark.anyio
async def test_content_safety_block_is_retried_once():
    attempts = 0

    async def runner(messages, model):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return {"text": "Antigravity Error: response blocked by content safety filters"}
        return {"text": "second try works"}

    events = await collect([agent("Retry")], runner)
    assert events[-1]["results"][0]["text"] == "second try works"
    assert attempts == 2


@pytest.mark.anyio
async def test_closing_the_stream_cancels_running_agents():
    cancelled = asyncio.Event()

    async def runner(messages, model):
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return {"text": "never"}

    gen = run_subagents([agent("Hang")], runner)
    first = await gen.__anext__()
    assert first["type"] == "agent_start"
    await gen.aclose()
    await asyncio.wait_for(cancelled.wait(), timeout=2)


# ───────────── HTTP endpoint ─────────────

@pytest.fixture
def fake_engine(monkeypatch):
    calls = []

    async def fake_generate_sync(messages, model=None, **kwargs):
        calls.append({"messages": messages, "model": model, **kwargs})
        task = messages[-1]["content"]
        return {
            "choices": [{"message": {"role": "assistant", "content": f"done: {task}"}}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 3},
        }

    monkeypatch.setattr("server.routes_agents.bridge_engine.generate_sync", fake_generate_sync)
    return calls


@pytest.mark.anyio
async def test_endpoint_streams_progress_events(fake_engine):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/claude/v1/agents/run", json={
            "model": "claude-sonnet-5-5",
            "goal": "demo",
            "agents": [agent("A", "one"), agent("B", "two")],
        }, headers={"x-claude-mode": "desktop"})
    assert res.status_code == 200
    frames = [line[6:] for line in res.text.splitlines() if line.startswith("data: ")]
    assert frames[-1] == "[DONE]"
    events = [json.loads(f) for f in frames[:-1]]
    assert {e["type"] for e in events} == {"agent_start", "agent_done", "run_done"}
    assert {r["text"] for r in events[-1]["results"]} == {"done: one", "done: two"}
    # the URL prefix selected the provider, the header selected the mode
    assert all(c["provider"] == "claude" and c["claude_mode"] == "desktop" for c in fake_engine)
    assert all(c["model"] == "claude-sonnet-5-5" for c in fake_engine)


@pytest.mark.anyio
async def test_endpoint_can_return_plain_json(fake_engine):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/v1/agents/run", json={"stream": False, "agents": [agent("Solo", "task")]})
    body = res.json()
    assert res.status_code == 200
    assert body["results"][0]["text"] == "done: task"
    assert body["usage"] == {"prompt_tokens": 7, "completion_tokens": 3}


@pytest.mark.anyio
async def test_endpoint_rejects_requests_without_a_usable_agent(fake_engine):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/v1/agents/run", json={"agents": [{"name": "NoTask"}]})
    assert res.status_code == 400
    assert fake_engine == []


@pytest.mark.anyio
async def test_total_agents_are_capped_at_the_limit():
    async def runner(messages, model):
        return {"text": "ok"}

    events = await collect([agent(f"A{i}") for i in range(60)], runner, max_agents=50, max_concurrency=6)
    assert len(events[-1]["results"]) == 50
    assert normalize_specs([agent(f"B{i}") for i in range(80)]) and len(normalize_specs([agent(f"B{i}") for i in range(80)])) == 50
