"""Live Quota Manager using Antigravity CLI (agy --print /usage)."""

import sys
import time
import threading
import subprocess
from typing import Dict, Any, Optional
from core.config import bridge_config


class QuotaManager:
    """Queries and caches live model quota directly from Antigravity CLI."""

    def __init__(self):
        self._cached_quota: Optional[Dict[str, Any]] = None
        self._last_fetch_time: float = 0
        self._cache_ttl: float = 120.0  # 2 minutes cache
        self._fetching: bool = False
        self._last_attempt: float = 0
        self._lock = threading.Lock()

    def _default_quota(self) -> Dict[str, Any]:
        return {
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
            "last_updated": int(time.time()),
        }

    def _start_background_fetch(self) -> None:
        """Ask the Antigravity CLI for the quota on a worker thread (one at a time)."""
        with self._lock:
            if self._fetching:
                return
            self._fetching = True
        threading.Thread(target=self._background_fetch, daemon=True, name="quota-fetch").start()

    def _background_fetch(self):
        """Runs `agy --print /usage` (can take 10 s). Only ever called from a worker thread, never from a request."""
        try:
            agy_path = bridge_config.agy_binary_path or "agy"
            extra_kwargs = {}
            if sys.platform == "win32":
                extra_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

            proc = subprocess.run(
                [agy_path, "--print", "/usage"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
                **extra_kwargs,
            )
            now = time.time()
            if proc.returncode == 0 and proc.stdout.strip():
                quota_data = self._default_quota()
                quota_data["raw_output"] = proc.stdout.strip()
                quota_data["last_updated"] = int(now)
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
                self._cached_quota = quota_data
                self._last_fetch_time = now
        except Exception as e:
            print(f"Notice: Background quota fetch notice ({e})", file=sys.stderr)
        finally:
            self._last_attempt = time.time()  # also after a failure, so a broken CLI is not asked again at once
            self._fetching = False

    def _due(self, now: float) -> bool:
        return now - max(self._last_fetch_time, self._last_attempt) >= self._cache_ttl

    def fetch_quota(self, force: bool = False) -> Dict[str, Any]:
        """Return the cached quota at once; a stale or missing cache is refreshed in the background.

        This runs inside request handlers. It used to run the CLI inline when nothing was cached, and with
        the CLI slow or failing that froze the whole server (every /v1/models call ran it once per model).
        """
        now = time.time()
        if force or self._due(now):
            self._start_background_fetch()
        return self._cached_quota or self._default_quota()

    def get_model_quota(self, model_id: str) -> Dict[str, Any]:
        """Get the live quota group for a specific model without blocking."""
        now = time.time()
        quota = self.fetch_quota(force=False)

        mid = model_id.lower()
        if "claude" in mid or "gpt" in mid or "oss" in mid:
            group_key = "claude_gpt"
        else:
            group_key = "gemini"

        gdata = quota.get(group_key, self._default_quota()[group_key])
        return {
            "group": group_key,
            "group_name": gdata.get("name", group_key),
            "five_hour_remaining": gdata.get("five_hour_remaining", 100),
            "five_hour_reset": gdata.get("five_hour_reset"),
            "weekly_remaining": gdata.get("weekly_remaining", 100),
            "weekly_reset": gdata.get("weekly_reset"),
            "last_updated": quota.get("last_updated", int(now)),
        }


quota_manager = QuotaManager()

