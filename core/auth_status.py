"""Detect the login state of the three supported providers.

Providers: Claude Code, Antigravity (Google account) and Codex CLI.
Detection only reads local state (CLI status command or credential files) and
never sends or logs tokens.
"""

import base64
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

from core.config import bridge_config

NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

PROVIDER_KEYS = ("claude", "antigravity", "codex")


@dataclass
class ProviderStatus:
    key: str
    installed: bool = False
    logged_in: bool = False
    account: str = ""

    @property
    def active(self) -> bool:
        return self.installed and self.logged_in


def _read_json(path: Path) -> Optional[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def parse_claude_status(raw: str) -> Tuple[bool, str]:
    """Parse the JSON printed by `claude auth status`."""
    if not raw:
        return False, ""
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end <= start:
        return False, ""
    try:
        data = json.loads(raw[start:end + 1])
    except ValueError:
        return False, ""
    if not isinstance(data, dict) or not data.get("loggedIn"):
        return False, ""
    return True, str(data.get("email") or data.get("orgName") or "")


def read_antigravity_login(gemini_dir: Path) -> Tuple[bool, str]:
    """Antigravity authenticates with a Google account stored under ~/.gemini."""
    creds = _read_json(gemini_dir / "oauth_creds.json") or {}
    has_token = bool(creds.get("refresh_token") or creds.get("access_token"))
    accounts_file = gemini_dir / "google_accounts.json"
    accounts = _read_json(accounts_file) or {}
    active = str(accounts.get("active") or "")
    logged_in = has_token and (bool(active) or not accounts_file.exists())
    return logged_in, active


def _jwt_email(token: Optional[str]) -> str:
    if not token or token.count(".") < 2:
        return ""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
        return str(data.get("email") or "")
    except (ValueError, UnicodeError):
        return ""


def find_codex_binary() -> Optional[str]:
    """Find the full path to codex.exe or codex.cmd and ensure its folder is in PATH."""
    exe = shutil.which("codex") or shutil.which("codex.cmd") or shutil.which("codex.exe")
    if exe and os.path.exists(exe):
        return exe

    local_app_data = os.environ.get("LOCALAPPDATA")
    candidates = []
    if local_app_data:
        candidates.append(Path(local_app_data) / "Programs" / "OpenAI" / "Codex" / "bin" / "codex.exe")
    candidates.append(Path.home() / "AppData" / "Local" / "Programs" / "OpenAI" / "Codex" / "bin" / "codex.exe")
    candidates.append(Path.home() / "AppData" / "Roaming" / "npm" / "codex.cmd")
    candidates.append(Path.home() / "AppData" / "Roaming" / "npm" / "codex.exe")
    candidates.append(Path.home() / ".cargo" / "bin" / "codex.exe")

    for c in candidates:
        if c.exists():
            bin_dir = str(c.parent)
            if bin_dir not in os.environ.get("PATH", ""):
                os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
            return str(c)

    return None


def read_codex_login(codex_home: Path) -> Tuple[bool, str]:
    """Codex CLI stores ChatGPT tokens, API key or custom provider in <CODEX_HOME>/auth.json or config.toml."""
    data = _read_json(codex_home / "auth.json")
    if data:
        tokens = data.get("tokens") if isinstance(data.get("tokens"), dict) else {}
        if tokens.get("access_token") or tokens.get("refresh_token"):
            return True, _jwt_email(tokens.get("id_token")) or "ChatGPT Account"
        if data.get("OPENAI_API_KEY"):
            return True, "API key"

    # Also check config.toml for configured model providers or api keys
    config_toml = codex_home / "config.toml"
    if config_toml.exists():
        try:
            content = config_toml.read_text(encoding="utf-8")
            if "api_key" in content or "model_provider" in content:
                # Extract provider name if available
                import re
                prov_match = re.search(r'name\s*=\s*"([^"]+)"', content)
                prov_name = prov_match.group(1) if prov_match else "Codex CLI"
                return True, prov_name
        except Exception:
            pass

    return False, ""


def _codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")


def _run_capture(cmd: list, timeout: int = 12) -> str:
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=NO_WINDOW,
        )
        return proc.stdout or ""
    except (OSError, subprocess.SubprocessError):
        return ""


def check_claude() -> ProviderStatus:
    exe = shutil.which("claude")
    if not exe:
        return ProviderStatus("claude")
    logged_in, account = parse_claude_status(_run_capture([exe, "auth", "status"]))
    return ProviderStatus("claude", True, logged_in, account)


def check_antigravity() -> ProviderStatus:
    agy = bridge_config.agy_binary_path
    installed = bool((agy and os.path.exists(agy)) or shutil.which("agy"))
    logged_in, account = read_antigravity_login(Path.home() / ".gemini")
    return ProviderStatus("antigravity", installed, logged_in, account)


def check_codex() -> ProviderStatus:
    exe = find_codex_binary()
    installed = bool(exe)
    logged_in, account = read_codex_login(_codex_home())
    return ProviderStatus("codex", installed, logged_in, account)


def check_all() -> Dict[str, ProviderStatus]:
    return {
        "claude": check_claude(),
        "antigravity": check_antigravity(),
        "codex": check_codex(),
    }


def login_command(key: str) -> Optional[str]:
    """Windows `start` command line that opens a terminal with the login flow and auto-closes when done."""
    if key == "claude":
        exe = shutil.which("claude") or "claude"
        return f'start "Claude Code - Iniciar sesion" cmd /c ""{exe}" auth login & echo Autenticacion completada con exito. Cerrando... & timeout /t 2 >nul"'
    if key == "antigravity":
        agy = bridge_config.agy_binary_path
        if not agy or not os.path.exists(agy):
            return None
        return (
            f'start "Antigravity - Iniciar sesion" cmd /c '
            f'""{agy}" & echo Autenticacion completada con exito. Cerrando... & timeout /t 2 >nul"'
        )
    if key == "codex":
        exe = find_codex_binary() or "codex"
        return f'start "Codex CLI - Iniciar sesion" cmd /c ""{exe}" login & echo Autenticacion completada con exito. Cerrando... & timeout /t 2 >nul"'
    return None


def install_command(key: str) -> Optional[str]:
    """Terminal command (shown to the user) that installs a missing CLI."""
    commands = {
        "claude": "winget install Anthropic.ClaudeCode",
        "codex": "npm install -g @openai/codex",
    }
    cmd = commands.get(key)
    if not cmd:
        return None
    return f'start "Instalar CLI" cmd /k "{cmd}"'
