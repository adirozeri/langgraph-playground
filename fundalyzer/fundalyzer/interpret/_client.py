"""Anthropic SDK wrapper for the interpret module.

All LLM calls go through here so tests can patch a single point.
Tool-use is used for every structured call to guarantee schema compliance —
Claude cannot return free text when a tool is required.
"""
from __future__ import annotations

import logging
from typing import Any, Protocol

import anthropic

from ..settings import settings

log = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 1024


class MessagesAPI(Protocol):
    """Structural type that matches anthropic.Anthropic().messages."""

    def create(self, **kwargs: Any) -> Any: ...


def get_client(api_key: str | None = None) -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=api_key or settings.anthropic_api_key)


def call_with_tool(
    messages_api: MessagesAPI,
    *,
    system: str,
    user_message: str,
    tool: dict[str, Any],
    model: str = DEFAULT_MODEL,
    max_tokens: int = MAX_TOKENS,
) -> dict[str, Any]:
    """Call Claude with a required tool and return the parsed tool_use input.

    Using tool_choice={"type":"tool","name":tool["name"]} forces Claude to
    respond via the tool rather than free text, guaranteeing the response
    matches the declared JSON schema.

    Raises:
        ValueError: if the response contains no tool_use block (should never
                    happen with tool_choice but guards against API changes).
    """
    log.debug("Calling Claude (%s) with tool '%s'", model, tool["name"])

    response = messages_api.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        tools=[tool],
        tool_choice={"type": "tool", "name": tool["name"]},
        messages=[{"role": "user", "content": user_message}],
    )

    for block in response.content:
        if block.type == "tool_use":
            log.debug(
                "Claude responded with tool_use; stop_reason=%s input_tokens=%d output_tokens=%d",
                response.stop_reason,
                response.usage.input_tokens,
                response.usage.output_tokens,
            )
            return block.input  # type: ignore[return-value]

    raise ValueError(
        f"Claude response contained no tool_use block. "
        f"stop_reason={response.stop_reason!r} content={response.content!r}"
    )


def call_text(
    messages_api: MessagesAPI,
    *,
    system: str,
    user_message: str,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 256,
) -> str:
    """Call Claude without a tool and return the first text block.

    Used for the synthesis summary which is a plain string, not structured JSON.
    """
    response = messages_api.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user_message}],
    )
    for block in response.content:
        if hasattr(block, "text"):
            return block.text.strip()
    raise ValueError("Claude response contained no text block.")
