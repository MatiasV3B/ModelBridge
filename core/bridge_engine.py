"""Core Bridge Engine orchestrating Antigravity CLI and SDK."""

import os
import sys
import json
import time
import uuid
import base64
import shutil
import asyncio
import subprocess
from pathlib import Path
from typing import List, Dict, Any, AsyncGenerator, Optional, Tuple
from core.config import bridge_config
from core.model_registry import model_registry
from core.file_store import file_store
from claude_agent import claude_agent_executor


class RequestMetrics:
    def __init__(self):
        self.total_requests: int = 0
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0
        self.active_requests: int = 0
        self.recent_logs: List[Dict[str, Any]] = []
        self._max_logs: int = 200

    def add_log(self, entry: Dict[str, Any]):
        self.recent_logs.append(entry)
        if len(self.recent_logs) > self._max_logs:
            self.recent_logs.pop(0)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_requests": self.total_requests,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "active_requests": self.active_requests,
            "recent_logs": self.recent_logs[-50:],
        }


metrics = RequestMetrics()


def extract_content_and_files(messages: List[Dict[str, Any]]) -> Tuple[str, List[str]]:
    """
    Formats an OpenAI messages list into an Antigravity prompt and extracts any attached files.
    """
    formatted_parts: List[str] = []
    attached_files: List[str] = []

    for msg in messages:
        role = msg.get("role", "user").upper()
        content = msg.get("content", "")

        if isinstance(content, str):
            formatted_parts.append(f"[{role}]: {content}")
        elif isinstance(content, list):
            # Multimodal parts: text, image_url, etc.
            text_subparts = []
            for part in content:
                if isinstance(part, dict):
                    part_type = part.get("type", "")
                    if part_type == "text":
                        text_subparts.append(part.get("text", ""))
                    elif part_type == "image_url":
                        img_info = part.get("image_url", {})
                        url = img_info.get("url", "")
                        if url.startswith("data:image"):
                            # Base64 image - save to temporary file
                            try:
                                header, b64data = url.split(",", 1)
                                ext = "png"
                                if "jpeg" in header or "jpg" in header:
                                    ext = "jpg"
                                elif "webp" in header:
                                    ext = "webp"
                                saved = file_store.save_file(
                                    f"inline_{uuid.uuid4().hex[:8]}.{ext}",
                                    base64.b64decode(b64data),
                                    purpose="multimodal_inline"
                                )
                                attached_files.append(saved["local_path"])
                                text_subparts.append(f"[Attached Image: {saved['filename']}]")
                            except Exception as e:
                                text_subparts.append(f"[Error loading image: {e}]")
                        else:
                            text_subparts.append(f"[Image URL: {url}]")
                    elif part_type == "file" or part_type == "file_id":
                        fid = part.get("file_id") or part.get("id")
                        path = file_store.get_file_path(fid)
                        if path:
                            attached_files.append(str(path))
                            text_subparts.append(f"[Attached Document File: {path.name}]")
            formatted_parts.append(f"[{role}]: {' '.join(text_subparts)}")

    # Add instruction for clean output format
    prompt = "\n\n".join(formatted_parts)
    return prompt, attached_files


