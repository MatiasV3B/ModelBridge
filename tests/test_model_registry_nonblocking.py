"""The model list must never make a chat request wait: the CLIs that build it take seconds to start."""

import threading
import time

from core import model_registry as mr


def _slow_registry(monkeypatch, delay=0.6):
    calls = {"n": 0}
    lock = threading.Lock()

    def slow(self):
        with lock:
            calls["n"] += 1
        time.sleep(delay)
        return [{"id": "claude-sonnet-5-5", "name": "Claude Sonnet 5.5"}]

    monkeypatch.setattr(mr.ModelRegistry, "fetch_antigravity_models", lambda self: [{"id": "gemini-3.8-flash-medium", "name": "G"}])
    monkeypatch.setattr(mr.ModelRegistry, "fetch_codex_models", lambda self: [])
    monkeypatch.setattr(mr.ModelRegistry, "fetch_claude_models", slow)
    return mr.ModelRegistry(), calls


def test_stale_cache_is_served_immediately_and_refreshed_in_background(monkeypatch):
    registry, calls = _slow_registry(monkeypatch)
    startup_calls = calls["n"]
    registry._last_fetch_time = 0  # cache expired

    started = time.time()
    models = registry.get_models()
    resolved = registry.resolve_model("claude-sonnet-5-5")
    elapsed = time.time() - started

    assert models and resolved == "claude-sonnet-5-5"
    assert elapsed < 0.3, f"a chat request waited {elapsed:.2f}s for the model list"

    # a burst of requests starts a single refresh
    for _ in range(5):
        registry.get_models()
    deadline = time.time() + 5
    while registry._refreshing and time.time() < deadline:
        time.sleep(0.05)
    assert calls["n"] == startup_calls + 1
    assert time.time() - registry._last_fetch_time < 5


def test_the_three_clis_are_asked_in_parallel(monkeypatch):
    started = time.time()
    _slow_registry(monkeypatch, delay=0.5)  # only the Claude one is slow here, but the startup must not add up
    assert time.time() - started < 1.5
