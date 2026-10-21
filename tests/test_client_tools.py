"""OpenAI tool calling on top of the text-only engines (Zylo Chat / Zylo Code)."""

import asyncio
import json
from unittest.mock import patch

from fastapi.testclient import TestClient

from core import client_tools
from server.app import app

TOOLS = [{"type": "function", "function": {"name": "read_file", "description": "Read a file",
                                           "parameters": {"type": "object", "properties": {"path": {"type": "string"}}}}}]


def _fake_stream(pieces):
    async def gen(*args, **kwargs):
        for p in pieces:
            yield {"id": "x", "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {"content": p}, "finish_reason": None}]}
        yield {"id": "x", "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
               "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}
    return gen


def _collect(pieces):
    async def run():
        return [c async for c in client_tools.stream_with_tools(_fake_stream(pieces)())]
    return asyncio.run(run())


def test_stream_turns_block_into_tool_calls_even_split_across_chunks():
    out = _collect(["Let me look.", " <tool", '_call>{"name": "read_file", "argu', 'ments": {"path": "a.ts"}}</tool_call>'])
    text = "".join(c["choices"][0]["delta"].get("content", "") for c in out)
    calls = [c["choices"][0]["delta"]["tool_calls"][0] for c in out if "tool_calls" in c["choices"][0]["delta"]]
    assert "<tool" not in text and text.strip() == "Let me look."
    assert calls[0]["function"]["name"] == "read_file"
    assert json.loads(calls[0]["function"]["arguments"]) == {"path": "a.ts"}
    assert calls[0]["id"].startswith("call_")
    assert out[-1]["choices"][0]["finish_reason"] == "tool_calls"


def test_plain_text_and_thoughts_pass_through():
    out = _collect(["<thought>maybe <tool_call>{\"name\":\"x\"}</tool_call></thought>", "Hello <b>"])
    text = "".join(c["choices"][0]["delta"].get("content", "") for c in out)
    assert text.endswith("Hello <b>")
    assert out[-1]["choices"][0]["finish_reason"] == "stop"


def test_history_with_tool_results_becomes_text():
    msgs = [{"role": "user", "content": "hi"},
            {"role": "assistant", "content": None, "tool_calls": [{"id": "c1", "type": "function",
                                                                    "function": {"name": "read_file", "arguments": '{"path":"a"}'}}]},
            {"role": "tool", "tool_call_id": "c1", "content": "file body"}]
    out = client_tools.prepare_messages(msgs, TOOLS)
    assert out[0]["role"] == "system" and "read_file" in out[0]["content"]
    assert "<tool_call>" in out[2]["content"]
    assert out[3]["role"] == "user" and "read_file" in out[3]["content"] and "file body" in out[3]["content"]


def test_endpoint_streams_tool_calls_and_cors_preflight():
    client = TestClient(app)
    with patch("server.routes_chat.bridge_engine.generate_stream",
               _fake_stream(['<tool_call>{"name":"read_file","arguments":{"path":"x"}}</tool_call>'])):
        r = client.post("/v1/chat/completions", json={"model": "m", "stream": True, "tools": TOOLS,
                                                      "messages": [{"role": "user", "content": "read x"}]})
    events = [json.loads(l[6:]) for l in r.text.splitlines() if l.startswith("data: {")]
    assert any("tool_calls" in e["choices"][0]["delta"] for e in events)
    pre = client.options("/v1/chat/completions", headers={
        "Origin": "https://chat.zyloai.net", "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type,authorization", "Access-Control-Request-Private-Network": "true"})
    assert pre.status_code == 200
    assert pre.headers.get("access-control-allow-private-network") == "true"
    assert pre.headers.get("access-control-allow-origin") in ("*", "https://chat.zyloai.net")


def test_non_stream_moves_calls_to_message():
    result = {"choices": [{"message": {"role": "assistant", "content": 'ok <tool_call>{"name":"read_file","arguments":{}}</tool_call>'},
                           "finish_reason": "stop"}]}
    out = client_tools.apply_to_completion(result)
    assert out["choices"][0]["finish_reason"] == "tool_calls"
    assert out["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"] == "{}"
