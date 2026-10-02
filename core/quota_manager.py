"""Live Quota Manager using Antigravity CLI (agy --print /usage)."""

import sys
import time
import subprocess
from typing import Dict, Any, Optional
from core.config import bridge_config


class QuotaManager:
    """Queries and caches live model quota directly from Antigravity CLI."""

    def __init__(self):
        self._cached_quota: Optional[Dict[str, Any]] = None
        self._last_fetch_time: float = 0
        self._cache_ttl: float = 20.0  # 20 seconds cache to be snappy

    def fetch_quota(self, force: bool = False) -> Dict[str, Any]:
        """
        Runs `agy.exe --print /usage` and parses:
        Gemini Models	Weekly Limit Remaining	82%	2026-09-23T13:46:14Z
        Gemini Models	Five Hour Limit Remaining	35%	2026-09-20T03:23:55Z
        Claude and GPT models	Weekly Limit Remaining	99%	2026-09-27T00:25:45Z
        Claude and GPT models	Five Hour Limit Remaining	97%	2026-09-20T05:25:45Z
        """
        now = time.time()
        if not force and self._cached_quota and (now - self._last_fetch_time < self._cache_ttl):
            return self._cached_quota

        agy_path = bridge_config.agy_binary_path or "agy"
        extra_kwargs = {}
        if sys.platform == "win32":
            extra_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

        quota_data = {
            "gemini": {
                "name": "Gemini Models",
                "five_hour_remaining": 100,
                "five_hour_reset": None,
                "weekly_remaining": 100,
                "weekly_reset": None,
            },
            "claude_gpt": {
                "name": "Claude and GPT models",
                "five_hour_remaining": 100,
                "five_hour_reset": None,
                "weekly_remaining": 100,
                "weekly_reset": None,
            },
            "raw_output": "",
            "last_updated": int(now),
        }

        try:
            proc = subprocess.run(
                [agy_path, "--print", "/usage"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
                **extra_kwargs,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                quota_data["raw_output"] = proc.stdout.strip()
                for line in proc.stdout.strip().splitlines():
                    parts = line.split("\t")
                    if len(parts) >= 4:
                        group = parts[0].strip()
                        metric = parts[1].strip()
                        pct_str = parts[2].strip()
                        reset_ts = parts[3].strip()

                        clean_pct = pct_str.replace("%", "").strip()
                        pct = int(clean_pct) if clean_pct.isdigit() else 100

                        target_group = "gemini" if "gemini" in group.lower() else "claude_gpt"

                        if "five hour" in metric.lower():
                            quota_data[target_group]["five_hour_remaining"] = pct
                            quota_data[target_group]["five_hour_reset"] = reset_ts
                        elif "weekly" in metric.lower():
                            quota_data[target_group]["weekly_remaining"] = pct
                            quota_data[target_group]["weekly_reset"] = reset_ts
        except Exception as e:
            print(f"Notice: Failed to fetch quota from agy ({e})", file=sys.stderr)
            # If we had a previous cache, preserve it rather than returning defaults
            if self._cached_quota:
                return self._cached_quota

        self._cached_quota = quota_data
        self._last_fetch_time = now
        return quota_data

    def get_model_quota(self, model_id: str) -> Dict[str, Any]:
        """Get the live quota group for a specific model."""
        quota = self.fetch_quota()
        mid = model_id.lower()
        if "claude" in mid or "gpt" in mid or "oss" in mid:
            group_key = "claude_gpt"
        else:
            group_key = "gemini"

        gdata = quota[group_key]
        return {
            "group": group_key,
            "group_name": gdata["name"],
            "five_hour_remaining": gdata["five_hour_remaining"],
            "five_hour_reset": gdata["five_hour_reset"],
            "weekly_remaining": gdata["weekly_remaining"],
            "weekly_reset": gdata["weekly_reset"],
            "last_updated": quota["last_updated"],
        }


quota_manager = QuotaManager()
