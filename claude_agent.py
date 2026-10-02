import os
import json
import logging
from typing import AsyncGenerator, Dict, Any, List, Optional
import anthropic
from anthropic import AsyncAnthropic

logger = logging.getLogger("AntigravityBridge.ClaudeAgent")

# Model aliases and mapping
CLAUDE_MODELS = {
    # Claude Sonnet 5.5
    "claude-sonnet-5-5": "claude-sonnet-5-5",
    "claude-sonnet-5.5": "claude-sonnet-5-5",
    "claude-5-5-sonnet": "claude-sonnet-5-5",
    "claude-5.5-sonnet": "claude-sonnet-5-5",
    "sonnet-5.5": "claude-sonnet-5-5",
    "claude-sonnet": "claude-sonnet-5-5",

    # Claude Opus 5.5 / 4.6
    "claude-opus-5-5": "claude-opus-5-5",
    "claude-opus-5.5": "claude-opus-5-5",
    "claude-5-5-opus": "claude-opus-5-5",
    "claude-5.5-opus": "claude-opus-5-5",
    "opus-5.5": "claude-opus-5-5",
    "claude-opus": "claude-opus-5-5",
    "claude-opus-4-6-thinking": "claude-3-opus-20240229",
    "claude-opus-4.6": "claude-3-opus-20240229",
    "claude-3-opus": "claude-3-opus-20240229",

    # Claude Fable 5.1
    "claude-fable-5-1": "claude-fable-5-1",
    "claude-fable-5.1": "claude-fable-5-1",
    "claude-5-1-fable": "claude-fable-5-1",
    "claude-5.1-fable": "claude-fable-5-1",
    "fable-5.1": "claude-fable-5-1",
    "claude-fable": "claude-fable-5-1",

    # Claude Haiku 4.5
    "claude-haiku-4-5": "claude-haiku-4-5",
    "claude-haiku-4.5": "claude-haiku-4-5",
    "claude-4-5-haiku": "claude-haiku-4-5",
    "claude-4.5-haiku": "claude-haiku-4-5",
    "haiku-4.5": "claude-haiku-4-5",
    "claude-haiku": "claude-haiku-4-5",

    # Claude 3.7 / 3.5 Fallbacks
    "claude-sonnet-4-6": "claude-3-7-sonnet-20250219",
    "claude-3.7-sonnet": "claude-3-7-sonnet-20250219",
    "claude-3-7-sonnet": "claude-3-7-sonnet-20250219",
    "claude-3.5-sonnet": "claude-3-5-sonnet-20241022",
    "claude-3-5-sonnet": "claude-3-5-sonnet-20241022",
    "claude-3-5-haiku": "claude-3-5-haiku-20241022",
}

FALLBACK_STABLE_MODELS = {
    "claude-sonnet-5-5": "claude-3-7-sonnet-20250219",
    "claude-opus-5-5": "claude-3-opus-20240229",
    "claude-fable-5-1": "claude-3-7-sonnet-20250219",
    "claude-haiku-4-5": "claude-3-5-haiku-20241022",
}

DEFAULT_CLAUDE_MODEL = "claude-sonnet-5-5"

