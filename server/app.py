"""FastAPI application setup and server lifecycle manager."""

import time
import uvicorn
import threading
from typing import Optional
from pydantic import BaseModel
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from core.config import bridge_config
from core.bridge_engine import metrics
from core.model_registry import model_registry
from server.routes_models import router as models_router
from server.routes_files import router as files_router
from server.routes_chat import router as chat_router
from server.routes_responses import router as responses_router
from server.routes_power import router as power_router, trigger_toast, ToastNotificationRequest
from server.routes_code import router as code_router
from server.routes_claude import router as claude_router
from server.routes_mcp import router as mcp_router

START_TIME = time.time()

app = FastAPI(
    title="Model Bridge (OpenAI, Claude Agent & MCP Server)",
    description="Localhost bridge connecting AI clients, Claude Code and local agents via MCP to Antigravity and browser automation.",
    version="1.2.0",
)

# Enable CORS for all local web clients (LibreChat, Open WebUI, browser extensions, etc.)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(models_router)
app.include_router(files_router)
app.include_router(chat_router)
app.include_router(claude_router)
app.include_router(mcp_router)
app.include_router(responses_router)
app.include_router(power_router)
app.include_router(code_router)


@app.get("/")
@app.get("/health")
async def health_check():
    """Health check returning bridge status and active configuration."""
    return {
        "status": "online",
        "service": "Antigravity Bridge",
        "version": "1.0.0",
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "default_model": bridge_config.default_model,
        "engine_mode": bridge_config.engine_mode,
        "openai_compatibility": {
            "chat_completions": "/v1/chat/completions",
            "responses": "/v1/responses",
            "models": "/v1/models",
            "files": "/v1/files",
        },
    }


@app.get("/api/metrics")
async def get_metrics():
    """Endpoint for GUI to fetch live metrics and request logs."""
    return metrics.to_dict()


@app.post("/api/models/refresh")
async def refresh_models():
    """Refresh models list from Antigravity CLI."""
    models = model_registry.refresh_models()
    return {"status": "ok", "models": models}


class ConfigUpdateRequest(BaseModel):
    antigravity_mode: Optional[str] = None
    claude_mode: Optional[str] = None
    openai_mode: Optional[str] = None
    gemini_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    default_model: Optional[str] = None
    engine_mode: Optional[str] = None


@app.get("/api/config")
async def get_bridge_config():
    """Retrieve active bridge configuration including Antigravity, Claude, and OpenAI modes."""
    import os
    return {
        "antigravity_mode": getattr(bridge_config, "antigravity_mode", "desktop"),
        "claude_mode": getattr(bridge_config, "claude_mode", "desktop"),
        "openai_mode": getattr(bridge_config, "openai_mode", "desktop"),
        "has_gemini_key": bool(bridge_config.gemini_api_key or os.environ.get("GEMINI_API_KEY")),
        "has_anthropic_key": bool(bridge_config.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY")),
        "has_openai_key": bool(bridge_config.openai_api_key or os.environ.get("OPENAI_API_KEY")),
        "gemini_api_key": bridge_config.gemini_api_key or "",
        "anthropic_api_key": bridge_config.anthropic_api_key or "",
        "openai_api_key": bridge_config.openai_api_key or "",
        "default_model": bridge_config.default_model,
        "engine_mode": bridge_config.engine_mode,
    }


@app.post("/api/config")
async def update_bridge_config(req: ConfigUpdateRequest):
    """Update and persist bridge configuration for all provider engines."""
    if req.antigravity_mode is not None:
        bridge_config.antigravity_mode = req.antigravity_mode
    if req.claude_mode is not None:
        bridge_config.claude_mode = req.claude_mode
    if req.openai_mode is not None:
        bridge_config.openai_mode = req.openai_mode
    if req.gemini_api_key is not None:
        bridge_config.gemini_api_key = req.gemini_api_key.strip() or None
    if req.anthropic_api_key is not None:
        bridge_config.anthropic_api_key = req.anthropic_api_key.strip() or None
    if req.openai_api_key is not None:
        bridge_config.openai_api_key = req.openai_api_key.strip() or None
    if req.default_model is not None:
        bridge_config.default_model = req.default_model
    if req.engine_mode is not None:
        bridge_config.engine_mode = req.engine_mode
    bridge_config.save()
    import os
    return {
        "status": "ok",
        "antigravity_mode": getattr(bridge_config, "antigravity_mode", "desktop"),
        "claude_mode": getattr(bridge_config, "claude_mode", "desktop"),
        "openai_mode": getattr(bridge_config, "openai_mode", "desktop"),
        "has_gemini_key": bool(bridge_config.gemini_api_key or os.environ.get("GEMINI_API_KEY")),
        "has_anthropic_key": bool(bridge_config.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY")),
        "has_openai_key": bool(bridge_config.openai_api_key or os.environ.get("OPENAI_API_KEY")),
    }


@app.post("/api/toast")
@app.post("/api/notify")
async def root_trigger_toast(req: ToastNotificationRequest):
    """Convenience alias for /api/power/toast."""
    return await trigger_toast(req)


class ServerManager:
    """Manages starting and stopping Uvicorn server in a dedicated background thread."""

    def __init__(self):
        self._server: uvicorn.Server = None
        self._thread: threading.Thread = None
        self._is_running: bool = False

    @property
    def is_running(self) -> bool:
        return self._is_running

    def start(self, host: str = "127.0.0.1", port: int = 8000):
        if self._is_running:
            return

        config = uvicorn.Config(
            app=app,
            host=host,
            port=port,
            log_config=None,
            loop="asyncio",
        )
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._run_server, daemon=True)
        self._thread.start()
        self._is_running = True

    def _run_server(self):
        try:
            self._server.run()
        finally:
            self._is_running = False

    def stop(self):
        if self._server and self._is_running:
            self._server.should_exit = True
            self._is_running = False


server_manager = ServerManager()
