"""Dynamic Model Registry for Antigravity Bridge."""

import os
import sys
import json
import time
import shutil
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional
from core.config import bridge_config
from core.quota_manager import quota_manager

FALLBACK_MODELS = [
    ("gemini-3.8-flash-medium", "Gemini 3.8 Flash (Medium)"),
    ("gemini-3.8-flash-high", "Gemini 3.8 Flash (High)"),
    ("gemini-3.8-flash-low", "Gemini 3.8 Flash (Low)"),
    ("gemini-3.7-flash-medium", "Gemini 3.7 Flash (Medium)"),
    ("gemini-3.7-flash-high", "Gemini 3.7 Flash (High)"),
    ("gemini-3.7-flash-low", "Gemini 3.7 Flash (Low)"),
    ("gemini-3.6-flash-medium", "Gemini 3.6 Flash (Medium)"),
    ("gemini-3.6-flash-high", "Gemini 3.6 Flash (High)"),
    ("gemini-3.6-flash-low", "Gemini 3.6 Flash (Low)"),
    ("gemini-3.1-pro-high", "Gemini 3.1 Pro (High)"),
    ("gemini-3.1-pro-low", "Gemini 3.1 Pro (Low)"),
    ("claude-sonnet-5-5", "Claude Sonnet 5.5 (Thinking)"),
    ("claude-opus-5-5", "Claude Opus 5.5 (Thinking)"),
    ("claude-fable-5-1", "Claude Fable 5.1 (Agentic)"),
    ("claude-haiku-4-5", "Claude Haiku 4.5 (Fast)"),
    ("claude-sonnet-4-6", "Claude Sonnet 4.6 (Thinking)"),
    ("claude-opus-4-6-thinking", "Claude Opus 4.6 (Thinking)"),
    ("gpt-oss-120b-medium", "GPT-OSS 120B (Medium)"),
]

# Aliases to map generic requests to the active Antigravity models
MODEL_ALIASES = {
    "gemini-flash": "gemini-3.8-flash-medium",
    "gemini-pro": "gemini-3.1-pro-high",
    "gemini-3.8-flash": "gemini-3.8-flash-medium",
    "gemini-3.7-flash": "gemini-3.7-flash-medium",
    "gemini-3.6-flash": "gemini-3.6-flash-medium",
    "gemini-3.1-pro": "gemini-3.1-pro-high",
    "claude-sonnet": "claude-sonnet-5-5",
    "claude-sonnet-5-5": "claude-sonnet-5-5",
    "claude-sonnet-5.5": "claude-sonnet-5-5",
    "claude-5-5-sonnet": "claude-sonnet-5-5",
    "claude-5.5-sonnet": "claude-sonnet-5-5",
    "sonnet-5.5": "claude-sonnet-5-5",
    "claude-opus": "claude-opus-5-5",
    "claude-opus-5-5": "claude-opus-5-5",
    "claude-opus-5.5": "claude-opus-5-5",
    "claude-5-5-opus": "claude-opus-5-5",
    "claude-5.5-opus": "claude-opus-5-5",
    "opus-5.5": "claude-opus-5-5",
    "claude-fable": "claude-fable-5-1",
    "claude-fable-5-1": "claude-fable-5-1",
    "claude-fable-5.1": "claude-fable-5-1",
    "claude-5-1-fable": "claude-fable-5-1",
    "claude-5.1-fable": "claude-fable-5-1",
    "fable-5.1": "claude-fable-5-1",
    "claude-haiku": "claude-haiku-4-5",
    "claude-haiku-4-5": "claude-haiku-4-5",
    "claude-haiku-4.5": "claude-haiku-4-5",
    "claude-4-5-haiku": "claude-haiku-4-5",
    "claude-4.5-haiku": "claude-haiku-4-5",
    "haiku-4.5": "claude-haiku-4-5",
    "claude-opus-4-7": "claude-opus-4-6-thinking",
    "claude-3-7-sonnet": "claude-sonnet-4-6",
    "claude-3-7-sonnet-20250219": "claude-sonnet-4-6",
    "claude-3-5-sonnet": "claude-sonnet-4-6",
    "claude-3-5-sonnet-20241022": "claude-sonnet-4-6",
    "claude-3-opus": "claude-opus-4-6-thinking",
    "claude-3-opus-20240229": "claude-opus-4-6-thinking",
    "claude-3-5-haiku": "claude-haiku-4-5",
    "claude-3-5-haiku-20241022": "claude-haiku-4-5",
    "sonnet": "claude-sonnet-4-6",
    "opus": "claude-opus-4-6-thinking",
    "haiku": "claude-haiku-4-5",
    "gpt-oss": "gpt-oss-120b-medium",
    "gpt-oss-120b": "gpt-oss-120b-medium",
    "gpt-ss": "gpt-oss-120b-medium",
    "gpt-ss-120b": "gpt-oss-120b-medium",
}


