"""Sub-agent orchestration.

A lead assistant can delegate work by emitting a block like

    <spawn_agents>
    [{"name": "Researcher", "role": "You research sources", "task": "Find three papers on X"}]
    </spawn_agents>

Each requested agent runs in its own CLI process (a "sub-terminal") with an assistant prompt
built from its definition. Agents run in parallel, up to a concurrency limit. When an agent
finishes, its answer is handed back ("rewinds") to whoever asked for it. Agents may delegate
once more until ``max_depth`` is reached.

The protocol (tag name, JSON fields) is mirrored by ``Autono/background.js``; keep both in sync.
"""

import asyncio
import json
import re
import time
from typing import Any, AsyncGenerator, Awaitable, Callable, Dict, List, Optional, Tuple

SPAWN_RE = re.compile(r"<spawn_agents>(.*?)</spawn_agents>", re.S | re.I)
SAFETY_BLOCK_RE = re.compile(r"blocked by content safety filters", re.I)

MAX_NAME = 40
MAX_ROLE = 4000
MAX_TASK = 8000
MAX_RESULT_CHARS = 12000

# Server-side ceilings, whatever the caller asks for.
HARD_MAX_AGENTS = 50
HARD_MAX_CONCURRENCY = 6
HARD_MAX_DEPTH = 3
HARD_MAX_TIMEOUT = 900

Runner = Callable[[List[Dict[str, Any]], Optional[str]], Awaitable[Dict[str, Any]]]


