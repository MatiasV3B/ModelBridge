"""macOS helpers: where the CLIs live, opening Terminal.app and auto-start with a LaunchAgent.

On Windows none of this is used; every caller checks IS_MAC first.
"""

import os
import plistlib
import shlex
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

IS_MAC = sys.platform == "darwin"

LAUNCH_AGENT_LABEL = "com.matiasv3b.modelbridge"
LAUNCH_AGENT = Path.home() / "Library" / "LaunchAgents" / f"{LAUNCH_AGENT_LABEL}.plist"
ROOT = Path(__file__).resolve().parent.parent


def bin_dirs() -> List[Path]:
    """Folders where Homebrew, npm, uv, cargo and the official installers put CLIs on a Mac.

    Apps opened from Finder or launchd get a minimal PATH (/usr/bin:/bin...), so shutil.which misses these.
    """
    home = Path.home()
    return [
        home / ".local" / "bin",
        home / ".claude" / "local",
        home / ".npm-global" / "bin",
        home / ".volta" / "bin",
        home / ".bun" / "bin",
        home / ".cargo" / "bin",
        home / ".agy" / "bin",
        home / "agy" / "bin",
        Path("/opt/homebrew/bin"),
        Path("/usr/local/bin"),
    ]


def find_bin(name: str) -> Optional[str]:
    for folder in bin_dirs():
        candidate = folder / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    # nvm keeps one bin folder per Node version
    for candidate in sorted((Path.home() / ".nvm" / "versions" / "node").glob(f"*/bin/{name}"), reverse=True):
        if os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def extend_path() -> None:
    """Add the usual CLI folders to PATH so child processes (claude, codex, agy, node) are found."""
    current = os.environ.get("PATH", "").split(os.pathsep)
    extra = [str(d) for d in bin_dirs() if d.is_dir() and str(d) not in current]
    if extra:
        os.environ["PATH"] = os.pathsep.join(extra + current)


def _applescript_str(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def open_terminal(command: str) -> None:
    """Run a shell command in a new Terminal.app window."""
    script = (f'tell application "Terminal"\n'
              f'  activate\n'
              f'  do script {_applescript_str(command)}\n'
              f'end tell')
    subprocess.Popen(["osascript", "-e", script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def login_shell_command(exe: str, *args: str, auto_close: bool = False) -> str:
    cmd = " ".join(shlex.quote(p) for p in (exe, *args))
    if auto_close:
        cmd += "; echo 'Autenticacion completada con exito. Cerrando...'; sleep 2; exit"
    return cmd


def notify(title: str, message: str) -> None:
    script = f"display notification {_applescript_str(message)} with title {_applescript_str(title)}"
    subprocess.run(["osascript", "-e", script], capture_output=True, timeout=10)


# ───────────── auto-start (LaunchAgent) ─────────────

def _python() -> str:
    venv = ROOT / ".venv" / "bin" / "python"
    saved = ROOT / ".python-path"
    if saved.exists():
        path = saved.read_text(encoding="utf-8").strip()
        if path:
            return path
    return str(venv) if venv.exists() else sys.executable


def set_login_item(enabled: bool) -> None:
    uid = str(os.getuid())
    if not enabled:
        if LAUNCH_AGENT.exists():
            subprocess.run(["launchctl", "bootout", f"gui/{uid}", str(LAUNCH_AGENT)], capture_output=True)
            LAUNCH_AGENT.unlink()
        return
    LAUNCH_AGENT.parent.mkdir(parents=True, exist_ok=True)
    log = Path.home() / ".antigravity_bridge" / "launchagent.log"
    plist = {
        "Label": LAUNCH_AGENT_LABEL,
        "ProgramArguments": [_python(), str(ROOT / "main.py"), "--headless"],
        "WorkingDirectory": str(ROOT),
        "RunAtLoad": True,
        "KeepAlive": False,
        "StandardOutPath": str(log),
        "StandardErrorPath": str(log),
    }
    with open(LAUNCH_AGENT, "wb") as f:
        plistlib.dump(plist, f)


def is_login_item_enabled() -> bool:
    return LAUNCH_AGENT.exists()
