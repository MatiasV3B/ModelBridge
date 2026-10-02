"""Anthropic Messages and Claude Agent SDK endpoints for Antigravity Bridge."""

import json
import logging
import uuid
import time
import re
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from typing import List, Optional, Any, Dict, Tuple

from claude_agent import claude_agent_executor, DEFAULT_CLAUDE_MODEL
from core.config import bridge_config
from core.bridge_engine import metrics, bridge_engine
from core.model_registry import model_registry

router = APIRouter(tags=["Claude Agent SDK"])
logger = logging.getLogger("antigravity_bridge.claude")


class ClaudeAgentRunRequest(BaseModel):
    prompt: Optional[str] = ""
    messages: Optional[List[Dict[str, Any]]] = None
    model: Optional[str] = DEFAULT_CLAUDE_MODEL
    system: Optional[Union[str, List[Any]]] = None
    page_context: Optional[str] = None
    tools: Optional[List[Dict[str, Any]]] = None
    thinking_budget: Optional[int] = 0
    stream: Optional[bool] = True

    class Config:
        extra = "allow"


def _extract_anthropic_key(request: Request) -> Optional[str]:
    """Extract Anthropic API key from headers, config, or environment."""
    x_api_key = request.headers.get("x-api-key")
    if x_api_key and not x_api_key.startswith("sk-antigravity"):
        return x_api_key
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        bearer_key = auth_header[7:].strip()
        if bearer_key and not bearer_key.startswith("sk-antigravity"):
            return bearer_key
    return bridge_config.anthropic_api_key or None


def clean_model_name(raw_model: Optional[str]) -> str:
    """Clean model name by stripping ANSI codes or bracket annotations like [1m."""
    if not raw_model:
        return DEFAULT_CLAUDE_MODEL
    cleaned = re.sub(r"\x1b\[[0-9;]*m", "", raw_model).strip()
    if "[" in cleaned:
        cleaned = cleaned.split("[")[0].strip()
    return cleaned or DEFAULT_CLAUDE_MODEL


def map_model_for_agy(model: str) -> str:
    """Map any requested Claude/other model to an available Antigravity CLI model."""
    cleaned = clean_model_name(model).lower()
    if "opus" in cleaned:
        return "claude-opus-4-6-thinking"
    elif "sonnet" in cleaned or "fable" in cleaned:
        return "claude-sonnet-4-6"
    elif "haiku" in cleaned:
        return "claude-sonnet-4-6"
    elif "gpt" in cleaned:
        return "gpt-oss-120b-medium"
    elif "gemini" in cleaned:
        return model_registry.resolve_model(cleaned)
    return "claude-sonnet-4-6"


def extract_anthropic_prompt(messages: Any, system: Any = None) -> Tuple[str, List[str]]:
    """Convert Anthropic messages and system prompt into an optimized prompt string for Antigravity CLI."""
    msg_parts: List[str] = []

    # Process conversation messages first
    if isinstance(messages, list):
        for msg in messages:
            role = msg.get("role", "user").upper()
            content = msg.get("content", "")
            if isinstance(content, str) and content.strip():
                msg_parts.append(f"[{role}]: {content.strip()}")
            elif isinstance(content, list):
                block_texts = []
                for block in content:
                    if isinstance(block, dict):
                        btype = block.get("type", "")
                        if btype == "text":
                            t = block.get("text", "").strip()
                            if t:
                                block_texts.append(t)
                        elif btype == "tool_result":
                            res_content = block.get("content", "")
                            t_id = block.get("tool_use_id", "")
                            block_texts.append(f"[Tool Result {t_id}]: {res_content}")
                        elif btype == "tool_use":
                            name = block.get("name", "")
                            inp = json.dumps(block.get("input", {}), ensure_ascii=False)
                            block_texts.append(f"[Tool Call: {name}({inp})]")
                    elif isinstance(block, str) and block.strip():
                        block_texts.append(block.strip())
                if block_texts:
                    msg_parts.append(f"[{role}]: {' '.join(block_texts)}")

    # Optimization: If it's a single user message and no complex history, return clean user prompt
    if len(msg_parts) == 1 and msg_parts[0].startswith("[USER]: "):
        clean_user = msg_parts[0][8:].strip()
        if clean_user:
            return clean_user, []

    # Process system prompt if present, capping to safe length
    sys_text = ""
    if system:
        if isinstance(system, str):
            sys_text = system.strip()
        elif isinstance(system, list):
            s_parts = []
            for item in system:
                if isinstance(item, dict):
                    t = item.get("text", "").strip()
                    if t:
                        s_parts.append(t)
                elif isinstance(item, str) and item.strip():
                    s_parts.append(item.strip())
            sys_text = " ".join(s_parts)

    parts: List[str] = []
    if sys_text:
        if len(sys_text) > 3000:
            sys_text = sys_text[:1500] + "\n...[guidelines]...\n" + sys_text[-1500:]
        parts.append(f"[System Instructions]:\n{sys_text}")

    parts.extend(msg_parts)

    full_prompt = "\n\n".join(parts)
    # Ensure full prompt never exceeds safe Windows command line buffer (~15,000 chars)
    if len(full_prompt) > 15000:
        full_prompt = full_prompt[-15000:]

    return full_prompt, []


