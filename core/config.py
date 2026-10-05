"""Configuration management for Antigravity Bridge."""

import os
import sys
import json
import shutil
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional

APP_DIR = Path.home() / ".antigravity_bridge"
CONFIG_FILE = APP_DIR / "config.json"
FILES_DIR = APP_DIR / "files"

# Ensure essential directories exist
APP_DIR.mkdir(parents=True, exist_ok=True)
FILES_DIR.mkdir(parents=True, exist_ok=True)


def find_agy_binary() -> str:
    """Find the path to agy.exe on Windows or systems."""
    # Check PATH first
    which_path = shutil.which("agy") or shutil.which("agy.exe")
    if which_path and os.path.exists(which_path):
        return which_path

    # Check Windows LocalAppData
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        agy_candidate = Path(local_app_data) / "agy" / "bin" / "agy.exe"
        if agy_candidate.exists():
            return str(agy_candidate)

    # Check user home AppData
    user_agy = Path.home() / "AppData" / "Local" / "agy" / "bin" / "agy.exe"
    if user_agy.exists():
        return str(user_agy)

    return "agy"


@dataclass
class BridgeConfig:
    host: str = "127.0.0.1"
    port: int = 8765
    default_model: str = "gemini-3.8-flash-medium"
    engine_mode: str = "cli"  # "cli" or "sdk"
    agy_binary_path: str = ""
    antigravity_mode: str = "desktop"  # "desktop" (Local Antigravity CLI) or "api" (Gemini API)
    claude_mode: str = "desktop"       # "desktop" (Claude Desktop service) or "api" (Claude API)
    openai_mode: str = "desktop"       # "desktop" (Codex Desktop CLI) or "api" (ChatGPT API)
    gemini_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    allow_tool_execution: bool = True
    auto_start_bridge: bool = True
    minimize_to_tray: bool = True
    start_with_windows: bool = True
    log_level: str = "INFO"

    def __post_init__(self):
        if not self.agy_binary_path:
            self.agy_binary_path = find_agy_binary()
        if not self.gemini_api_key:
            self.gemini_api_key = os.environ.get("GEMINI_API_KEY")
        if not self.anthropic_api_key:
            self.anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not self.openai_api_key:
            self.openai_api_key = os.environ.get("OPENAI_API_KEY")

    @classmethod
    def load(cls) -> "BridgeConfig":
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("port") == 8000:
                    data["port"] = 8765
                return cls(**data)
            except Exception:
                pass
        config = cls()
        config.save()
        return config

    def save(self):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(asdict(self), f, indent=2)
        except Exception as e:
            print(f"Error saving config: {e}", file=sys.stderr)


# Global singleton instance
bridge_config = BridgeConfig.load()


def set_windows_startup(enabled: bool):
    """Enable or disable auto-starting with Windows via Startup shortcut."""
    startup_dir = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    if not startup_dir.exists():
        return
    shortcut_path = startup_dir / "Antigravity Bridge.lnk"
    if enabled:
        try:
            import subprocess
            project_dir = Path(__file__).parent.parent.resolve()
            pythonw = shutil.which("pythonw") or "C:\\Python314\\pythonw.exe"
            main_py = project_dir / "main.py"
            ps_script = f"""
            $WshShell = New-Object -ComObject WScript.Shell
            $Shortcut = $WshShell.CreateShortcut('{shortcut_path}')
            $Shortcut.TargetPath = '{pythonw}'
            $Shortcut.Arguments = '"{main_py}"'
            $Shortcut.WorkingDirectory = '{project_dir}'
            $Shortcut.Description = 'Antigravity Bridge Localhost Gateway'
            $Shortcut.Save()
            """
            subprocess.run(
                ["powershell", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            )
        except Exception as e:
            print(f"Notice: Failed to set startup shortcut: {e}")
    else:
        if shortcut_path.exists():
            try:
                shortcut_path.unlink()
            except Exception:
                pass


def is_windows_startup_enabled() -> bool:
    startup_dir = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    return (startup_dir / "Antigravity Bridge.lnk").exists()