MODEL_USAGE_LIMITS = {
    "gemini": {
        "type": "unlimited",
        "label": "Cuota Alta",
        "window_hours": None,
        "limit": None,
        "desc": "Cuota estándar de Gemini sin restricciones horarias",
    },
    "claude-sonnet-5-5": {
        "type": "window",
        "label": "45 msgs / 5h",
        "window_hours": 5,
        "limit": 45,
        "desc": "Ventana de 45 mensajes cada 5 horas para Sonnet 5.5",
    },
    "claude-opus-5-5": {
        "type": "window",
        "label": "20 msgs / 5h",
        "window_hours": 5,
        "limit": 20,
        "desc": "Ventana de 20 mensajes cada 5 horas para Opus 5.5",
    },
    "claude-fable-5-1": {
        "type": "window",
        "label": "60 msgs / 5h",
        "window_hours": 5,
        "limit": 60,
        "desc": "Ventana de 60 mensajes cada 5 horas para Fable 5.1",
    },
    "claude-haiku-4-5": {
        "type": "window",
        "label": "100 msgs / 5h",
        "window_hours": 5,
        "limit": 100,
        "desc": "Ventana de 100 mensajes cada 5 horas para Haiku 4.5",
    },
    "claude-sonnet-4-6": {
        "type": "window",
        "label": "45 msgs / 5h",
        "window_hours": 5,
        "limit": 45,
        "desc": "Ventana de 45 mensajes cada 5 horas",
    },
    "claude-opus-4-6-thinking": {
        "type": "window",
        "label": "20 msgs / 5h",
        "window_hours": 5,
        "limit": 20,
        "desc": "Ventana estricta de 20 mensajes cada 5 horas",
    },
    "gpt-oss-120b-medium": {
        "type": "window",
        "label": "80 msgs / 3h",
        "window_hours": 3,
        "limit": 80,
        "desc": "Ventana de 80 mensajes cada 3 horas",
    },
}


def get_model_usage_limit(model_id: str) -> Dict[str, Any]:
    mid = model_id.lower()
    if "claude-sonnet-5" in mid or "sonnet-5" in mid:
        return MODEL_USAGE_LIMITS["claude-sonnet-5-5"]
    if "claude-opus-5" in mid or "opus-5" in mid:
        return MODEL_USAGE_LIMITS["claude-opus-5-5"]
    if "claude-fable" in mid or "fable" in mid:
        return MODEL_USAGE_LIMITS["claude-fable-5-1"]
    if "claude-haiku" in mid or "haiku" in mid:
        return MODEL_USAGE_LIMITS["claude-haiku-4-5"]
    if "claude-sonnet" in mid:
        return MODEL_USAGE_LIMITS["claude-sonnet-4-6"]
    if "claude-opus" in mid:
        return MODEL_USAGE_LIMITS["claude-opus-4-6-thinking"]
    if "gpt" in mid or "oss" in mid:
        return MODEL_USAGE_LIMITS["gpt-oss-120b-medium"]
    return MODEL_USAGE_LIMITS["gemini"]


