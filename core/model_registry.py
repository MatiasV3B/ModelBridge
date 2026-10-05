"""Dynamic Model Registry for Antigravity Bridge."""

import sys
import time
import subprocess
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
        self._last_fetch_time: float = 0
        self._cache_duration: float = 300  # 5 minutes cache
        self.refresh_models()

    def fetch_models_from_cli(self) -> List[Dict[str, str]]:
        """Fetch available models from `agy models`."""
        agy_path = bridge_config.agy_binary_path
        if not agy_path:
            return [{"id": m[0], "name": m[1]} for m in FALLBACK_MODELS]

        try:
            # Run `agy models` without creating a console window
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
            print(f"Notice: Failed to fetch models from CLI ({e}), using fallback list.")

        return [{"id": m[0], "name": m[1]} for m in FALLBACK_MODELS]

    def refresh_models(self) -> List[Dict[str, str]]:
        """Force refresh the model list."""
        self._models = self.fetch_models_from_cli()
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

        # If it looks like a gemini or claude model directly
        return requested_model

    def to_openai_format(self, provider: Optional[str] = None) -> List[Dict[str, Any]]:
        """Format models for OpenAI /v1/models response, optionally filtered by provider."""
        now = int(time.time())
        result = []

        def match_provider(mid: str) -> bool:
            if not provider:
                return True
            p = provider.lower()
            m = mid.lower()
            if p == "antigravity":
                return m.startswith("gemini-") or "oss" in m or "antigravity" in m
            if p in ("claude", "cloud"):
                return m.startswith("claude-") or "sonnet" in m or "opus" in m or "haiku" in m or "fable" in m
            if p == "openai":
                return "gpt" in m or "codex" in m or "o3" in m or "davinci" in m
            return True

        # Real Antigravity models
        for m in self.get_models():
            if not match_provider(m["id"]):
                continue
            result.append({
                "id": m["id"],
                "object": "model",
                "type": "model",
                "created": now,
                "created_at": now,
                "owned_by": provider or "antigravity",
                "permission": [],
                "root": m["id"],
                "parent": None,
                "display_name": m["name"],
                "usage_limit": get_model_usage_limit(m["id"]),
                "cli_quota": quota_manager.get_model_quota(m["id"]),
            })

        # Also expose common aliases so clients don't error if checking existence
        for alias, target in MODEL_ALIASES.items():
            if not match_provider(alias) and not match_provider(target):
                continue
            result.append({
                "id": alias,
                "object": "model",
                "type": "model",
                "created": now,
                "created_at": now,
                "owned_by": f"{provider or 'antigravity'}-alias",
                "permission": [],
                "root": target,
                "parent": None,
                "display_name": f"{alias} -> {target}",
                "usage_limit": get_model_usage_limit(target),
                "cli_quota": quota_manager.get_model_quota(target),
            })

        return result


model_registry = ModelRegistry()