# Standard Browser Agent Tool Definitions for Claude Agent SDK
BROWSER_AGENT_TOOLS = [
    {
        "name": "click_element",
        "description": "Click an interactive element on the active browser webpage by selector or coordinates.",
        "input_schema": {
            "type": "object",
            "properties": {
                "selector": {
                    "type": "string",
                    "description": "CSS selector or element description to click."
                },
                "coordinates": {
                    "type": "object",
                    "properties": {
                        "x": {"type": "number"},
                        "y": {"type": "number"}
                    },
                    "description": "Optional (x, y) coordinates."
                }
            },
            "required": ["selector"]
        }
    },
    {
        "name": "type_text",
        "description": "Type text into an input field or textarea on the active webpage.",
        "input_schema": {
            "type": "object",
            "properties": {
                "selector": {
                    "type": "string",
                    "description": "CSS selector of the target input/textarea."
                },
                "text": {
                    "type": "string",
                    "description": "Text to enter into the field."
                },
                "press_enter": {
                    "type": "boolean",
                    "description": "Whether to press Enter after typing."
                }
            },
            "required": ["selector", "text"]
        }
    },
    {
        "name": "navigate_to",
        "description": "Navigate the browser tab to a specific URL.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The destination URL to open (including https://)."
                }
            },
            "required": ["url"]
        }
    },
    {
        "name": "scroll_page",
        "description": "Scroll the active page up, down, or to a specific section.",
        "input_schema": {
            "type": "object",
            "properties": {
                "direction": {
                    "type": "string",
                    "enum": ["up", "down", "top", "bottom"],
                    "description": "Direction to scroll."
                },
                "amount": {
                    "type": "number",
                    "description": "Pixels to scroll (default 500)."
                }
            },
            "required": ["direction"]
        }
    },
    {
        "name": "capture_screenshot",
        "description": "Capture a screenshot of the current viewport for visual verification.",
        "input_schema": {
            "type": "object",
            "properties": {
                "full_page": {
                    "type": "boolean",
                    "description": "Whether to capture full page or visible area."
                }
            }
        }
    },
    {
        "name": "extract_dom_text",
        "description": "Extract text or structured content from a section of the page.",
        "input_schema": {
            "type": "object",
            "properties": {
                "selector": {
                    "type": "string",
                    "description": "CSS selector to extract text from (default 'body')."
                }
            }
        }
    },
    {
        "name": "press_key",
        "description": "Press a keyboard key or key combination on the active page.",
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "Key name (e.g. 'Enter', 'Escape', 'Tab', 'ArrowDown')."
                }
            },
            "required": ["key"]
        }
    },
    {
        "name": "wait_seconds",
        "description": "Wait for a specified number of seconds for page animations or content to load.",
        "input_schema": {
            "type": "object",
            "properties": {
                "seconds": {
                    "type": "number",
                    "description": "Seconds to wait (between 0.5 and 10)."
                }
            },
            "required": ["seconds"]
        }
    }
]


