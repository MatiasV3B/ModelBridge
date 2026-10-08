"""Dynamic Model Registry for Antigravity Bridge."""

import os
import sys
import json
import time
import shutil
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
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


def _aggregate_model_variants(raw_models: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """
    Groups models that differ only by thinking effort (-high, -medium, -low, -thinking)
    into a single canonical model representation with a 'thinking' list and 'variants' dict.
    e.g. gemini-3.8-flash-high, gemini-3.8-flash-medium, gemini-3.8-flash-low
         -> id: 'gemini-3.8-flash', name: 'Gemini 3.8 Flash', thinking: ['low', 'medium', 'high']
    """
    import re
    grouped: Dict[str, Dict[str, Any]] = {}
    ordered_ids: List[str] = []

    for m in raw_models:
        raw_id = m.get("id", "").strip()
        raw_name = m.get("name", "").strip()
        if not raw_id:
            continue

        effort = None
        base_id = raw_id
        if raw_id.endswith("-high"):
            base_id = raw_id[:-5]
            effort = "high"
        elif raw_id.endswith("-medium"):
            base_id = raw_id[:-7]
            effort = "medium"
        elif raw_id.endswith("-low"):
            base_id = raw_id[:-4]
            effort = "low"
        elif raw_id.endswith("-thinking"):
            base_id = raw_id[:-9]
            effort = "thinking"

        # Clean display name: remove trailing "(High)", "(Medium)", "(Low)", "(Thinking)"
        clean_name = re.sub(r'\s*\((High|Medium|Low|Thinking)\)\s*$', '', raw_name, flags=re.IGNORECASE).strip()
        if not clean_name:
            clean_name = base_id

        if base_id not in grouped:
            grouped[base_id] = {
                "id": base_id,
                "name": clean_name,
                "thinking": [],
                "default_thinking": "medium",
                "variants": {},
                "default_variant": raw_id,
            }
            ordered_ids.append(base_id)

        entry = grouped[base_id]
        if effort:
            if effort not in entry["thinking"]:
                entry["thinking"].append(effort)
            entry["variants"][effort] = raw_id
            if effort == "medium" or not entry.get("default_variant"):
                entry["default_variant"] = raw_id
        else:
            entry["variants"]["default"] = raw_id

    result = []
    for bid in ordered_ids:
        item = grouped[bid]
        if not item["thinking"]:
            item["thinking"] = ["low", "medium", "high"]
        order = ["low", "medium", "high", "thinking", "x-high", "max"]
        item["thinking"].sort(key=lambda x: order.index(x) if x in order else 99)
        if "medium" in item["thinking"]:
            item["default_thinking"] = "medium"
        elif "high" in item["thinking"]:
            item["default_thinking"] = "high"
        elif item["thinking"]:
            item["default_thinking"] = item["thinking"][0]
        result.append(item)

    return result


class ModelRegistry:
    def __init__(self):
        self._models: List[Dict[str, Any]] = []
        self._provider_models: Dict[str, List[Dict[str, Any]]] = {
            "antigravity": [],
            "claude": [],
            "openai": [],
        }
        self._last_fetch_time: float = 0
        self._cache_duration: float = 300  # 5 minutes cache
        self._refreshing = False
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

    def refresh_models(self) -> List[Dict[str, Any]]:
        """Force refresh the model list across all CLIs and aggregate thinking variants."""
        # The three CLIs are slow to start (each can take several seconds): ask them at the same time
        with ThreadPoolExecutor(max_workers=3) as pool:
            f_agy = pool.submit(self.fetch_antigravity_models)
            f_codex = pool.submit(self.fetch_codex_models)
            f_claude = pool.submit(self.fetch_claude_models)
            agy_raw, codex_raw, claude_raw = f_agy.result(), f_codex.result(), f_claude.result()
        agy_list = _aggregate_model_variants(agy_raw)
        codex_list = _aggregate_model_variants(codex_raw)
        claude_list = _aggregate_model_variants(claude_raw)

        antigravity_models = []
        claude_models = list(claude_list)
        openai_models = list(codex_list)

        for m in agy_list:
            mid = m["id"].lower()
            if "claude" in mid or "sonnet" in mid or "opus" in mid:
                if not any(x["id"] == m["id"] for x in claude_models):
                    claude_models.append(m)
                antigravity_models.append(m)
            elif "gpt" in mid or "oss" in mid:
                if not any(x["id"] == m["id"] for x in openai_models):
                    openai_models.append(m)
                antigravity_models.append(m)
            else:
                antigravity_models.append(m)

        self._provider_models = {
            "antigravity": antigravity_models,
            "openai": openai_models,
            "claude": claude_models,
        }

        all_models = []
        all_ids = set()
        for group in (antigravity_models, openai_models, claude_models):
            for m in group:
                if m["id"] not in all_ids:
                    all_ids.add(m["id"])
                    all_models.append(m)

        self._models = all_models
        self._last_fetch_time = time.time()
        return self._models

    def _refresh_in_background(self) -> None:
        """Refresh without making anyone wait (one refresh at a time)."""
        if self._refreshing:
            return
        self._refreshing = True

        def work() -> None:
            try:
                self.refresh_models()
            except Exception:
                pass
            finally:
                self._refreshing = False

        threading.Thread(target=work, daemon=True, name="model-refresh").start()

    def get_models(self) -> List[Dict[str, Any]]:
        """Get the cached models. An expired cache is refreshed in the background.

        This is called for every chat request, from the server's event loop: running the CLIs here
        (agy / codex / claude models, several seconds each) froze the whole server every few minutes.
        """
        if not self._models:
            self.refresh_models()  # only the very first call, at startup
        elif time.time() - self._last_fetch_time > self._cache_duration:
            self._refresh_in_background()
        return self._models

    def resolve_model(self, requested_model: Optional[str], effort: Optional[str] = None) -> str:
        """Resolve a requested model ID, mapping aliases and selecting proper effort variant if applicable."""
        if not requested_model:
            return bridge_config.default_model

        req = requested_model.strip()
        req_lower = req.lower()

        # Check aliases
        if req_lower in MODEL_ALIASES:
            req = MODEL_ALIASES[req_lower]
            req_lower = req.lower()

        eff = (effort or "").lower().strip()

        # Check registered models for variant resolution
        for m in self.get_models():
            if m["id"].lower() == req_lower:
                variants = m.get("variants", {})
                if eff and eff in variants:
                    return variants[eff]
                if "default_variant" in m:
                    return m["default_variant"]
                return m["id"]
            variants = m.get("variants", {})
            for v_eff, v_id in variants.items():
                if v_id.lower() == req_lower:
                    return v_id

        return req

    def to_openai_format(self, provider: Optional[str] = None) -> List[Dict[str, Any]]:
        """Format models for OpenAI /v1/models response, strictly deduplicated without exposing raw aliases."""
        now = int(time.time())
        result = []
        p_filter = provider.lower() if provider else None
        if p_filter == "cloud":
            p_filter = "claude"

        seen_ids = set()

        for prov_key, m_list in self._provider_models.items():
            if p_filter and p_filter != prov_key:
                continue

            for m in m_list:
                m_id = m["id"]
                if m_id in seen_ids:
                    continue
                seen_ids.add(m_id)

                result.append({
                    "id": m_id,
                    "object": "model",
                    "type": "model",
                    "created": now,
                    "created_at": now,
                    "owned_by": prov_key,
                    "permission": [],
                    "root": m_id,
                    "parent": None,
                    "display_name": m["name"],
                    "thinking": m.get("thinking", ["low", "medium", "high"]),
                    "default_thinking": m.get("default_thinking", "medium"),
                    "variants": m.get("variants", {}),
                    "usage_limit": get_model_usage_limit(m_id),
                    "cli_quota": quota_manager.get_model_quota(m_id),
                })

        return result


model_registry = ModelRegistry()
