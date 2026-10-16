"""What the Bridge lets a model do on this computer.

Two layers:

* Permission mode (changeable from the Autono Settings tab): how much the Antigravity CLI may do without asking.
    ask  - nothing is approved on its own (default)
    auto - every tool request is approved automatically
    none - same as auto here; the extra freedom of this mode (no confirmation dialogs) lives in the extension

* Hard limits (the same in every mode, and not changeable over HTTP, so a web page or an injected prompt cannot
  lift them): the CLI always runs with its sandbox on, the computer cannot be shut down or hibernated, and
  code from /api/code/execute runs only when the person turned it on locally (see code_execution_policy).
"""

import os
from typing import List, Optional
from urllib.parse import urlparse

MODES = ("ask", "auto", "none")
DEFAULT_MODE = "ask"

# Values of BridgeConfig.code_execution. "off" is the default; "isolated" must be set in config.json (or with the
# BRIDGE_CODE_EXECUTION environment variable) on this computer.
CODE_OFF = "off"
CODE_ISOLATED = "isolated"


def normalize_mode(value: Optional[str]) -> str:
    """An unknown or missing value falls back to the safest mode."""
    v = (value or "").strip().lower()
    return v if v in MODES else DEFAULT_MODE


def agy_permission_flags(mode: Optional[str]) -> List[str]:
    """Flags for the Antigravity CLI. --sandbox is always there: it is a hard limit, not part of the mode."""
    flags = ["--sandbox"]
    if normalize_mode(mode) in ("auto", "none"):
        flags.append("--dangerously-skip-permissions")
    return flags


def code_execution_policy(config_value: Optional[str] = None) -> str:
    """'isolated' only when explicitly set by the environment variable or the local config; anything else is off."""
    raw = os.environ.get("BRIDGE_CODE_EXECUTION") or config_value or CODE_OFF
    return CODE_ISOLATED if raw.strip().lower() == CODE_ISOLATED else CODE_OFF


def is_trusted_origin(origin: Optional[str]) -> bool:
    """Who may change the permission mode over HTTP.

    A web page always sends its own http(s) Origin on a cross-site request, so it is refused. A browser
    extension (chrome-extension://, moz-extension://) or a local tool that sends no Origin is allowed.
    """
    if not origin:
        return True
    scheme = urlparse(origin).scheme.lower()
    return scheme in ("chrome-extension", "moz-extension")


def hard_limits(code_policy: str) -> dict:
    """What the Bridge reports to the extension so Settings can show it."""
    return {
        "cli_sandbox": True,
        "shutdown": False,
        "hibernate": False,
        "code_execution": code_policy,
    }