class ModelRegistry:
    def __init__(self):
        self._models: List[Dict[str, str]] = []
        self._provider_models: Dict[str, List[Dict[str, str]]] = {
            "antigravity": [],
            "claude": [],
            "openai": [],
        }
        self._last_fetch_time: float = 0
        self._cache_duration: float = 300  # 5 minutes cache
        self.refresh_models()

    def fetch_antigravity_models(self) -> List[Dict[str, str]]:
        """Fetch available models from `agy models`."""
        agy_path = bridge_config.agy_binary_path
        if not agy_path or not (shutil.which(agy_path) or Path(agy_path).exists()):
            return [
                {"id": m[0], "name": m[1]}
                for m in FALLBACK_MODELS
                if m[0].startswith("gemini-") or "oss" in m[0]
            ]

        try:
            extra_kwargs = {}
            if sys.platform == "win32":
                extra_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

            proc = subprocess.run(
                [agy_path, "models"],
                capture_output=True,
                text=True,
                timeout=8,
                encoding="utf-8",
                errors="replace",
                **extra_kwargs,
            )
            if proc.returncode == 0:
                lines = proc.stdout.strip().splitlines()
                models = []
                for line in lines:
                    line = line.strip()
                    if not line or line.startswith("Fetching"):
                        continue
                    parts = line.split("\t")
                    if len(parts) >= 2:
                        models.append({"id": parts[0].strip(), "name": parts[1].strip()})
                    elif len(parts) == 1 and parts[0].strip():
                        name = parts[0].strip()
                        models.append({"id": name, "name": name})
                if models:
                    return models
        except Exception as e:
            print(f"Notice: Failed to fetch Antigravity models from CLI ({e}).")

        return [
            {"id": m[0], "name": m[1]}
            for m in FALLBACK_MODELS
            if m[0].startswith("gemini-") or "oss" in m[0]
        ]

    def fetch_codex_models(self) -> List[Dict[str, str]]:
        """Fetch available models from Codex CLI config & cache."""
        models: List[Dict[str, str]] = []
        seen = set()

        # 1. Inspect ~/.codex/models_cache.json
        codex_home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
        cache_path = codex_home / "models_cache.json"
        if cache_path.exists():
            try:
                data = json.loads(cache_path.read_text(encoding="utf-8"))
                for item in data.get("models", []):
                    slug = (item.get("slug") or "").strip()
                    dname = (item.get("display_name") or slug).strip()
                    if slug and slug not in seen:
                        seen.add(slug)
                        models.append({"id": slug, "name": dname})
            except Exception as e:
                print(f"Notice: Failed reading Codex models_cache.json ({e}).")

        # 2. Inspect active model configured in ~/.codex/config.toml
        config_path = codex_home / "config.toml"
        if config_path.exists():
            try:
                import re
                txt = config_path.read_text(encoding="utf-8")
                m = re.search(r'^\s*model\s*=\s*"([^"]+)"', txt, re.MULTILINE)
                if m:
                    cfg_model = m.group(1).strip()
                    if cfg_model and cfg_model not in seen:
                        seen.add(cfg_model)
                        models.insert(0, {"id": cfg_model, "name": cfg_model})
            except Exception:
                pass

        if not models:
            models = [
                {"id": "gpt-6-luna", "name": "GPT-6 Luna (Codex)"},
                {"id": "gpt-6-sol", "name": "GPT-6 Sol (Codex)"},
                {"id": "gpt-5.6-terra", "name": "GPT-5.6 Terra (Codex)"},
                {"id": "gpt-5.6-luna", "name": "GPT-5.6 Luna (Codex)"},
                {"id": "gpt-5.5", "name": "GPT-5.5 (Codex)"},
            ]

        return models

    def fetch_claude_models(self) -> List[Dict[str, str]]:
        """Fetch available models from Claude Code CLI."""
        claude_models: List[Dict[str, str]] = []
        seen = set()

        # 1. Check ~/.claude/settings.json
        settings_path = Path.home() / ".claude" / "settings.json"
        if settings_path.exists():
            try:
                data = json.loads(settings_path.read_text(encoding="utf-8"))
                cfg_model = (data.get("model") or "").strip()
                if cfg_model:
                    clean_id = cfg_model.split("[")[0].strip()
                    full_id = f"claude-{clean_id}" if not clean_id.startswith("claude-") else clean_id
                    if full_id not in seen:
                        seen.add(full_id)
                        claude_models.append({"id": full_id, "name": f"Claude {clean_id.title()} (Active)"})
            except Exception:
                pass

        # 2. Extract official models supported by installed Claude CLI binary
        claude_path = getattr(bridge_config, "claude_binary_path", "") or shutil.which("claude")
        if claude_path and os.path.exists(claude_path):
            try:
                raw_bytes = Path(claude_path).read_bytes()
                import re
                found = set(re.findall(rb'claude-(?:sonnet|opus|haiku)-[0-9]+(?:-[0-9]+)?', raw_bytes))
                for m_b in sorted(found, reverse=True):
                    m_str = m_b.decode('ascii')
                    if m_str not in seen:
                        seen.add(m_str)
                        parts = m_str.replace("claude-", "").split("-")
                        title = f"Claude {parts[0].title()} {'.'.join(parts[1:])}"
                        claude_models.append({"id": m_str, "name": title})
            except Exception:
                pass

        if not claude_models:
            claude_models = [
                {"id": "claude-sonnet-5-5", "name": "Claude Sonnet 5.5"},
                {"id": "claude-opus-5-5", "name": "Claude Opus 5.5"},
                {"id": "claude-fable-5-1", "name": "Claude Fable 5.1"},
                {"id": "claude-haiku-4-5", "name": "Claude Haiku 4.5"},
                {"id": "claude-sonnet-4-6", "name": "Claude Sonnet 4.6"},
                {"id": "claude-opus-4-7", "name": "Claude Opus 4.7"},
            ]

        return claude_models

    def refresh_models(self) -> List[Dict[str, str]]:
        """Force refresh the model list across all CLIs."""
        agy_list = self.fetch_antigravity_models()
        codex_list = self.fetch_codex_models()
        claude_list = self.fetch_claude_models()

        self._provider_models = {
            "antigravity": agy_list,
            "openai": codex_list,
            "claude": claude_list,
        }

        # Combined registry models list
        all_models = []
        all_ids = set()
        for group in (agy_list, codex_list, claude_list):
            for m in group:
                if m["id"] not in all_ids:
                    all_ids.add(m["id"])
                    all_models.append(m)

        self._models = all_models
        self._last_fetch_time = time.time()
        return self._models

    def get_models(self) -> List[Dict[str, str]]:
        """Get models, refreshing if cache expired."""
        if time.time() - self._last_fetch_time > self._cache_duration or not self._models:
            self.refresh_models()
        return self._models

    def resolve_model(self, requested_model: Optional[str]) -> str:
        """Resolve a requested model ID, mapping aliases or defaulting to active model."""
        if not requested_model:
            return bridge_config.default_model

        requested_model = requested_model.strip()

        # Check aliases
        if requested_model in MODEL_ALIASES:
            return MODEL_ALIASES[requested_model]

        # Check exact match in registered models
        for m in self.get_models():
            if m["id"].lower() == requested_model.lower():
                return m["id"]

        return requested_model

    def to_openai_format(self, provider: Optional[str] = None) -> List[Dict[str, Any]]:
        """Format models for OpenAI /v1/models response, optionally filtered by provider."""
        now = int(time.time())
        result = []
        p_filter = provider.lower() if provider else None
        if p_filter == "cloud":
            p_filter = "claude"

        # Emit models from each provider group
        for prov_key, m_list in self._provider_models.items():
            if p_filter and p_filter != prov_key:
                continue

            for m in m_list:
                result.append({
                    "id": m["id"],
                    "object": "model",
                    "type": "model",
                    "created": now,
                    "created_at": now,
                    "owned_by": prov_key,
                    "permission": [],
                    "root": m["id"],
                    "parent": None,
                    "display_name": m["name"],
                    "usage_limit": get_model_usage_limit(m["id"]),
                    "cli_quota": quota_manager.get_model_quota(m["id"]),
                })

        # Also expose common aliases filtered appropriately
        for alias, target in MODEL_ALIASES.items():
            alias_prov = "claude" if ("claude" in alias or "sonnet" in alias or "opus" in alias or "haiku" in alias or "fable" in alias) else ("openai" if ("gpt" in alias or "codex" in alias) else "antigravity")
            if p_filter and p_filter != alias_prov:
                continue
            result.append({
                "id": alias,
                "object": "model",
                "type": "model",
                "created": now,
                "created_at": now,
                "owned_by": f"{alias_prov}-alias",
                "permission": [],
                "root": target,
                "parent": None,
                "display_name": f"{alias} -> {target}",
                "usage_limit": get_model_usage_limit(target),
                "cli_quota": quota_manager.get_model_quota(target),
            })

        return result


model_registry = ModelRegistry()
