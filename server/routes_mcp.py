"""Model Context Protocol (MCP) server routes for Model Bridge.

Enables external local AI agents (Claude Code, Cursor, Claude Desktop, etc.)
to discover tools and command the user's active Autono browser session to
perform navigation, clicks, typing, scraping, and autonomous tasks.
"""

import time
import uuid
import json
import asyncio
import logging
from typing import Optional, Dict, Any, List
from pydantic import BaseModel
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

logger = logging.getLogger("model_bridge.mcp")

router = APIRouter(tags=["Model Context Protocol (MCP)"])

# In-memory action queue and pending futures for browser execution
action_queue: asyncio.Queue = asyncio.Queue()
pending_action_futures: Dict[str, asyncio.Future] = {}
last_browser_ping: float = 0.0

# Active SSE sessions for MCP
sse_sessions: Dict[str, asyncio.Queue] = {}


class BrowserActionRequest(BaseModel):
    action: str  # "browser_task", "get_active_tab", "navigate", "click", "type", "screenshot"
    params: Optional[Dict[str, Any]] = None
    timeout: Optional[int] = 45


class BrowserActionResult(BaseModel):
    action_id: str
    status: str  # "ok" or "error"
    result: Optional[Any] = None
    error: Optional[str] = None


# Tool catalog exposed via MCP
MCP_TOOLS_SPEC = [
    {
        "name": "browser_task",
        "description": "Execute an autonomous multi-step browsing task or goal inside the user's active Chrome browser session using Autono.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "goal": {
                    "type": "string",
                    "description": "The goal, query, or automation task to execute in the browser (e.g. 'Search for hotels in Tokyo on booking.com and list top 3')"
                },
                "mode": {
                    "type": "string",
                    "enum": ["cowork", "chat"],
                    "default": "cowork",
                    "description": "Use 'cowork' for active browser automation (clicks, forms) or 'chat' for answering questions with page context."
                }
            },
            "required": ["goal"]
        }
    },
    {
        "name": "browser_get_active_tab",
        "description": "Retrieve information and text content from the user's currently active web browser tab.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "browser_navigate",
        "description": "Navigate the user's active browser tab to a specified web URL.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Full destination web address (e.g. 'https://github.com/trending')"
                }
            },
            "required": ["url"]
        }
    },
    {
        "name": "browser_click",
        "description": "Click an interactive element in the user's active web browser tab by selector or text description.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "selector": {
                    "type": "string",
                    "description": "CSS selector or accessible description of element to click"
                }
            },
            "required": ["selector"]
        }
    },
    {
        "name": "browser_type",
        "description": "Type text into an input field or textarea in the active web browser tab.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "selector": {
                    "type": "string",
                    "description": "CSS selector of the input element"
                },
                "text": {
                    "type": "string",
                    "description": "Text string to type into the field"
                }
            },
            "required": ["selector", "text"]
        }
    },
    {
        "name": "browser_screenshot",
        "description": "Capture a live screenshot of the user's active browser tab (returns base64 PNG data URL).",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    }
]


# ─── Internal Dispatch Helper ────────────────────────────────────────────────
async def dispatch_browser_action(action: str, params: Optional[Dict[str, Any]] = None, timeout: int = 45) -> Dict[str, Any]:
    """Queue an action for Autono and await execution response."""
    global last_browser_ping
    action_id = f"act-{uuid.uuid4().hex[:12]}"
    loop = asyncio.get_running_loop()
    fut = loop.create_future()
    pending_action_futures[action_id] = fut

    # Push action to queue for Autono
    await action_queue.put({
        "action_id": action_id,
        "action": action,
        "params": params or {},
        "created_at": time.time(),
        "timeout": timeout
    })

    try:
        # Await completion by Autono
        res = await asyncio.wait_for(fut, timeout=float(timeout))
        return res
    except asyncio.TimeoutError:
        pending_action_futures.pop(action_id, None)
        is_connected = (time.time() - last_browser_ping) < 25
        if not is_connected:
            return {
                "status": "error",
                "error": "Autono extension is not connected to Model Bridge or MCP bridge is disabled in Autono settings. Please open Chrome, open the Autono side panel, and ensure 'Autono Browser MCP' is enabled in Settings -> Tools & MCP."
            }
        return {
            "status": "error",
            "error": f"Action '{action}' timed out after {timeout} seconds waiting for browser execution."
        }
    except Exception as e:
        pending_action_futures.pop(action_id, None)
        return {"status": "error", "error": str(e)}


# ─── HTTP Endpoints for Autono Browser Extension ─────────────────────────────
@router.get("/api/mcp/status")
async def get_mcp_status():
    """Return status of MCP bridge and whether Autono is actively listening."""
    is_connected = (time.time() - last_browser_ping) < 25
    return {
        "status": "online",
        "mcp_version": "2024-11-05",
        "browser_connected": is_connected,
        "pending_actions_count": action_queue.qsize(),
        "tools_count": len(MCP_TOOLS_SPEC)
    }


@router.get("/api/mcp/pending_actions")
async def get_pending_actions(timeout: int = 15):
    """Polled by Autono extension to retrieve pending actions from external agents."""
    global last_browser_ping
    last_browser_ping = time.time()

    # If action ready immediately, return it
    if not action_queue.empty():
        item = await action_queue.get()
        return {"has_action": True, "action": item}

    # Otherwise wait briefly (long polling)
    try:
        item = await asyncio.wait_for(action_queue.get(), timeout=min(timeout, 20))
        return {"has_action": True, "action": item}
    except asyncio.TimeoutError:
        return {"has_action": False}


