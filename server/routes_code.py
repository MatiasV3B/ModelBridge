"""Code execution endpoint for Antigravity Bridge.

Running code from a request is a hard limit: it is OFF unless the person turned it on on this computer
(`"code_execution": "isolated"` in ~/.antigravity_bridge/config.json, or the BRIDGE_CODE_EXECUTION environment
variable). It can never be switched on over HTTP, so a web page or an injected prompt cannot do it.

"isolated" is a best effort, NOT a security boundary: only Python and JavaScript, in a fresh empty folder, with a
cleaned environment (no API keys or tokens), a time limit and a cap on the output. The code can still read the
files this user can read. Shells (PowerShell, bash) are never available here.
"""

import os
import sys
import time
import shutil
import tempfile
import subprocess
from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException

from core.config import bridge_config
from core import permissions

router = APIRouter(prefix="/api/code", tags=["Code Execution"])

MAX_OUTPUT_CHARS = 64 * 1024
# The only variables the child process receives (no keys, tokens or user settings).
_SAFE_ENV_KEYS = ("PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "LANG", "LC_ALL")


class CodeExecutionRequest(BaseModel):
    code: str
    language: Optional[str] = "python"  # "python" or "javascript"
    timeout: Optional[int] = 15


def _clean_env(workdir: str) -> dict:
    env = {k: os.environ[k] for k in _SAFE_ENV_KEYS if k in os.environ}
    env.update({"TEMP": workdir, "TMP": workdir, "TMPDIR": workdir, "HOME": workdir, "USERPROFILE": workdir})
    return env


def _python_exe() -> str:
    """The Bridge usually runs under pythonw.exe, which has no stdout to capture: use the python.exe next to it."""
    exe = sys.executable
    if exe.lower().endswith("pythonw.exe"):
        sibling = exe[: -len("pythonw.exe")] + "python.exe"
        if os.path.exists(sibling):
            return sibling
    return exe


def _cap(text: str) -> str:
    return text if len(text) <= MAX_OUTPUT_CHARS else text[:MAX_OUTPUT_CHARS] + "\n[output cut]"


@router.post("/execute")
async def execute_code(req: CodeExecutionRequest):
    """Runs Python or JavaScript in an isolated subprocess, only when the person enabled it locally."""
    if permissions.code_execution_policy(bridge_config.code_execution) != permissions.CODE_ISOLATED:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "code_execution_disabled",
                "message": "Running code from the Bridge is off. To turn it on, set \"code_execution\": \"isolated\" "
                           "in ~/.antigravity_bridge/config.json on this computer.",
            },
        )

    lang = (req.language or "python").lower()
    timeout = min(max(1, req.timeout or 15), 30)

    workdir = tempfile.mkdtemp(prefix="bridge_code_")
    try:
        if lang in ["python", "py"]:
            cmd = [_python_exe(), "-I", "-c", req.code]
        elif lang in ["javascript", "js", "node"]:
            cmd = ["node", "-e", req.code]
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported execution language: {lang} (only python and javascript)")

        start_time = time.time()
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=workdir,
                env=_clean_env(workdir),
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            return {
                "status": "ok",
                "language": lang,
                "stdout": _cap(proc.stdout),
                "stderr": _cap(proc.stderr),
                "returncode": proc.returncode,
                "execution_time_ms": round((time.time() - start_time) * 1000, 1),
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
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to execute code: {e}")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
