"""Code execution and document export endpoints for Antigravity Bridge."""

import sys
import time
import subprocess
from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/code", tags=["Code Execution"])


class CodeExecutionRequest(BaseModel):
    code: str
    language: Optional[str] = "python"  # "python", "javascript", "powershell", "bash"
    timeout: Optional[int] = 15


@router.post("/execute")
async def execute_code(req: CodeExecutionRequest):
    """Safely executes code in a dedicated subprocess and returns stdout, stderr and metrics."""
    lang = (req.language or "python").lower()
    timeout = min(max(1, req.timeout or 15), 60)
    start_time = time.time()

    if lang in ["python", "py"]:
        cmd = [sys.executable, "-c", req.code]
    elif lang in ["javascript", "js", "node"]:
        cmd = ["node", "-e", req.code]
    elif lang in ["powershell", "ps1"] and sys.platform == "win32":
        cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", req.code]
    elif lang in ["bash", "sh"]:
        cmd = ["bash", "-c", req.code]
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported execution language: {lang}")

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        elapsed_ms = round((time.time() - start_time) * 1000, 1)
        return {
            "status": "ok",
            "language": lang,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "returncode": proc.returncode,
            "execution_time_ms": elapsed_ms,
        }
    except subprocess.TimeoutExpired:
        return {
            "status": "timeout",
            "language": lang,
            "stdout": "",
            "stderr": f"Execution timed out after {timeout} seconds.",
            "returncode": -1,
            "execution_time_ms": timeout * 1000,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to execute code: {e}")
