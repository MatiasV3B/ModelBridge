"""OpenAI tool calling for clients that run their own tools (Zylo Chat, Zylo Code, any OpenAI SDK app).

The engines behind the Bridge (Antigravity, Claude Code and Codex CLIs) only return text. So when a request
carries `tools`:

1. the tool list and a calling protocol are added as a system message,
2. earlier tool calls and tool results in the history are turned into text the model can read, and
3. the model's `<tool_call>{"name": ..., "arguments": {...}}</tool_call>` blocks are turned back into OpenAI
   `tool_calls`, with finish_reason "tool_calls".

The client runs the tools itself and sends the results back as `role: "tool"` messages, as with OpenAI.
"""

import json
import re
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

OPEN = "<tool_call>"
CLOSE = "</tool_call>"
_BLOCK_RE = re.compile(r"<tool_call>\s*(.*?)\s*</tool_call>", re.DOTALL)
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$")


def wants_tools(tools: Any, tool_choice: Any) -> bool:
    return bool(tools) and isinstance(tools, list) and tool_choice != "none"


def _tool_specs(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    specs = []
    for tool in tools:
        fn = tool.get("function") if isinstance(tool, dict) else None
        if not isinstance(fn, dict) or not fn.get("name"):
            continue
        specs.append({
            "name": fn["name"],
            "description": fn.get("description", ""),
            "parameters": fn.get("parameters") or {"type": "object", "properties": {}},
        })
    return specs


def system_prompt(tools: List[Dict[str, Any]], tool_choice: Any = "auto") -> str:
    specs = _tool_specs(tools)
    lines = [
        "You can call the tools listed below. The client application runs them and sends you the results.",
        "To call a tool, write exactly this block (JSON inside, arguments as an object):",
        f'{OPEN}{{"name": "tool_name", "arguments": {{"arg": "value"}}}}{CLOSE}',
        "Rules:",
        "- You may write a short sentence before the blocks, and several blocks in a row for parallel calls.",
        "- After the last block, STOP. Do not invent tool results: they arrive in the next message.",
        "- Only use the tool names below, with arguments that match their JSON schema.",
        "- If no tool is needed, answer normally without any block.",
    ]
    if tool_choice == "required":
        lines.append("- You MUST call at least one tool in this answer.")
    elif isinstance(tool_choice, dict):
        name = (tool_choice.get("function") or {}).get("name")
        if name:
            lines.append(f"- You MUST call the tool `{name}` in this answer.")
    lines.append("Tools:")
    lines.append(json.dumps(specs, ensure_ascii=False, indent=1))
    return "\n".join(lines)


def _text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(str(p.get("text", "")) for p in content if isinstance(p, dict) and p.get("type") == "text")
    return str(content)


def prepare_messages(messages: List[Dict[str, Any]], tools: Any, tool_choice: Any = "auto") -> List[Dict[str, Any]]:
    """History the text-only engines understand, with the tool protocol in front when tools are offered."""
    names = {}
    out: List[Dict[str, Any]] = []
    for msg in messages:
        role = msg.get("role")
        if role == "assistant" and msg.get("tool_calls"):
            parts = [_text(msg.get("content"))] if _text(msg.get("content")) else []
            for call in msg["tool_calls"]:
                fn = call.get("function") or {}
                names[call.get("id")] = fn.get("name", "")
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except (TypeError, ValueError):
                    args = fn.get("arguments")
                parts.append(OPEN + json.dumps({"name": fn.get("name"), "arguments": args}, ensure_ascii=False) + CLOSE)
            out.append({"role": "assistant", "content": "\n".join(parts)})
        elif role == "tool":
            name = msg.get("name") or names.get(msg.get("tool_call_id"), "")
            out.append({"role": "user", "content": f"[Tool result for {name or 'tool'} (call {msg.get('tool_call_id', '')})]:\n"
                                                    f"{_text(msg.get('content'))}"})
        elif role == "function":  # legacy OpenAI function calling
            out.append({"role": "user", "content": f"[Tool result for {msg.get('name', 'tool')}]:\n{_text(msg.get('content'))}"})
        else:
            out.append(msg)
    if wants_tools(tools, tool_choice):
        out.insert(0, {"role": "system", "content": system_prompt(tools, tool_choice)})
    return out


def parse_calls(text: str) -> Tuple[str, List[Dict[str, Any]]]:
    """Split a model answer into (visible text, OpenAI tool_calls)."""
    calls: List[Dict[str, Any]] = []
    for raw in _BLOCK_RE.findall(text):
        raw = _FENCE_RE.sub("", raw.strip())
        try:
            data = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(data, dict) or not data.get("name"):
            continue
        args = data.get("arguments", data.get("parameters", {}))
        calls.append({
            "id": f"call_{uuid.uuid4().hex[:24]}",
            "type": "function",
            "function": {
                "name": str(data["name"]),
                "arguments": args if isinstance(args, str) else json.dumps(args, ensure_ascii=False),
            },
        })
    if not calls:
        return text, []
    visible = text[:text.find(OPEN)].rstrip()
    return visible, calls


async def stream_with_tools(chunks: AsyncGenerator[Dict[str, Any], None]) -> AsyncGenerator[Dict[str, Any], None]:
    """Pass text through as it streams; once a <tool_call> starts, hold it back and emit tool_calls at the end.

    Text inside <thought>...</thought> (the engines' reasoning) is never taken as a tool call.
    """
    pending = ""         # text not sent yet
    captured = ""        # everything from the first <tool_call> on
    in_thought = False
    last: Optional[Dict[str, Any]] = None

    def content_chunk(base: Dict[str, Any], text: str) -> Dict[str, Any]:
        return {**{k: v for k, v in base.items() if k != "usage"},
                "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}]}

    async for chunk in chunks:
        choice = (chunk.get("choices") or [{}])[0]
        finish = choice.get("finish_reason")
        if finish is not None:
            last = chunk
            if finish == "error":
                break
            continue
        text = (choice.get("delta") or {}).get("content")
        if not text:
            yield chunk
            continue
        if captured:
            captured += text
            continue
        pending += text
        out = ""
        while pending:
            if in_thought:
                end = pending.find("</thought>")
                if end == -1:
                    keep = _partial_len(pending, "</thought>")
                    out, pending = out + pending[:len(pending) - keep], pending[len(pending) - keep:]
                    break
                out += pending[:end + len("</thought>")]
                pending = pending[end + len("</thought>"):]
                in_thought = False
                continue
            t_start = pending.find("<thought>")
            c_start = pending.find(OPEN)
            if c_start != -1 and (t_start == -1 or c_start < t_start):
                out += pending[:c_start]
                captured = pending[c_start:]
                pending = ""
                break
            if t_start != -1:
                out += pending[:t_start + len("<thought>")]
                pending = pending[t_start + len("<thought>"):]
                in_thought = True
                continue
            keep = max(_partial_len(pending, OPEN), _partial_len(pending, "<thought>"))
            out, pending = out + pending[:len(pending) - keep], pending[len(pending) - keep:]
            break
        if out:
            yield content_chunk(chunk, out)

    base = last or {"id": f"chatcmpl-{uuid.uuid4().hex[:20]}", "object": "chat.completion.chunk"}
    if last and (last.get("choices") or [{}])[0].get("finish_reason") == "error":
        if pending:
            yield content_chunk(base, pending)
        yield last
        return
    calls = parse_calls(captured)[1] if captured else []
    if captured and not calls:
        pending += captured  # not a valid call after all: show it as text
    if pending:
        yield content_chunk(base, pending)
    for i, call in enumerate(calls):
        yield {**{k: v for k, v in base.items() if k != "usage"},
               "choices": [{"index": 0, "delta": {"tool_calls": [{"index": i, **call}]}, "finish_reason": None}]}
    final = dict(base)
    final["choices"] = [{"index": 0, "delta": {}, "finish_reason": "tool_calls" if calls else "stop"}]
    yield final


def _partial_len(text: str, token: str) -> int:
    for n in range(min(len(token) - 1, len(text)), 0, -1):
        if token.startswith(text[-n:]):
            return n
    return 0


def apply_to_completion(result: Dict[str, Any]) -> Dict[str, Any]:
    """Non-streaming answer: move <tool_call> blocks into message.tool_calls."""
    choice = (result.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    visible, calls = parse_calls(message.get("content") or "")
    if calls:
        message["content"] = visible or None
        message["tool_calls"] = calls
        choice["finish_reason"] = "tool_calls"
    return result