class ClaudeAgentExecutor:
    """
    Antigravity Bridge - Claude Agent SDK Executor.
    Provides streaming responses, extended thinking (CoT), and browser tool calling
    supporting Sonnet 5.5, Opus 5.5, Fable 5.1, and Haiku 4.5.
    """
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            logger.info("ANTHROPIC_API_KEY is not set yet in environment. Key can be provided per request or in settings.")
        self.client = AsyncAnthropic(api_key=self.api_key) if self.api_key else None

    def resolve_model(self, model_id: Optional[str]) -> str:
        if not model_id:
            return DEFAULT_CLAUDE_MODEL
        m_lower = model_id.lower().strip()
        return CLAUDE_MODELS.get(m_lower, model_id)

    def is_claude_model(self, model_id: Optional[str]) -> bool:
        if not model_id:
            return False
        m_lower = model_id.lower().strip()
        return (
            "claude" in m_lower or
            "sonnet" in m_lower or
            "opus" in m_lower or
            "fable" in m_lower or
            "haiku" in m_lower
        )

    async def run_agent(
        self,
        prompt: str,
        messages: Optional[List[Dict[str, Any]]] = None,
        system_prompt: Optional[str] = None,
        page_context: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None,
        thinking_budget: int = 0,
        api_key: Optional[str] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Executes a turn with Claude via Anthropic Messages Stream API.
        Yields structured SSE/JSON event dictionaries for the Antigravity frontend.
        """
        effective_key = api_key or self.api_key or os.getenv("ANTHROPIC_API_KEY")
        if not effective_key:
            yield {
                "type": "error",
                "message": "Falta la API Key de Anthropic. Configura ANTHROPIC_API_KEY en tu entorno o en los ajustes de Antigravity Bridge."
            }
            return

        active_client = AsyncAnthropic(api_key=effective_key)
        resolved_model = self.resolve_model(model)

        # Build system directive
        base_system = (
            system_prompt or
            "Eres el copiloto autónomo Antigravity para el navegador web. "
            "Ayudas al usuario analizando páginas, navegando y ejecutando tareas con precisión."
        )

        # Format message history
        conversation_messages: List[Dict[str, Any]] = []
        if messages and len(messages) > 0:
            for msg in messages:
                role = msg.get("role", "user")
                if role not in ["user", "assistant"]:
                    role = "user"
                content = msg.get("content", "")
                conversation_messages.append({
                    "role": role,
                    "content": content
                })
        else:
            full_user_content = prompt
            if page_context:
                full_user_content = f"<contexto_de_pagina>\n{page_context}\n</contexto_de_pagina>\n\n{prompt}"
            conversation_messages.append({
                "role": "user",
                "content": full_user_content
            })

        # Helper to execute stream with a specific model
        async def _execute_stream(target_model: str):
            call_kwargs: Dict[str, Any] = {
                "model": target_model,
                "max_tokens": 8192,
                "system": base_system,
                "messages": conversation_messages,
            }

            # Extended Thinking for Claude models that support thinking
            supports_thinking = any(x in target_model.lower() for x in ["3-7", "3.7", "5-5", "5.5", "4-6", "4.6", "opus", "fable", "sonnet", "haiku"])
            if thinking_budget > 0 and supports_thinking:
                budget = max(1024, min(thinking_budget, 32768))
                call_kwargs["thinking"] = {
                    "type": "enabled",
                    "budget_tokens": budget
                }
                call_kwargs["max_tokens"] = max(call_kwargs.get("max_tokens", 8192), budget + 4096)

            # Assign tools (custom or default browser agent tools)
            agent_tools = tools if tools is not None else BROWSER_AGENT_TOOLS
            if agent_tools:
                call_kwargs["tools"] = agent_tools

            async with active_client.messages.stream(**call_kwargs) as stream:
                async for event in stream:
                    event_type = getattr(event, "type", None)

                    # Text delta
                    if event_type == "text":
                        yield {
                            "type": "chunk",
                            "text": event.text
                        }
                    # Thinking delta (CoT)
                    elif event_type == "thinking":
                        yield {
                            "type": "reasoning",
                            "thinking": event.thinking
                        }
                    # Tool use block
                    elif event_type == "tool_use":
                        yield {
                            "type": "tool_call",
                            "tool": event.name,
                            "arguments": event.input
                        }

                final_msg = await stream.get_final_message()
                yield {
                    "type": "complete",
                    "stop_reason": getattr(final_msg, "stop_reason", "end_turn"),
                    "usage": {
                        "input_tokens": final_msg.usage.input_tokens if hasattr(final_msg, "usage") else 0,
                        "output_tokens": final_msg.usage.output_tokens if hasattr(final_msg, "usage") else 0,
                    }
                }

        try:
            async for item in _execute_stream(resolved_model):
                yield item
        except anthropic.NotFoundError:
            # Automatic graceful fallback if requested model is not yet in public tier
            fallback = FALLBACK_STABLE_MODELS.get(resolved_model, "claude-3-7-sonnet-20250219")
            logger.warning(f"Model '{resolved_model}' not found in Anthropic API tier. Falling back gracefully to '{fallback}'.")
            try:
                async for item in _execute_stream(fallback):
                    yield item
            except Exception as fb_err:
                logger.error(f"Fallback to '{fallback}' failed: {fb_err}")
                yield {
                    "type": "error",
                    "message": f"Error de Claude API ({fb_err.__class__.__name__}): {str(fb_err)}"
                }
        except anthropic.APIError as api_err:
            logger.error(f"Claude API Error: {api_err}")
            yield {
                "type": "error",
                "message": f"Error de Claude API ({api_err.__class__.__name__}): {str(api_err)}"
            }
        except Exception as e:
            logger.exception("Unexpected error in Claude Agent")
            yield {
                "type": "error",
                "message": f"Error inesperado al ejecutar Claude Agent: {str(e)}"
            }


claude_agent_executor = ClaudeAgentExecutor()
