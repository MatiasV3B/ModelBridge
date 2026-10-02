"""Core Bridge Engine orchestrating Antigravity CLI and SDK."""

import os
import sys
import json
import time
import uuid
import base64
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
        resolved_model = model_registry.resolve_model(model)

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

        # Provider identification
        is_claude = claude_agent_executor.is_claude_model(resolved_model)
        is_openai = any(x in resolved_model.lower() for x in ["gpt", "codex", "o3", "davinci"]) and not is_claude
        is_gemini = "gemini" in resolved_model.lower() and not is_claude and not is_openai

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

        full_response_text = ""
        prompt_tokens = len(prompt) // 4 + 10
        completion_tokens = 0

        try:
            if use_claude_api:
                # Direct Anthropic Claude API execution
                async for chunk_text, event_data in self._stream_claude_agent(prompt, messages, resolved_model, api_key=passed_claude_key, **kwargs):
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
            elif use_openai_api:
                # Direct OpenAI / ChatGPT API execution
                async for chunk_text, event_data in self._stream_openai_api(prompt, messages, resolved_model, api_key=passed_openai_key, **kwargs):
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
                # Direct Google Gemini API execution
                async for token in self._stream_sdk(prompt, resolved_model, attached_files):
                    if token:
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
            else:
                # Local Desktop / CLI execution (Antigravity Desktop, Claude Desktop CLI, or Codex Desktop)
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
        """Stream chunks using official OpenAI Chat Completions API."""
        import httpx
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        clean_model = model.replace("gpt-5-codex", "gpt-4o").replace("codex", "gpt-4o")
        msgs = messages if messages else [{"role": "user", "content": prompt}]
        payload = {
            "model": clean_model if ("gpt" in clean_model or "o3" in clean_model) else "gpt-4o",
            "messages": msgs,
            "stream": True,
        }
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream("POST", url, json=payload, headers=headers) as response:
                    if response.status_code != 200:
                        err_bytes = await response.aread()
                        yield (f"\n[OpenAI API Error {response.status_code}: {err_bytes.decode('utf-8', errors='ignore')}]\n", None)
                        return
                    async for line in response.aiter_lines():
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
                yield (f"\n[Error Claude Agent: {event.get('message')}]\n", None)

        if in_thinking:
            yield ("</thought>\n\n", None)


bridge_engine = BridgeEngine()

