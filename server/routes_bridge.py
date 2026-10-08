"""Bridge lifecycle: a hard restart that frees the port and starts a clean process."""

import logging
import os
import subprocess
import sys
import asyncio
import threading

from fastapi import APIRouter, HTTPException

from pydantic import BaseModel

from core import updater
from core.config import bridge_config

router = APIRouter(tags=["Bridge"])
logger = logging.getLogger("antigravity_bridge")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _windowless_python() -> str:
    exe = sys.executable
    if os.name == "nt" and exe.lower().endswith("python.exe"):
        candidate = exe[:-len("python.exe")] + "pythonw.exe"
        if os.path.exists(candidate):
            return candidate
    return exe


def _schedule_restart() -> None:
    """Start the helper that replaces this process with a fresh Bridge (see core/relauncher.py)."""
    if getattr(sys, "frozen", False):
        raise HTTPException(status_code=501, detail="This is the packaged app: close it and open it again.")
    main_py = os.path.join(ROOT, "main.py")
    port = bridge_config.port
    # Always headless: the restarted Bridge is the server; the window (if there was one) is not reopened.
    command = [_windowless_python(), main_py, "--headless", "--port", str(port)]
    helper = [_windowless_python(), os.path.join(ROOT, "core", "relauncher.py"),
              str(os.getpid()), str(port), ROOT, "--", *command]
    flags = (0x00000008 | 0x00000200 | 0x08000000) if os.name == "nt" else 0
    try:
        subprocess.Popen(helper, cwd=ROOT, creationflags=flags, close_fds=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         **({} if os.name == "nt" else {"start_new_session": True}))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not start the restart helper: {exc}")
    logger.warning("Hard restart requested: the Bridge will be replaced in a moment.")
    # The helper also kills this process; this timer is only a backstop if it is slow.
    threading.Timer(8.0, lambda: os._exit(0)).start()


@router.post("/v1/bridge/restart")
async def restart_bridge():
    """Close this Bridge completely (and any leftover of it) and open a new one.

    The extension polls /health afterwards; the new process is up again in a few seconds.
    """
    _schedule_restart()
    return {"status": "restarting"}


class ExtensionRequest(BaseModel):
    ext_id: str = ""
    ext_path: str = ""


@router.get("/v1/update/status")
async def update_status(ext_id: str = "", force: bool = False, ext_path: str = ""):
    """Is there a newer Bridge / Autono on GitHub than what is installed here?"""
    return await asyncio.to_thread(updater.status, ext_id, force, ext_path)


@router.post("/v1/update/bridge")
async def update_bridge():
    """Download the new Bridge code and restart into it."""
    try:
        result = await asyncio.to_thread(updater.apply_bridge)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    _schedule_restart()
    return {"status": "updated", **result}


@router.post("/v1/update/extension")
async def update_extension(req: ExtensionRequest):
    """Replace the extension's files on disk; the extension then reloads itself."""
    try:
        return {"status": "updated", **await asyncio.to_thread(updater.apply_extension, req.ext_id, req.ext_path)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