class BridgeEngine:
    """Manages generation through CLI (agy.exe) or SDK."""

    def __init__(self):
        self.config = bridge_config

    async def generate_stream(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Stream chat completions tokens in OpenAI chunk format.
        Yields chunk dictionaries.
        """
        req_id = f"chatcmpl-{uuid.uuid4().hex[:20]}"
        created_time = int(time.time())
        effort = kwargs.get("reasoning_effort") or kwargs.get("thinking_effort") or kwargs.get("thinking_budget")
        resolved_model = model_registry.resolve_model(model, effort=effort)

        prompt, attached_files = extract_content_and_files(messages)

        metrics.active_requests += 1
        metrics.total_requests += 1
        start_time = time.time()
        log_entry = {
            "id": req_id,
            "timestamp": time.strftime("%H:%M:%S"),
            "model": resolved_model,
            "type": "stream",
            "status": "in_progress",
            "prompt_length": len(prompt),
        }
        metrics.add_log(log_entry)

        # Provider identification (supports explicit provider prefix from endpoint)
        explicit_provider = kwargs.get("provider")
        if explicit_provider == "antigravity":
            is_claude = False
            is_openai = False
            is_gemini = True
        elif explicit_provider in ("claude", "cloud"):
            is_claude = True
            is_openai = False
            is_gemini = False
        elif explicit_provider == "openai":
            is_claude = False
            is_openai = True
            is_gemini = False
        else:
            is_claude = claude_agent_executor.is_claude_model(resolved_model)
            is_openai = any(x in resolved_model.lower() for x in ["gpt", "codex", "o3", "davinci"]) and not is_claude
            is_gemini = not is_claude and not is_openai

        # Mode & Key resolution
        passed_claude_key = kwargs.get("api_key") or kwargs.get("anthropic_api_key") or self.config.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY")
        claude_mode = kwargs.get("claude_mode") or getattr(self.config, "claude_mode", "desktop")

        passed_gemini_key = kwargs.get("gemini_api_key") or self.config.gemini_api_key or os.environ.get("GEMINI_API_KEY")
        antigravity_mode = kwargs.get("antigravity_mode") or getattr(self.config, "antigravity_mode", "desktop")

        passed_openai_key = kwargs.get("openai_api_key") or self.config.openai_api_key or os.environ.get("OPENAI_API_KEY")
        openai_mode = kwargs.get("openai_mode") or getattr(self.config, "openai_mode", "desktop")

        use_claude_api = is_claude and (claude_mode == "api" or (claude_mode == "auto" and bool(passed_claude_key)))
        use_gemini_api = is_gemini and (antigravity_mode == "api" or (antigravity_mode == "auto" and bool(passed_gemini_key))) and bool(passed_gemini_key)
        use_openai_api = is_openai and (openai_mode == "api" or (openai_mode == "auto" and bool(passed_openai_key))) and bool(passed_openai_key)

        clean_kwargs = dict(kwargs)
        clean_kwargs.pop("api_key", None)
        clean_kwargs.pop("anthropic_api_key", None)
        clean_kwargs.pop("gemini_api_key", None)
        clean_kwargs.pop("openai_api_key", None)

        full_response_text = ""
        prompt_tokens = len(prompt) // 4 + 10
        completion_tokens = 0

        try:
            if use_claude_api:
                # Direct Anthropic Claude API execution with automatic fallback
                claude_streamed = False
                try:
                    async for chunk_text, event_data in self._stream_claude_agent(prompt, messages, resolved_model, api_key=passed_claude_key, **clean_kwargs):
                        if chunk_text:
                            claude_streamed = True
                            full_response_text += chunk_text
                            completion_tokens += 1
                            yield {
                                "id": req_id,
                                "object": "chat.completion.chunk",
                                "created": created_time,
                                "model": resolved_model,
                                "choices": [
                                    {
                                        "index": 0,
                                        "delta": {"content": chunk_text},
                                        "finish_reason": None,
                                    }
                                ],
                            }
                except Exception as api_err:
                    if not claude_streamed:
                        import logging
                        logging.getLogger("antigravity_bridge").warning(f"Claude API attempt failed ({api_err}). Falling back to local CLI...")
                        async for chunk_text, event_data in self._stream_cli(prompt, resolved_model, attached_files):
                            if chunk_text:
                                full_response_text += chunk_text
                                completion_tokens += 1
                                yield {
                                    "id": req_id,
                                    "object": "chat.completion.chunk",
                                    "created": created_time,
                                    "model": resolved_model,
                                    "choices": [
                                        {
                                            "index": 0,
                                            "delta": {"content": chunk_text},
                                            "finish_reason": None,
                                        }
                                    ],
                                }
                    else:
                        raise
            elif use_openai_api:
                # Direct OpenAI / ChatGPT API execution
                async for chunk_text, event_data in self._stream_openai_api(prompt, messages, resolved_model, api_key=passed_openai_key, **clean_kwargs):
                    if chunk_text:
                        full_response_text += chunk_text
                        completion_tokens += 1
                        yield {
                            "id": req_id,
                            "object": "chat.completion.chunk",
                            "created": created_time,
                            "model": resolved_model,
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": {"content": chunk_text},
                                    "finish_reason": None,
                                }
                            ],
                        }
            elif use_gemini_api:
                # Direct Google Gemini API execution with automatic fallback
                gemini_streamed = False
                try:
                    async for token in self._stream_sdk(prompt, resolved_model, attached_files):
                        if token:
                            gemini_streamed = True
                            full_response_text += token
                            completion_tokens += 1
                            yield {
                                "id": req_id,
                                "object": "chat.completion.chunk",
                                "created": created_time,
                                "model": resolved_model,
                                "choices": [
                                    {
                                        "index": 0,
                                        "delta": {"content": token},
                                        "finish_reason": None,
                                    }
                                ],
                            }
                except Exception as sdk_err:
                    if not gemini_streamed:
                        import logging
                        logging.getLogger("antigravity_bridge").warning(f"Gemini SDK attempt failed ({sdk_err}). Falling back to local CLI...")
                        async for chunk_text, event_data in self._stream_cli(prompt, resolved_model, attached_files):
                            if chunk_text:
                                full_response_text += chunk_text
                                completion_tokens += 1
                                yield {
                                    "id": req_id,
                                    "object": "chat.completion.chunk",
                                    "created": created_time,
                                    "model": resolved_model,
                                    "choices": [
                                        {
                                            "index": 0,
                                            "delta": {"content": chunk_text},
                                            "finish_reason": None,
                                        }
                                    ],
                                }
                    else:
                        raise
            elif is_openai:
                # Local Codex Desktop CLI execution
                async for chunk_text, event_data in self._stream_codex_cli(prompt, resolved_model, attached_files):
                    if chunk_text:
                        full_response_text += chunk_text
                        completion_tokens += 1
                        yield {
                            "id": req_id,
                            "object": "chat.completion.chunk",
                            "created": created_time,
                            "model": resolved_model,
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": {"content": chunk_text},
                                    "finish_reason": None,
                                }
                            ],
                        }
                    if event_data and "usage" in event_data:
                        u = event_data["usage"]
                        prompt_tokens = u.get("input_tokens", prompt_tokens)
                        completion_tokens = u.get("output_tokens", completion_tokens)
            elif is_claude:
                # Local Claude Desktop / CLI execution
                claude_binary = getattr(self.config, "claude_binary_path", "") or shutil.which("claude")
                streamed_claude = False
                if claude_binary and (shutil.which(claude_binary) or os.path.exists(claude_binary)):
                    try:
                        async for chunk_text, event_data in self._stream_claude_cli(prompt, resolved_model, attached_files):
                            if chunk_text:
                                streamed_claude = True
                                full_response_text += chunk_text
                                completion_tokens += 1
                                yield {
                                    "id": req_id,
                                    "object": "chat.completion.chunk",
                                    "created": created_time,
                                    "model": resolved_model,
                                    "choices": [
                                        {
                                            "index": 0,
                                            "delta": {"content": chunk_text},
                                            "finish_reason": None,
                                        }
                                    ],
                                }
                            if event_data and "usage" in event_data:
                                u = event_data["usage"]
                                prompt_tokens = u.get("input_tokens", prompt_tokens)
                                completion_tokens = u.get("output_tokens", completion_tokens)
                    except Exception as err:
                        if not streamed_claude:
                            logger.warning(f"Claude CLI execution failed ({err}), falling back to Antigravity CLI.")
                        else:
                            raise

                if not streamed_claude:
                    # Fallback to Antigravity CLI which natively supports Claude models
                    async for chunk_text, event_data in self._stream_cli(prompt, resolved_model, attached_files):
                        if chunk_text:
                            full_response_text += chunk_text
                            completion_tokens += 1
                            yield {
                                "id": req_id,
                                "object": "chat.completion.chunk",
                                "created": created_time,
                                "model": resolved_model,
                                "choices": [
                                    {
                                        "index": 0,
                                        "delta": {"content": chunk_text},
                                        "finish_reason": None,
                                    }
                                ],
                            }
                        if event_data and "usage" in event_data:
                            u = event_data["usage"]
                            prompt_tokens = u.get("input_tokens", prompt_tokens)
                            completion_tokens = u.get("output_tokens", completion_tokens)
            else:
                # Local Desktop / CLI execution (Antigravity Desktop agy.exe)
                async for chunk_text, event_data in self._stream_cli(prompt, resolved_model, attached_files):
                    if chunk_text:
                        full_response_text += chunk_text
                        completion_tokens += 1
                        yield {
                            "id": req_id,
                            "object": "chat.completion.chunk",
                            "created": created_time,
                            "model": resolved_model,
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": {"content": chunk_text},
                                    "finish_reason": None,
                                }
                            ],
                        }
                    if event_data and "usage" in event_data:
                        u = event_data["usage"]
                        prompt_tokens = u.get("input_tokens", prompt_tokens)
                        completion_tokens = u.get("output_tokens", completion_tokens)

            # Final finish chunk
            yield {
                "id": req_id,
                "object": "chat.completion.chunk",
                "created": created_time,
                "model": resolved_model,
                "choices": [
                    {
                        "index": 0,
                        "delta": {},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                }
            }

            duration = round(time.time() - start_time, 2)
            metrics.total_input_tokens += prompt_tokens
            metrics.total_output_tokens += completion_tokens
            log_entry["status"] = "success"
            log_entry["duration"] = f"{duration}s"
            log_entry["tokens"] = f"{prompt_tokens}/{completion_tokens}"

        except Exception as e:
            duration = round(time.time() - start_time, 2)
            log_entry["status"] = "error"
            log_entry["duration"] = f"{duration}s"
            log_entry["error"] = str(e)
            yield {
                "id": req_id,
                "object": "chat.completion.chunk",
                "created": created_time,
                "model": resolved_model,
                "choices": [
                    {
                        "index": 0,
                        "delta": {"content": f"\n[Antigravity Bridge Error: {e}]"},
                        "finish_reason": "error",
                    }
                ],
            }
        finally:
            metrics.active_requests = max(0, metrics.active_requests - 1)

    async def generate_sync(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Generate non-streaming response in OpenAI Chat Completions format.
        """
        req_id = f"chatcmpl-{uuid.uuid4().hex[:20]}"
        created_time = int(time.time())
        resolved_model = model_registry.resolve_model(model)

        full_content = ""
        prompt_tokens = 0
        completion_tokens = 0

        async for chunk in self.generate_stream(
            messages=messages,
            model=resolved_model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        ):
            choices = chunk.get("choices", [])
            if choices:
                delta = choices[0].get("delta", {})
                content = delta.get("content")
                if content:
                    full_content += content
            if "usage" in chunk:
                u = chunk["usage"]
                prompt_tokens = u.get("prompt_tokens", 0)
                completion_tokens = u.get("completion_tokens", 0)

        if prompt_tokens == 0:
            prompt_tokens = len(str(messages)) // 4 + 10
        if completion_tokens == 0:
            completion_tokens = len(full_content) // 4 + 1

        return {
            "id": req_id,
            "object": "chat.completion",
            "created": created_time,
            "model": resolved_model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": full_content,
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }

    async def _stream_cli(
        self, prompt: str, model: str, attached_files: List[str]
    ) -> AsyncGenerator[Tuple[str, Optional[Dict[str, Any]]], None]:
        """Stream chunks by spawning `agy.exe` with stream-json."""
        agy_path = self.config.agy_binary_path
        if not agy_path or not os.path.exists(agy_path):
            raise RuntimeError(f"Antigravity CLI not found at: '{agy_path}'. Please run installer or check PATH.")

        cmd = [
            agy_path,
            "-p", prompt,
            "--model", model,
            "--output-format", "stream-json",
            "--dangerously-skip-permissions",
        ]

        if "-high" in model:
            cmd.extend(["--effort", "high"])
        elif "-medium" in model:
            cmd.extend(["--effort", "medium"])
        elif "-low" in model:
            cmd.extend(["--effort", "low"])

        # If there are attached files or workspace folders, add their parent dir
        for f in attached_files:
            p = Path(f)
            if p.exists():
                cmd.extend(["--add-dir", str(p.parent)])

        # Create async subprocess without creating any terminal/console window
        extra_kwargs = {}
        if sys.platform == "win32":
            extra_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(Path.home()),
            **extra_kwargs,
        )

        in_thinking = False
        while True:
            line_bytes = await process.stdout.readline()
            if not line_bytes:
                break

            line = line_bytes.decode("utf-8", errors="replace").strip()
            if not line:
                continue

            try:
                data = json.loads(line)
                event_type = data.get("event")

                if event_type == "step_update":
                    step = data.get("step_update", {})
                    
                    # Check for explicit thinking/reasoning delta first
                    thinking_delta = step.get("thinking_delta") or step.get("thought_delta") or step.get("reasoning_delta")
                    if thinking_delta:
                        if not in_thinking:
                            yield (f"<thought>{thinking_delta}", None)
                            in_thinking = True
                        else:
                            yield (thinking_delta, None)

                    # Streaming text delta
                    text_delta = step.get("text_delta")
                    if text_delta:
                        if in_thinking:
                            yield (f"</thought>\n\n{text_delta}", None)
                            in_thinking = False
                        else:
                            yield (text_delta, None)

                elif event_type == "result":
                    if in_thinking:
                        yield ("</thought>\n\n", None)
                        in_thinking = False
                    result = data.get("result", {})
                    if result.get("status") == "ERROR":
                        err_text = result.get("error", "Error desconocido en Antigravity CLI")
                        yield (f"\n[Antigravity Error: {err_text}]\n", result)
                    else:
                        yield ("", result)

            except json.JSONDecodeError:
                # Raw text fallback if non-json line appeared
                if in_thinking:
                    yield ("</thought>\n\n", None)
                    in_thinking = False
                yield (line + "\n", None)

        if in_thinking:
            yield ("</thought>\n\n", None)
            in_thinking = False

        await process.wait()

    async def _stream_codex_cli(
        self, prompt: str, model: str, attached_files: List[str]
    ) -> AsyncGenerator[Tuple[str, Optional[Dict[str, Any]]], None]:
        """Stream chunks by spawning `codex.exe exec --json --skip-git-repo-check -`."""
        codex_path = getattr(self.config, "codex_binary_path", "")
        if not codex_path or not os.path.exists(codex_path):
            from core.auth_status import find_codex_binary
            codex_path = find_codex_binary() or "codex"

        cmd = [
            codex_path,
            "exec",
            "--json",
            "--skip-git-repo-check",
            "-",
        ]

        # Check if a model is explicitly passed that is supported by current login
        # Note: ChatGPT subscription auth in Codex CLI rejects explicit -m gpt-4o/o3 if not in config.
        # Only pass -m if user explicitly picked a non-default custom model name that isn't standard chatgpt alias
        m_lower = model.lower().strip()
        if m_lower and not any(x in m_lower for x in ["gpt-4o", "chatgpt", "codex", "default"]):
            cmd.extend(["-m", model])

        # Attach directory contexts if available
        for f in attached_files:
            p = Path(f)
            if p.exists():
                cmd.extend(["--add-dir", str(p.parent)])

        extra_kwargs = {}
        if sys.platform == "win32":
            extra_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **extra_kwargs,
        )

        # Write prompt to stdin and close stdin so codex exec knows input is finished
        try:
            prompt_bytes = prompt.encode("utf-8")
            process.stdin.write(prompt_bytes)
            await process.stdin.drain()
            process.stdin.close()
            await process.stdin.wait_closed()
        except Exception as e:
            yield (f"\n[Codex Stdin Error: {e}]\n", None)
            return

        in_thinking = False
        while True:
            line_bytes = await process.stdout.readline()
            if not line_bytes:
                break

            line = line_bytes.decode("utf-8", errors="replace").strip()
            if not line:
                continue

            try:
                data = json.loads(line)
                event_type = data.get("type")

                # Agent message item completed
                if event_type == "item.completed":
                    item = data.get("item", {})
                    itype = item.get("type")
                    if itype == "agent_message":
                        text = item.get("text", "")
                        if in_thinking:
                            yield ("</thought>\n\n", None)
                            in_thinking = False
                        if text:
                            yield (text, None)
                    elif itype == "reasoning":
                        reasoning = item.get("text") or item.get("reasoning", "")
                        if reasoning:
                            if not in_thinking:
                                yield (f"<thought>{reasoning}", None)
                                in_thinking = True
                            else:
                                yield (reasoning, None)

                # Real-time delta streaming if supported in current CLI version
                elif event_type in ("item.delta", "text_delta", "agent_message.delta"):
                    delta_text = data.get("delta", {}).get("text") or data.get("text") or ""
                    if delta_text:
                        if in_thinking:
                            yield (f"</thought>\n\n{delta_text}", None)
                            in_thinking = False
                        else:
                            yield (delta_text, None)

                elif event_type == "turn.completed":
                    if in_thinking:
                        yield ("</thought>\n\n", None)
                        in_thinking = False
                    usage = data.get("usage", {})
                    yield ("", {"usage": {
                        "input_tokens": usage.get("input_tokens", 0),
                        "output_tokens": usage.get("output_tokens", 0),
                    }})

                elif event_type in ("error", "turn.failed"):
                    if in_thinking:
                        yield ("</thought>\n\n", None)
                        in_thinking = False
                    err_msg = data.get("message") or data.get("error", {}).get("message") or "Error en Codex CLI"
                    yield (f"\n[Codex Error: {err_msg}]\n", None)

            except json.JSONDecodeError:
                if in_thinking:
                    yield ("</thought>\n\n", None)
                    in_thinking = False
                yield (line + "\n", None)

        if in_thinking:
            yield ("</thought>\n\n", None)
            in_thinking = False

        await process.wait()

    async def _stream_claude_cli(
        self, prompt: str, model: str, attached_files: List[str]
    ) -> AsyncGenerator[Tuple[str, Optional[Dict[str, Any]]], None]:
        """Stream chunks by spawning `claude -p - --output-format stream-json --verbose --include-partial-messages`."""
        claude_path = getattr(self.config, "claude_binary_path", "") or shutil.which("claude") or "claude"

        cmd = [
            claude_path,
            "-p", "-",
            "--output-format", "stream-json",
            "--verbose",
            "--include-partial-messages",
            "--dangerously-skip-permissions",
        ]

        # Map or pass model if supported
        clean_model = model.strip()
        if clean_model:
            # Map friendly aliases if needed
            if "sonnet-4-6" in clean_model:
                clean_model = "claude-sonnet-4-6"
            elif "opus-4-7" in clean_model:
                clean_model = "claude-opus-4-7"
            elif "haiku-4-5" in clean_model:
                clean_model = "claude-haiku-4-5"
            cmd.extend(["--model", clean_model])

        for f in attached_files:
            p = Path(f)
            if p.exists():
                cmd.extend(["--add-dir", str(p.parent)])

        extra_kwargs = {}
        if sys.platform == "win32":
            extra_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **extra_kwargs,
        )

        try:
            prompt_bytes = prompt.encode("utf-8")
            process.stdin.write(prompt_bytes)
            await process.stdin.drain()
            process.stdin.close()
            await process.stdin.wait_closed()
        except Exception as e:
            yield (f"\n[Claude Stdin Error: {e}]\n", None)
            return

        in_thinking = False
        while True:
            line_bytes = await process.stdout.readline()
            if not line_bytes:
                break

            line = line_bytes.decode("utf-8", errors="replace").strip()
            if not line:
                continue

            try:
                data = json.loads(line)
                ev_type = data.get("type")

                # Real-time token streaming via stream_event
                if ev_type == "stream_event":
                    event = data.get("event", {})
                    etype = event.get("type")
                    if etype == "content_block_delta":
                        delta = event.get("delta", {})
                        if delta.get("type") == "text_delta":
                            chunk_text = delta.get("text", "")
                            if chunk_text:
                                yield (chunk_text, None)
                        elif delta.get("type") == "thinking_delta":
                            thinking_text = delta.get("thinking", "")
                            if thinking_text:
                                if not in_thinking:
                                    yield (f"<thought>{thinking_text}", None)
                                    in_thinking = True
                                else:
                                    yield (thinking_text, None)

                # Fallback block parsing
                elif ev_type == "assistant":
                    msg = data.get("message", {})
                    for block in msg.get("content", []):
                        if block.get("type") == "text":
                            t = block.get("text", "")
                            # Only yield if not already streamed
                            pass

                elif ev_type == "result":
                    if in_thinking:
                        yield ("</thought>\n\n", None)
                        in_thinking = False
                    usage = data.get("usage", {})
                    yield ("", {"usage": {
                        "input_tokens": usage.get("input_tokens", 0),
                        "output_tokens": usage.get("output_tokens", 0),
                    }})

                elif ev_type in ("error", "fatal"):
                    if in_thinking:
                        yield ("</thought>\n\n", None)
                        in_thinking = False
                    err_msg = data.get("message") or data.get("error", {}).get("message") or "Error en Claude Code CLI"
                    yield (f"\n[Claude Code Error: {err_msg}]\n", None)

            except json.JSONDecodeError:
                if in_thinking:
                    yield ("</thought>\n\n", None)
                    in_thinking = False
                yield (line + "\n", None)

        if in_thinking:
            yield ("</thought>\n\n", None)
            in_thinking = False

        await process.wait()

    async def _stream_sdk(
        self, prompt: str, model: str, attached_files: List[str]
    ) -> AsyncGenerator[str, None]:
        """Stream tokens using python `google.antigravity.Agent`."""
        try:
            from google.antigravity import Agent, LocalAgentConfig
            from google.antigravity.types import CapabilitiesConfig, Image, Document
        except ImportError:
            raise RuntimeError("google-antigravity SDK is not installed in the current Python environment.")

        api_key = self.config.gemini_api_key or os.environ.get("GEMINI_API_KEY")
        agent_config = LocalAgentConfig(
            model=model,
            api_key=api_key,
            capabilities=CapabilitiesConfig(),
        )

        chat_inputs = [prompt]
        for fpath in attached_files:
            f = Path(fpath)
            if f.suffix.lower() in [".png", ".jpg", ".jpeg", ".webp"]:
                chat_inputs.append(Image.from_file(str(f)))
            elif f.suffix.lower() in [".pdf", ".txt", ".md", ".json"]:
                chat_inputs.append(Document.from_file(str(f)))

        async with Agent(agent_config) as agent:
            response = await agent.chat(chat_inputs if len(chat_inputs) > 1 else prompt)
            async for token in response:
                yield token

    async def _stream_openai_api(
        self, prompt: str, messages: List[Dict[str, Any]], model: str, api_key: str, **kwargs
    ) -> AsyncGenerator[Tuple[str, Optional[Dict[str, Any]]], None]:
        """Stream chunks using official OpenAI Chat Completions API with adaptive parameter handling."""
        import httpx
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        clean_model = model.replace("gpt-5-codex", "gpt-4o").replace("codex", "gpt-4o")
        msgs = messages if messages else [{"role": "user", "content": prompt}]
        actual_model = clean_model if ("gpt" in clean_model or "o3" in clean_model or "o1" in clean_model) else "gpt-4o"
        is_reasoning_model = any(actual_model.lower().startswith(x) for x in ["o1", "o3", "o4"]) or "gpt-5" in actual_model.lower()

        payload: Dict[str, Any] = {
            "model": actual_model,
            "messages": msgs,
            "stream": True,
        }

        effort = kwargs.get("reasoning_effort") or kwargs.get("thinking_effort") or "medium"
        if is_reasoning_model:
            # OpenAI documentation: Reasoning models (o1, o3-mini) support reasoning_effort
            # and MUST NOT include temperature
            payload["reasoning_effort"] = effort if effort in ["low", "medium", "high"] else "medium"
        else:
            temp = kwargs.get("temperature")
            payload["temperature"] = temp if temp is not None else 0.2

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(url, json=payload, headers=headers)
                if response.status_code != 200:
                    err_text = response.text
                    # Auto-recovery for parameter mismatches
                    if "temperature" in err_text and ("not supported" in err_text or "unsupported" in err_text):
                        payload.pop("temperature", None)
                        payload["reasoning_effort"] = effort if effort in ["low", "medium", "high"] else "medium"
                    elif "reasoning_effort" in err_text and ("not supported" in err_text or "unsupported" in err_text):
                        payload.pop("reasoning_effort", None)
                        payload["temperature"] = 0.2
                    else:
                        yield (f"\n[OpenAI API Error {response.status_code}: {err_text}]\n", None)
                        return

                async with client.stream("POST", url, json=payload, headers=headers) as stream_resp:
                    if stream_resp.status_code != 200:
                        err_bytes = await stream_resp.aread()
                        yield (f"\n[OpenAI API Error {stream_resp.status_code}: {err_bytes.decode('utf-8', errors='ignore')}]\n", None)
                        return
                    async for line in stream_resp.aiter_lines():
                        if line.startswith("data: "):
                            data_str = line[6:].strip()
                            if data_str == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data_str)
                                delta = chunk.get("choices", [{}])[0].get("delta", {})
                                content = delta.get("content", "")
                                if content:
                                    yield (content, None)
                            except Exception:
                                continue
        except Exception as e:
            yield (f"\n[OpenAI Connection Error: {str(e)}]\n", None)

    async def _stream_claude_agent(
        self, prompt: str, messages: List[Dict[str, Any]], model: str, **kwargs
    ) -> AsyncGenerator[Tuple[str, Optional[Dict[str, Any]]], None]:
        """Stream chunks using official Claude with extended thinking and browser tools."""
        # Calculate thinking budget based on model
        m_lower = model.lower()
        supports_thinking = any(x in m_lower for x in ["5-5", "5.5", "4-6", "4.6", "3-7", "3.7", "opus", "fable", "thinking", "haiku"])
        effort = kwargs.get("reasoning_effort") or kwargs.get("thinking_effort")
        effort_map = {
            "fast": 0,
            "low": 1024,
            "medium": 4096,
            "thinking": 4096,
            "high": 8192,
            "x-high": 16384,
            "max": 32768,
        }
        if effort == "fast":
            thinking_budget = 0
        else:
            mapped_budget = effort_map.get(effort) if effort else None
            thinking_budget = kwargs.get("thinking_budget") if kwargs.get("thinking_budget") is not None else (mapped_budget if mapped_budget is not None else (4096 if supports_thinking else 0))

        in_thinking = False

        async for event in claude_agent_executor.run_agent(
            prompt=prompt,
            messages=messages,
            model=model,
            thinking_budget=thinking_budget,
            effort=effort,
            api_key=kwargs.get("api_key") or self.config.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY")
        ):
            etype = event.get("type")
            if etype == "reasoning":
                text = event.get("thinking", "")
                if not in_thinking:
                    yield (f"<thought>{text}", None)
                    in_thinking = True
                else:
                    yield (text, None)
            elif etype == "chunk":
                text = event.get("text", "")
                if in_thinking:
                    yield (f"</thought>\n\n{text}", None)
                    in_thinking = False
                else:
                    yield (text, None)
            elif etype == "tool_call":
                if in_thinking:
                    yield ("</thought>\n\n", None)
                    in_thinking = False
                tool_name = event.get("tool")
                args = json.dumps(event.get("arguments", {}), ensure_ascii=False)
                yield (f"\n\n⚙️ *[Claude Agent Tool: `{tool_name}`]*\n```json\n{args}\n```\n\n", None)
            elif etype == "complete":
                if in_thinking:
                    yield ("</thought>\n\n", None)
                    in_thinking = False
                yield ("", {"usage": event.get("usage", {})})
            elif etype == "error":
                if in_thinking:
                    yield ("</thought>\n\n", None)
                    in_thinking = False
                err_msg = event.get("message") or "Claude Agent error"
                raise RuntimeError(err_msg)

        if in_thinking:
            yield ("</thought>\n\n", None)


bridge_engine = BridgeEngine()

