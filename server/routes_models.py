from fastapi import APIRouter, HTTPException, Request
from core.model_registry import model_registry

router = APIRouter(tags=["Models"])


def _extract_provider_from_path(request: Request):
    path = request.url.path.lower()
    if path.startswith("/antigravity"):
        return "antigravity"
    if path.startswith("/claude") or path.startswith("/cloud"):
        return "claude"
    if path.startswith("/openai"):
        return "openai"
    return request.headers.get("x-provider") or None


@router.get("/v1/models")
@router.get("/models")
@router.get("/v1/v1/models")
async def list_models(request: Request):
    """List available models and aliases filtered by provider (or all if not specified)."""
    provider = _extract_provider_from_path(request)
    models = model_registry.to_openai_format(provider=provider)
    return {
        "object": "list",
        "data": models,
        "has_more": False,
    }


@router.get("/v1/models/{model_id}")
@router.get("/models/{model_id}")
@router.get("/v1/v1/models/{model_id}")
async def retrieve_model(model_id: str, request: Request):
    """Retrieve specific model details."""
    provider = _extract_provider_from_path(request)
    models = model_registry.to_openai_format(provider=provider)
    for m in models:
        if m["id"].lower() == model_id.lower():
            return m

    # If it's a valid resolved model
    resolved = model_registry.resolve_model(model_id)
    return {
        "id": model_id,
        "object": "model",
        "created": 1700000000,
        "owned_by": "antigravity",
        "root": resolved,
        "parent": None,
    }


@router.get("/v1/usage-limits")
@router.get("/usage-limits")
@router.get("/v1/quota")
@router.get("/quota")
@router.get("/v1/usage")
@router.get("/usage")
async def get_live_quota(refresh: bool = False):
    """Retrieve live quota directly from Antigravity CLI (agy --print /usage)."""
    from core.quota_manager import quota_manager
    live_quota = quota_manager.fetch_quota(force=refresh)
    return {
        "object": "antigravity_quota",
        "gemini": live_quota["gemini"],
        "claude_gpt": live_quota["claude_gpt"],
        "raw_output": live_quota["raw_output"],
        "last_updated": live_quota["last_updated"],
    }
