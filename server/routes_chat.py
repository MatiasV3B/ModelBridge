"""OpenAI Chat Completions API endpoint."""

import json
import logging
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Any, Dict, Union
from core.bridge_engine import bridge_engine

router = APIRouter(tags=["Chat Completions"])
logger = logging.getLogger("antigravity_bridge")


class MessageItem(BaseModel):
    role: str
    content: Union[str, List[Any], None] = ""
    name: Optional[str] = None


class ChatCompletionRequest(BaseModel):
    model: Optional[str] = None
    messages: List[Dict[str, Any]] = Field(default_factory=list)
    stream: Optional[bool] = False
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    max_tokens: Optional[int] = None
    presence_penalty: Optional[float] = None
    frequency_penalty: Optional[float] = None
    user: Optional[str] = None

    class Config:
        extra = "allow"


async def sse_event_generator(req_data: ChatCompletionRequest, **kwargs):
    """Generate Server-Sent Events for streaming chat completions."""
    try:
        async for chunk in bridge_engine.generate_stream(
            messages=req_data.messages,
            model=req_data.model,
            temperature=req_data.temperature,
            max_tokens=req_data.max_tokens,
            **kwargs
        ):
            payload = f"data: {json.dumps(chunk)}\n\n"
            yield payload.encode("utf-8")

        # Standard OpenAI stream termination
        yield b"data: [DONE]\n\n"
    except Exception as e:
        logger.error(f"Streaming error: {e}")
        err_chunk = {
            "error": {
                "message": str(e),
                "type": "server_error",
                "param": None,
                "code": None,
            }
        }
        yield f"data: {json.dumps(err_chunk)}\n\n".encode("utf-8")
        yield b"data: [DONE]\n\n"


@router.post("/v1/chat/completions")
@router.post("/chat/completions")
async def create_chat_completion(request: Request):
    """Handle OpenAI Chat Completions requests (streaming & non-streaming)."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    req_data = ChatCompletionRequest(**body)

    if not req_data.messages:
        raise HTTPException(status_code=400, detail="Missing required parameter 'messages'")

    claude_mode = request.headers.get("x-claude-mode") or body.get("claude_mode")
    antigravity_mode = request.headers.get("x-antigravity-mode") or body.get("antigravity_mode")
    openai_mode = request.headers.get("x-openai-mode") or body.get("openai_mode")
    api_key = request.headers.get("x-api-key") or body.get("api_key") or request.headers.get("x-anthropic-key")
    gemini_api_key = request.headers.get("x-gemini-key") or body.get("gemini_api_key")
    openai_api_key = request.headers.get("x-openai-key") or body.get("openai_api_key")
    thinking_budget = body.get("thinking_budget")
    reasoning_effort = body.get("reasoning_effort") or body.get("thinking_effort")

    forward_kwargs = {
        "claude_mode": claude_mode,
        "antigravity_mode": antigravity_mode,
        "openai_mode": openai_mode,
        "api_key": api_key,
        "gemini_api_key": gemini_api_key,
        "openai_api_key": openai_api_key,
        "thinking_budget": thinking_budget,
        "reasoning_effort": reasoning_effort,
    }

    # Streaming mode
    if req_data.stream:
        return StreamingResponse(
            sse_event_generator(req_data, **forward_kwargs),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Content-Type": "text/event-stream",
                "X-Accel-Buffering": "no",
            },
        )

    # Non-streaming mode
    try:
        result = await bridge_engine.generate_sync(
            messages=req_data.messages,
            model=req_data.model,
            temperature=req_data.temperature,
            max_tokens=req_data.max_tokens,
            **forward_kwargs
        )
        return JSONResponse(content=result)
    except Exception as e:
        logger.error(f"Chat completion error: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "message": f"Antigravity Bridge error: {str(e)}",
                    "type": "api_error",
                    "param": None,
                    "code": "internal_error",
                }
            },
        )
