"""Permission mode of the Bridge (read and set from the Autono Settings tab)."""

from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, Header, HTTPException

from core.config import bridge_config
from core import permissions

router = APIRouter(prefix="/api/permissions", tags=["Permissions"])


class PermissionModeRequest(BaseModel):
    mode: str


def _state() -> dict:
    return {
        "mode": permissions.normalize_mode(bridge_config.permission_mode),
        "modes": list(permissions.MODES),
        "hard_limits": permissions.hard_limits(permissions.code_execution_policy(bridge_config.code_execution)),
    }


@router.get("")
async def get_permissions():
    """Current mode plus the limits that apply in every mode."""
    return _state()


@router.post("")
async def set_permissions(req: PermissionModeRequest, origin: Optional[str] = Header(default=None)):
    """Changes the mode. A web page cannot do it (its Origin is http/https); the extension can."""
    if not permissions.is_trusted_origin(origin):
        raise HTTPException(status_code=403, detail="Only the Autono extension can change the permission mode.")
    mode = (req.mode or "").strip().lower()
    if mode not in permissions.MODES:
        raise HTTPException(status_code=422, detail=f"mode must be one of: {', '.join(permissions.MODES)}")
    bridge_config.permission_mode = mode
    bridge_config.save()
    return _state()