@router.post("/api/mcp/action_result")
async def post_action_result(payload: BrowserActionResult):
    """Called by Autono extension to report action completion and results."""
    global last_browser_ping
    last_browser_ping = time.time()

    fut = pending_action_futures.pop(payload.action_id, None)
    if fut and not fut.done():
        fut.set_result({
            "status": payload.status,
            "result": payload.result,
            "error": payload.error
        })
        return {"status": "ok", "delivered": True}
    return {"status": "ignored", "delivered": False}


@router.post("/api/mcp/action")
async def execute_direct_action(req: BrowserActionRequest):
    """Direct HTTP endpoint to execute a browser action via Autono."""
    res = await dispatch_browser_action(req.action, req.params, req.timeout or 45)
    return res


# ─── Standard MCP JSON-RPC 2.0 Protocol Endpoint (POST /mcp) ─────────────────
@router.post("/mcp")
async def handle_mcp_jsonrpc(request: Request):
    """Standard JSON-RPC 2.0 endpoint for MCP clients."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}, "id": None})

    msg_id = body.get("id")
    method = body.get("method", "")
    params = body.get("params", {})

    # 1. Initialize
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {}
                },
                "serverInfo": {
                    "name": "autono-browser-mcp",
                    "version": "1.0.0"
                }
            }
        }

    # 2. Notifications (no response required)
    if method in ("notifications/initialized", "notifications/cancelled"):
        return JSONResponse(content={})

    # 3. List Tools
    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "tools": MCP_TOOLS_SPEC
            }
        }

    # 4. Call Tool
    if method == "tools/call":
        tool_name = params.get("name", "")
        tool_args = params.get("arguments", {})

        action_map = {
            "browser_task": "browser_task",
            "browser_get_active_tab": "get_active_tab",
            "browser_navigate": "navigate",
            "browser_click": "click",
            "browser_type": "type",
            "browser_screenshot": "screenshot"
        }

        action = action_map.get(tool_name)
        if not action:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {
                    "code": -32601,
                    "message": f"Method/Tool '{tool_name}' not found."
                }
            }

        res = await dispatch_browser_action(action, tool_args, timeout=60)
        if res.get("status") == "error":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": f"Error executing browser action: {res.get('error', 'Unknown error')}"
                        }
                    ],
                    "isError": True
                }
            }

        data_str = json.dumps(res.get("result", {}), ensure_ascii=False, indent=2) if isinstance(res.get("result"), (dict, list)) else str(res.get("result") or "Action completed successfully.")
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": data_str
                    }
                ],
                "isError": False
            }
        }

    # 5. Ping
    if method == "ping":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}

    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "error": {
            "code": -32601,
            "message": f"Method '{method}' not implemented."
        }
    }


# ─── Standard MCP SSE Transport (GET /mcp/sse, POST /mcp/messages) ────────────
@router.get("/mcp/sse")
async def mcp_sse_endpoint(request: Request):
    """Server-Sent Events endpoint for MCP clients like Cursor."""
    session_id = uuid.uuid4().hex
    queue: asyncio.Queue = asyncio.Queue()
    sse_sessions[session_id] = queue

    async def event_generator():
        try:
            # First event: endpoint URL for posting messages
            endpoint_url = f"/mcp/messages?session_id={session_id}"
            yield f"event: endpoint\ndata: {endpoint_url}\n\n"

            while True:
                if await request.is_disconnected():
                    break
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"event: message\ndata: {json.dumps(data)}\n\n"
                except asyncio.TimeoutError:
                    # Keepalive comment
                    yield ": ping\n\n"
        finally:
            sse_sessions.pop(session_id, None)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.post("/mcp/messages")
async def mcp_post_message(request: Request, session_id: str):
    """Receive messages for an active SSE session."""
    queue = sse_sessions.get(session_id)
    if not queue:
        raise HTTPException(status_code=404, detail="SSE session not found or expired.")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body.")

    # Process JSON-RPC request and queue response
    msg_id = body.get("id")
    method = body.get("method", "")
    params = body.get("params", {})

    if method == "initialize":
        await queue.put({
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "autono-browser-mcp", "version": "1.0.0"}
            }
        })
    elif method == "tools/list":
        await queue.put({
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {"tools": MCP_TOOLS_SPEC}
        })
    elif method == "tools/call":
        tool_name = params.get("name", "")
        tool_args = params.get("arguments", {})
        action_map = {
            "browser_task": "browser_task",
            "browser_get_active_tab": "get_active_tab",
            "browser_navigate": "navigate",
            "browser_click": "click",
            "browser_type": "type",
            "browser_screenshot": "screenshot"
        }
        action = action_map.get(tool_name)
        if not action:
            await queue.put({
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32601, "message": f"Tool '{tool_name}' not found."}
            })
        else:
            res = await dispatch_browser_action(action, tool_args, timeout=60)
            data_str = json.dumps(res.get("result", {}), ensure_ascii=False) if isinstance(res.get("result"), (dict, list)) else str(res.get("result") or "Done")
            await queue.put({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": data_str}],
                    "isError": res.get("status") == "error"
                }
            })

    return {"status": "accepted"}