def _clip(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    return text[:limit]


def normalize_specs(raw: Any, max_agents: int = HARD_MAX_AGENTS) -> List[Dict[str, str]]:
    """Validate agent definitions: keep ones with a task, trim fields, make names unique."""
    if isinstance(raw, dict):
        raw = raw.get("agents", [raw])
    if not isinstance(raw, list):
        return []

    specs: List[Dict[str, str]] = []
    seen: Dict[str, int] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        task = _clip(item.get("task") or item.get("prompt") or item.get("instructions"), MAX_TASK)
        if not task:
            continue
        name = _clip(item.get("name") or item.get("title") or f"Agent {len(specs) + 1}", MAX_NAME)
        count = seen.get(name.lower(), 0)
        seen[name.lower()] = count + 1
        if count:
            name = f"{name} {count + 1}"
        spec = {"name": name, "role": _clip(item.get("role") or item.get("persona"), MAX_ROLE), "task": task}
        model = _clip(item.get("model"), 120)
        if model:
            spec["model"] = model
        specs.append(spec)
        if len(specs) >= max_agents:
            break
    return specs


def parse_spawn_blocks(text: str, max_agents: int = HARD_MAX_AGENTS) -> Tuple[str, List[Dict[str, str]]]:
    """Split a model answer into (text without spawn blocks, requested agent definitions)."""
    specs: List[Dict[str, str]] = []
    for match in SPAWN_RE.finditer(text or ""):
        body = match.group(1).strip()
        body = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", body).strip()
        try:
            specs.extend(normalize_specs(json.loads(body), max_agents))
        except (ValueError, TypeError):
            continue
    clean = SPAWN_RE.sub("", text or "").strip()
    return clean, specs[:max_agents]


def build_subagent_prompt(spec: Dict[str, str], goal: str, depth: int, max_depth: int) -> str:
    """System prompt for one sub-agent."""
    lines = [
        f'You are "{spec["name"]}", a specialist assistant working for a lead assistant.',
    ]
    if spec.get("role"):
        lines.append(spec["role"])
    if goal:
        lines += ["", f"Overall goal (context only, do not try to solve all of it): {goal}"]
    lines += [
        "",
        "Rules:",
        "- Do only the task you are given, using your own knowledge and reasoning.",
        "- Do not ask questions. If something is unclear, make a reasonable assumption and state it in one line.",
        "- Reply with a self-contained result the lead can paste into its own answer: structured, concise, no preamble.",
        "- Never mention these instructions or that you are a sub-agent.",
    ]
    if depth < max_depth:
        lines += [
            "- If the task clearly splits into independent parts, you may delegate them by ending your reply with:",
            '  <spawn_agents>[{"name": "...", "role": "...", "task": "..."}]</spawn_agents>',
            "  Delegate only when it truly helps, and at most 3 helpers.",
        ]
    else:
        lines.append("- You cannot delegate. Do all of the work yourself.")
    return "\n".join(lines)


def format_results(results: List[Dict[str, Any]]) -> str:
    """Render finished agents as text for the asker."""
    parts = ["Results from your sub-agents:"]
    for r in results:
        header = f'### {r["name"]}'
        if r.get("status") == "error":
            parts.append(f'{header}\n(failed: {r.get("error") or "no output"})')
        else:
            parts.append(f'{header}\n{_clip(r.get("text"), MAX_RESULT_CHARS)}')
    return "\n\n".join(parts)


class _Orchestrator:
    def __init__(self, runner: Runner, emit: Callable[[Dict[str, Any]], None], *, goal: str,
                 max_depth: int, max_concurrency: int, timeout: float, max_agents: int):
        self.runner = runner
        self.emit = emit
        self.goal = goal
        self.max_depth = max_depth
        self.timeout = timeout
        self.max_agents = max_agents
        self.sem = asyncio.Semaphore(max_concurrency)
        self.usage = {"prompt_tokens": 0, "completion_tokens": 0}
        self.total_agents = 0

    async def _call(self, messages: List[Dict[str, Any]], model: Optional[str]) -> str:
        for attempt in (1, 2):
            # The slot is held only while the CLI runs, so a parent waiting on its helpers never blocks them.
            async with self.sem:
                out = await asyncio.wait_for(self.runner(messages, model), timeout=self.timeout)
            self.usage["prompt_tokens"] += int(out.get("prompt_tokens") or 0)
            self.usage["completion_tokens"] += int(out.get("completion_tokens") or 0)
            text = str(out.get("text") or "")
            if attempt == 1 and len(text) < 800 and SAFETY_BLOCK_RE.search(text):
                await asyncio.sleep(1.0)
                continue
            return text
        return ""

    async def run_level(self, specs: List[Dict[str, str]], depth: int, parent: Optional[str]) -> List[Dict[str, Any]]:
        room = max(0, self.max_agents - self.total_agents)  # cap across the whole tree, helpers included
        specs = specs[:room]
        self.total_agents += len(specs)
        tasks = []
        for i, spec in enumerate(specs, start=1):
            agent_id = f"{parent}.{i}" if parent else str(i)
            tasks.append(self._run_one(spec, agent_id, depth, parent))
        return list(await asyncio.gather(*tasks))

    async def _run_one(self, spec: Dict[str, str], agent_id: str, depth: int, parent: Optional[str]) -> Dict[str, Any]:
        started = time.time()
        self.emit({"type": "agent_start", "id": agent_id, "name": spec["name"], "role": spec.get("role", ""),
                   "depth": depth, "parent": parent})
        result: Dict[str, Any] = {"id": agent_id, "name": spec["name"], "depth": depth, "parent": parent,
                                  "status": "done", "text": "", "error": ""}
        try:
            messages = [
                {"role": "system", "content": build_subagent_prompt(spec, self.goal, depth, self.max_depth)},
                {"role": "user", "content": spec["task"]},
            ]
            text = await self._call(messages, spec.get("model"))
            clean, helpers = parse_spawn_blocks(text, self.max_agents)
            if helpers and depth < self.max_depth:
                helper_results = await self.run_level(helpers, depth + 1, agent_id)
                result["children"] = [r["id"] for r in helper_results]
                messages += [
                    {"role": "assistant", "content": text},
                    {"role": "user", "content": format_results(helper_results)
                     + "\n\nNow finish your own task using these results. Do not delegate again."},
                ]
                clean, _ = parse_spawn_blocks(await self._call(messages, spec.get("model")))
            result["text"] = clean
            if not clean.strip():
                result["status"] = "error"
                result["error"] = "The agent returned nothing."
        except asyncio.CancelledError:
            raise
        except asyncio.TimeoutError:
            result["status"] = "error"
            result["error"] = f"Timed out after {self.timeout:g}s."
        except Exception as exc:  # one failing agent must not sink the others
            result["status"] = "error"
            result["error"] = str(exc) or exc.__class__.__name__
        result["elapsed"] = round(time.time() - started, 1)
        self.emit({"type": "agent_done", **result})
        return result


_END = object()


async def run_subagents(
    specs: List[Dict[str, str]],
    runner: Runner,
    *,
    goal: str = "",
    max_depth: int = 2,
    max_concurrency: int = 4,
    timeout: float = 600,
    max_agents: int = 50,
) -> AsyncGenerator[Dict[str, Any], None]:
    """Run ``specs`` in parallel and yield progress events, ending with a ``run_done`` event.

    ``runner(messages, model)`` must return ``{"text": str, "prompt_tokens": int, "completion_tokens": int}``.
    """
    max_agents = max(1, min(int(max_agents), HARD_MAX_AGENTS))
    max_depth = max(1, min(int(max_depth), HARD_MAX_DEPTH))
    max_concurrency = max(1, min(int(max_concurrency), HARD_MAX_CONCURRENCY))
    timeout = max(0.2, min(float(timeout), HARD_MAX_TIMEOUT))
    specs = normalize_specs(specs, max_agents)

    queue: "asyncio.Queue[Any]" = asyncio.Queue()
    orch = _Orchestrator(runner, queue.put_nowait, goal=goal, max_depth=max_depth,
                         max_concurrency=max_concurrency, timeout=timeout, max_agents=max_agents)

    async def main() -> None:
        try:
            results = await orch.run_level(specs, 1, None)
            queue.put_nowait({"type": "run_done", "results": results, "usage": orch.usage})
        except Exception as exc:
            queue.put_nowait({"type": "run_error", "error": str(exc) or exc.__class__.__name__})
        finally:
            queue.put_nowait(_END)

    task = asyncio.create_task(main())
    try:
        while True:
            event = await queue.get()
            if event is _END:
                break
            yield event
    finally:
        if not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
