"""OpenAI Responses API endpoint."""

import time
import uuid
import json
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Any, Dict, Union
from core.bridge_engine import bridge_engine

router = APIRouter(tags=["Responses"])


class ResponseRequest(BaseModel):
    model: Optional[str] = None
    input: Union[str, List[Any]] = ""
    instructions: Optional[str] = None
    stream: Optional[bool] = False
    temperature: Optional[float] = None
    max_output_tokens: Optional[int] = None

    class Config:
        extra = "allow"


@router.post("/v1/responses")
@router.post("/responses")
async def create_response(request: Request):
    """Handle OpenAI Responses API requests."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    req_data = ResponseRequest(**body)

    messages = []
    if req_data.instructions:
        messages.append({"role": "system", "content": req_data.instructions})

    if isinstance(req_data.input, str):
        messages.append({"role": "user", "content": req_data.input})
    elif isinstance(req_data.input, list):
        for item in req_data.input:
            if isinstance(item, dict) and "role" in item:
                messages.append(item)
            elif isinstance(item, str):
                messages.append({"role": "user", "content": item})
            else:
                messages.append({"role": "user", "content": str(item)})

    if not messages:
        messages.append({"role": "user", "content": "Hello"})

    resp_id = f"resp-{uuid.uuid4().hex[:20]}"
    created_time = int(time.time())

    if req_data.stream:
        async def response_stream_generator():
            async for chunk in bridge_engine.generate_stream(
                messages=messages,
                model=req_data.model,
                temperature=req_data.temperature,
                max_tokens=req_data.max_output_tokens,
            ):
                choices = chunk.get("choices", [])
                delta = choices[0].get("delta", {}) if choices else {}
                content = delta.get("content", "")
                if content:
                    event = {
                        "id": resp_id,
                        "object": "response.text.delta",
                        "delta": content,
                    }
                    yield f"data: {json.dumps(event)}\n\n".encode("utf-8")
            yield b"data: [DONE]\n\n"

        return StreamingResponse(
            response_stream_generator(),
            media_type="text/event-stream"
        )

    # Sync
    result = await bridge_engine.generate_sync(
        messages=messages,
        model=req_data.model,
        temperature=req_data.temperature,
        max_tokens=req_data.max_output_tokens,
    )

    msg_content = result["choices"][0]["message"]["content"]
    return {
        "id": resp_id,
        "object": "response",
        "created_at": created_time,
        "model": result.get("model", req_data.model),
        "status": "completed",
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "text",
                        "text": msg_content
                    }
                ]
            }
        ],
        "usage": result.get("usage", {})
    }
