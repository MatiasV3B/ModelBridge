"""Sub-agent endpoint: run several assistants in parallel, each in its own CLI process."""

import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from core.bridge_engine import bridge_engine
from core.subagents import normalize_specs, run_subagents

router = APIRouter(tags=["Sub-agents"])
logger = logging.getLogger("antigravity_bridge")


class AgentsRunRequest(BaseModel):
    model: Optional[str] = None
    goal: str = ""
    agents: List[Dict[str, Any]] = Field(default_factory=list)
    stream: bool = True
    max_concurrency: int = 4
    max_depth: int = 2
    max_agents: int = 50
    timeout: float = 600
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None

    class Config:
        extra = "allow"


def _forward_kwargs(request: Request, body: Dict[str, Any]) -> Dict[str, Any]:
    """Provider, mode and key hints, resolved exactly like the chat completions route."""
    path = request.url.path.lower()
    url_provider = None
    if path.startswith("/antigravity"):
        url_provider = "antigravity"
    elif path.startswith("/claude") or path.startswith("/cloud"):
        url_provider = "claude"
    elif path.startswith("/openai"):
        url_provider = "openai"
    headers = request.headers
    return {
        "provider": url_provider or body.get("provider") or headers.get("x-provider"),
        "claude_mode": headers.get("x-claude-mode") or body.get("claude_mode"),
        "antigravity_mode": headers.get("x-antigravity-mode") or body.get("antigravity_mode"),
        "openai_mode": headers.get("x-openai-mode") or body.get("openai_mode"),
        "api_key": headers.get("x-api-key") or body.get("api_key") or headers.get("x-anthropic-key"),
        "gemini_api_key": headers.get("x-gemini-key") or body.get("gemini_api_key"),
        "openai_api_key": headers.get("x-openai-key") or body.get("openai_api_key"),
        "reasoning_effort": body.get("reasoning_effort") or body.get("thinking_effort"),
        "thinking_budget": body.get("thinking_budget"),
    }


def make_engine_runner(default_model: Optional[str], kwargs: Dict[str, Any],
                       temperature: Optional[float], max_tokens: Optional[int]):
    async def runner(messages: List[Dict[str, Any]], model: Optional[str]) -> Dict[str, Any]:
        result = await bridge_engine.generate_sync(
            messages=messages,
            model=model or default_model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )
        text = ((result.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        usage = result.get("usage") or {}
        return {
            "text": text,
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
        }

    return runner


@router.post("/v1/agents/run")
@router.post("/agents/run")
async def run_agents(request: Request):
    """Run the given sub-agents in parallel and stream their progress (or return the final results)."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    req = AgentsRunRequest(**body)
    specs = normalize_specs(req.agents, req.max_agents)
    if not specs:
        raise HTTPException(status_code=400, detail="'agents' must contain at least one agent with a 'task'")

    runner = make_engine_runner(req.model, _forward_kwargs(request, body), req.temperature, req.max_tokens)
    events = run_subagents(
        specs, runner,
        goal=req.goal, max_depth=req.max_depth, max_concurrency=req.max_concurrency,
        timeout=req.timeout, max_agents=req.max_agents,
    )

    if req.stream:
        async def sse():
            try:
                async for event in events:
                    yield f"data: {json.dumps(event)}\n\n".encode("utf-8")
            except Exception as exc:
                logger.error(f"Sub-agent stream error: {exc}")
                yield f"data: {json.dumps({'type': 'run_error', 'error': str(exc)})}\n\n".encode("utf-8")
            yield b"data: [DONE]\n\n"

        return StreamingResponse(
            sse(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )

    final: Dict[str, Any] = {}
    async for event in events:
        if event.get("type") in ("run_done", "run_error"):
            final = event
    if final.get("type") == "run_error":
        return JSONResponse(status_code=500, content={"error": {"message": final.get("error", "sub-agent run failed")}})
    return JSONResponse(content={"results": final.get("results", []), "usage": final.get("usage", {})})
