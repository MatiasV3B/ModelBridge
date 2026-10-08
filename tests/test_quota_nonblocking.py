"""The quota lookup runs inside /v1/models; it must not wait for a slow or broken Antigravity CLI."""

import subprocess
import threading
import time

from core.quota_manager import QuotaManager


def test_slow_cli_does_not_block_model_listing(monkeypatch):
    calls = {"n": 0}
    lock = threading.Lock()

    def slow_run(*args, **kwargs):
        with lock:
            calls["n"] += 1
        time.sleep(1.0)
        raise subprocess.TimeoutExpired(cmd="agy", timeout=10)

    monkeypatch.setattr("core.quota_manager.subprocess.run", slow_run)
    manager = QuotaManager()

    started = time.time()
    for i in range(25):  # /v1/models asks once per model
        quota = manager.get_model_quota(f"model-{i}")
    elapsed = time.time() - started

    assert quota["five_hour_remaining"] == 100  # the default until a real answer arrives
    assert elapsed < 0.3, f"listing the models waited {elapsed:.2f}s for the CLI"

    time.sleep(1.5)  # the single background attempt finishes and fails
    assert calls["n"] == 1, "the CLI must be asked once, not once per model"
    manager.get_model_quota("model-x")
    time.sleep(0.2)
    assert calls["n"] == 1, "a failed attempt must not be repeated immediately"