async def generate_anthropic_sse_stream(
    event_generator,
    model: str,
    msg_id: str,
    input_tokens: int = 25
):
    """
    Standard Anthropic Messages SSE Streamer.
    Adheres strictly to the Anthropic Messages Streaming protocol:
    1. message_start
    2. content_block_start -> content_block_delta -> content_block_stop
    3. message_delta
    4. message_stop
    """
    # 1. message_start
    start_payload = {
        "type": "message_start",
        "message": {
            "id": msg_id,
            "type": "message",
            "role": "assistant",
            "content": [],
            "model": model,
            "stop_reason": None,
            "stop_sequence": None,
            "usage": {"input_tokens": input_tokens, "output_tokens": 1}
        }
    }
    yield f"event: message_start\ndata: {json.dumps(start_payload)}\n\n".encode("utf-8")

    current_block_type = None  # None, "thinking", "text"
    current_block_index = 0
    completion_tokens = 0
    blocks_opened = False

    async for item_type, data in event_generator:
        if item_type == "thinking" and data:
            if current_block_type != "thinking":
                if current_block_type is not None:
                    yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': current_block_index})}\n\n".encode("utf-8")
                    current_block_index += 1
                start_blk = {
                    "type": "content_block_start",
                    "index": current_block_index,
                    "content_block": {"type": "thinking", "thinking": ""}
                }
                yield f"event: content_block_start\ndata: {json.dumps(start_blk)}\n\n".encode("utf-8")
                current_block_type = "thinking"
                blocks_opened = True

            delta_blk = {
                "type": "content_block_delta",
                "index": current_block_index,
                "delta": {"type": "thinking_delta", "thinking": data}
            }
            yield f"event: content_block_delta\ndata: {json.dumps(delta_blk)}\n\n".encode("utf-8")
            completion_tokens += max(1, len(data) // 4)

        elif item_type == "text" and data:
            if current_block_type != "text":
                if current_block_type is not None:
                    yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': current_block_index})}\n\n".encode("utf-8")
                    current_block_index += 1
                start_blk = {
                    "type": "content_block_start",
                    "index": current_block_index,
                    "content_block": {"type": "text", "text": ""}
                }
                yield f"event: content_block_start\ndata: {json.dumps(start_blk)}\n\n".encode("utf-8")
                current_block_type = "text"
                blocks_opened = True

            delta_blk = {
                "type": "content_block_delta",
                "index": current_block_index,
                "delta": {"type": "text_delta", "text": data}
            }
            yield f"event: content_block_delta\ndata: {json.dumps(delta_blk)}\n\n".encode("utf-8")
            completion_tokens += max(1, len(data) // 4)

        elif item_type == "tool_use" and data:
            if current_block_type is not None:
                yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': current_block_index})}\n\n".encode("utf-8")
                current_block_index += 1
                current_block_type = None

            tool_id = data.get("id") or f"toolu_{uuid.uuid4().hex[:12]}"
            tool_name = data.get("name") or "tool"
            tool_input = data.get("input") or {}
            start_blk = {
                "type": "content_block_start",
                "index": current_block_index,
                "content_block": {"type": "tool_use", "id": tool_id, "name": tool_name, "input": {}}
            }
            yield f"event: content_block_start\ndata: {json.dumps(start_blk)}\n\n".encode("utf-8")
            delta_blk = {
                "type": "content_block_delta",
                "index": current_block_index,
                "delta": {"type": "input_json_delta", "partial_json": json.dumps(tool_input)}
            }
            yield f"event: content_block_delta\ndata: {json.dumps(delta_blk)}\n\n".encode("utf-8")
            yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': current_block_index})}\n\n".encode("utf-8")
            current_block_index += 1
            blocks_opened = True

    # Close active block if open
    if current_block_type is not None:
        yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': current_block_index})}\n\n".encode("utf-8")

    # If no blocks were opened at all (empty response or error fallback), open and close a text block
    if not blocks_opened:
        start_blk = {
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": "text", "text": ""}
        }
        yield f"event: content_block_start\ndata: {json.dumps(start_blk)}\n\n".encode("utf-8")
        delta_blk = {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "text_delta", "text": " "}
        }
        yield f"event: content_block_delta\ndata: {json.dumps(delta_blk)}\n\n".encode("utf-8")
        yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': 0})}\n\n".encode("utf-8")

    # 3. message_delta
    stop_payload = {
        "type": "message_delta",
        "delta": {"stop_reason": "end_turn", "stop_sequence": None},
        "usage": {"output_tokens": max(1, completion_tokens)}
    }
    yield f"event: message_delta\ndata: {json.dumps(stop_payload)}\n\n".encode("utf-8")

    # 4. message_stop
    yield b"event: message_stop\ndata: {\"type\": \"message_stop\"}\n\n"


async def claude_sse_generator(
    prompt: str,
    messages: Optional[List[Dict[str, Any]]],
    model: str,
    system_prompt: Optional[str],
    page_context: Optional[str],
    tools: Optional[List[Dict[str, Any]]],
    thinking_budget: int,
    api_key: Optional[str]
):
    """Yield SSE events for Claude Agent execution (Chrome Extension format)."""
    async for event in claude_agent_executor.run_agent(
        prompt=prompt,
        messages=messages,
        system_prompt=system_prompt,
        page_context=page_context,
        tools=tools,
        model=model,
        thinking_budget=thinking_budget,
        api_key=api_key
    ):
        yield f"data: {json.dumps(event)}\n\n".encode("utf-8")
    yield b"data: [DONE]\n\n"


@router.post("/v1/claude/agent")
@router.post("/claude/agent")
async def run_claude_agent(request: Request):
    """Run an autonomous task with Claude Agent SDK and browser tools."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    req_data = ClaudeAgentRunRequest(**body)
    api_key = _extract_anthropic_key(request)

    prompt = req_data.prompt or ""
    if not prompt and req_data.messages:
        last_msg = req_data.messages[-1]
        prompt = last_msg.get("content", "")

    sys_text = req_data.system
    if isinstance(sys_text, list):
        sys_text = " ".join([b.get("text", "") for b in sys_text if isinstance(b, dict)])

    if req_data.stream:
        return StreamingResponse(
            claude_sse_generator(
                prompt=prompt,
                messages=req_data.messages,
                model=req_data.model or DEFAULT_CLAUDE_MODEL,
                system_prompt=sys_text,
                page_context=req_data.page_context,
                tools=req_data.tools,
                thinking_budget=req_data.thinking_budget or 0,
                api_key=api_key
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Content-Type": "text/event-stream",
                "X-Accel-Buffering": "no",
            },
        )

    # Non-streaming collection
    collected_text = ""
    collected_reasoning = ""
    tool_calls = []

    async for event in claude_agent_executor.run_agent(
        prompt=prompt,
        messages=req_data.messages,
        system_prompt=sys_text,
        page_context=req_data.page_context,
        tools=req_data.tools,
        model=req_data.model or DEFAULT_CLAUDE_MODEL,
        thinking_budget=req_data.thinking_budget or 0,
        api_key=api_key
    ):
        etype = event.get("type")
        if etype == "chunk":
            collected_text += event.get("text", "")
        elif etype == "reasoning":
            collected_reasoning += event.get("thinking", "")
        elif etype == "tool_call":
            tool_calls.append(event)
        elif etype == "error":
            return JSONResponse(status_code=500, content={"error": event.get("message")})

    return JSONResponse(content={
        "status": "success",
        "model": req_data.model or DEFAULT_CLAUDE_MODEL,
        "content": collected_text,
        "reasoning": collected_reasoning,
        "tool_calls": tool_calls
    })


@router.post("/v1/messages/count_tokens")
@router.post("/messages/count_tokens")
@router.post("/v1/v1/messages/count_tokens")
async def count_tokens_endpoint(request: Request):
    """Token counting endpoint expected by Claude Code and Anthropic SDK."""
    try:
        body = await request.json()
    except Exception:
        body = {}

    total_chars = 0
    system = body.get("system")
    if isinstance(system, str):
        total_chars += len(system)
    elif isinstance(system, list):
        for b in system:
            if isinstance(b, dict):
                total_chars += len(str(b.get("text", "")))

    messages = body.get("messages", [])
    if isinstance(messages, list):
        for m in messages:
            content = m.get("content", "")
            if isinstance(content, str):
                total_chars += len(content)
            elif isinstance(content, list):
                for b in content:
                    if isinstance(b, dict):
                        total_chars += len(str(b.get("text", "") or b.get("content", "")))

    tools = body.get("tools", [])
    if isinstance(tools, list):
        for t in tools:
            total_chars += len(json.dumps(t))

    estimated_tokens = max(1, total_chars // 4 + 10)
    return JSONResponse(content={"input_tokens": estimated_tokens})


@router.post("/v1/messages")
@router.post("/messages")
@router.post("/v1/v1/messages")
async def anthropic_messages_endpoint(request: Request):
    """
    Native Anthropic Messages API compatibility endpoint.
    Supports Claude Code CLI (in terminal), anthropic-python, and Claude Agent SDK.
    Routes intelligently to Anthropic API if key is present, or to Antigravity CLI (agy)
    with native Google Authentication.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    raw_model = body.get("model", DEFAULT_CLAUDE_MODEL)
    model = clean_model_name(raw_model)
    messages = body.get("messages", [])
    system = body.get("system", "")
    stream = body.get("stream", False)
    tools = body.get("tools", None)
    thinking = body.get("thinking", {})
    thinking_budget = thinking.get("budget_tokens", 0) if isinstance(thinking, dict) else 0

    req_claude_mode = request.headers.get("x-claude-mode") or body.get("claude_mode") or getattr(bridge_config, "claude_mode", "auto")
    api_key = _extract_anthropic_key(request) or body.get("api_key")
    has_real_anthropic_key = bool(api_key and not api_key.startswith("sk-antigravity"))

    m_lower = model.lower()
    is_new_anthropic_model = any(k in m_lower for k in ["5-5", "5.5", "5-1", "5.1", "4-5", "haiku-4-5"])

    # Extract clean prompt for Antigravity CLI fallback
    prompt_str, _ = extract_anthropic_prompt(messages, system)
    input_tokens = max(1, len(prompt_str) // 4 + 10)

    msg_id = f"msg_{uuid.uuid4().hex[:20]}"
    start_time = time.time()

    # Track metrics in Antigravity Bridge
    metrics.active_requests += 1
    metrics.total_requests += 1
    log_entry = {
        "id": msg_id,
        "timestamp": time.strftime("%H:%M:%S"),
        "model": model,
        "type": "claude_messages_stream" if stream else "claude_messages_sync",
        "status": "in_progress",
        "prompt_length": len(prompt_str),
    }
    metrics.add_log(log_entry)

    # Decide execution strategy based on claude_mode:
    # 1. "api": Directly use Anthropic API (Anthropic Messages API)
    # 2. "cli" / "claude_code": Route to local Claude Code / Antigravity CLI
    # 3. "auto": If key exists, use API; otherwise use Claude Code local service
    if req_claude_mode == "api":
        use_anthropic_api = True
    elif req_claude_mode in ["cli", "claude_code"]:
        use_anthropic_api = False
    else:
        use_anthropic_api = has_real_anthropic_key and claude_agent_executor.is_claude_model(model)

    if use_anthropic_api:
        if not has_real_anthropic_key:
            logger.warning(f"Claude API mode requested for '{model}', but no Anthropic API key is provided.")
            async def event_generator():
                yield ("text", "\n[Aviso: Has seleccionado el modo 'Claude API Directa', pero no se ha configurado ninguna clave ANTHROPIC_API_KEY. Ve a los Ajustes de Autono para ingresar tu clave sk-ant-... o selecciona el modo 'Claude Code (Servicio local)' para usarlo sin clave.]\n")
        else:
            logger.info(f"Routing Anthropic message request to Anthropic API with model '{model}'")
            async def event_generator():
                async for event in claude_agent_executor.run_agent(
                    prompt=prompt_str,
                    messages=messages,
                    system_prompt=system if isinstance(system, str) else None,
                    tools=tools,
                    model=model,
                    thinking_budget=thinking_budget,
                    api_key=api_key
                ):
                    etype = event.get("type")
                    if etype == "chunk":
                        yield ("text", event.get("text", ""))
                    elif etype == "reasoning":
                        yield ("thinking", event.get("thinking", ""))
                    elif etype == "tool_call":
                        yield ("tool_use", {
                            "id": f"toolu_{uuid.uuid4().hex[:12]}",
                            "name": event.get("tool"),
                            "input": event.get("arguments", {})
                        })
                    elif etype == "error":
                        yield ("text", f"\n[Error de Claude API: {event.get('message')}]\n")
    else:
        # Route to Antigravity CLI (agy.exe)
        agy_model = map_model_for_agy(model)
        logger.info(f"Routing Claude Code request to Antigravity CLI with model '{agy_model}' (requested: '{model}')")

        async def event_generator():
            in_thinking = False
            async for chunk_text, event_data in bridge_engine._stream_cli(prompt_str, agy_model, []):
                if chunk_text:
                    # Parse thought tags if present
                    if "<thought>" in chunk_text:
                        th = chunk_text.split("<thought>", 1)[1]
                        if "</thought>" in th:
                            th_part, txt_part = th.split("</thought>", 1)
                            if th_part:
                                yield ("thinking", th_part)
                            if txt_part:
                                yield ("text", txt_part)
                        else:
                            yield ("thinking", th)
                            in_thinking = True
                    elif "</thought>" in chunk_text:
                        txt_part = chunk_text.split("</thought>", 1)[1]
                        in_thinking = False
                        if txt_part:
                            yield ("text", txt_part)
                    elif in_thinking:
                        yield ("thinking", chunk_text)
                    else:
                        yield ("text", chunk_text)

    if stream:
        async def sse_wrapper():
            try:
                async for chunk in generate_anthropic_sse_stream(
                    event_generator(),
                    model=model,
                    msg_id=msg_id,
                    input_tokens=input_tokens
                ):
                    yield chunk
                log_entry["status"] = "success"
                log_entry["duration"] = f"{round(time.time() - start_time, 2)}s"
            except Exception as e:
                logger.error(f"Error in Anthropic streaming response: {e}")
                log_entry["status"] = "error"
                log_entry["error"] = str(e)
                # Ensure closing events
                error_blk = {
                    "type": "content_block_start",
                    "index": 0,
                    "content_block": {"type": "text", "text": f"\n[Antigravity Bridge Error: {e}]\n"}
                }
                yield f"event: content_block_start\ndata: {json.dumps(error_blk)}\n\n".encode("utf-8")
                yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': 0})}\n\n".encode("utf-8")
                stop_payload = {
                    "type": "message_delta",
                    "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                    "usage": {"output_tokens": 10}
                }
                yield f"event: message_delta\ndata: {json.dumps(stop_payload)}\n\n".encode("utf-8")
                yield b"event: message_stop\ndata: {\"type\": \"message_stop\"}\n\n"
            finally:
                metrics.active_requests = max(0, metrics.active_requests - 1)

        return StreamingResponse(
            sse_wrapper(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Content-Type": "text/event-stream",
                "X-Accel-Buffering": "no",
            }
        )

    # Non-streaming collection
    content_blocks = []
    collected_text = ""
    try:
        async for item_type, data in event_generator():
            if item_type == "text" and data:
                collected_text += data
            elif item_type == "tool_use" and data:
                content_blocks.append({
                    "type": "tool_use",
                    "id": data.get("id"),
                    "name": data.get("name"),
                    "input": data.get("input", {})
                })

        if collected_text:
            content_blocks.insert(0, {"type": "text", "text": collected_text})
        elif not content_blocks:
            content_blocks.append({"type": "text", "text": " "})

        output_tokens = max(1, len(collected_text) // 4)
        duration = round(time.time() - start_time, 2)
        log_entry["status"] = "success"
        log_entry["duration"] = f"{duration}s"
        log_entry["tokens"] = f"{input_tokens}/{output_tokens}"

        return JSONResponse(content={
            "id": msg_id,
            "type": "message",
            "role": "assistant",
            "content": content_blocks,
            "model": model,
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens}
        })
    except Exception as e:
        log_entry["status"] = "error"
        log_entry["error"] = str(e)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        metrics.active_requests = max(0, metrics.active_requests - 1)
