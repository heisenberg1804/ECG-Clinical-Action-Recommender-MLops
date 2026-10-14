"""
The tutor's model call (D-56).

`TutorModel.stream()` turns one Messages API call into three kinds of events:
("text", delta), ("progress", delta) for Opus 5.5's between-tool-call updates,
and a closing ("final", message), where `message` is the assistant turn as plain
dicts. The chat loop only sees these, so CI drives it with a scripted fake.
"""
import os
from collections.abc import AsyncIterator
from typing import Any, Protocol

import anthropic

DEFAULT_MODEL = "claude-opus-5-5"
BETAS = [
    "server-side-fallback-2026-07-01",  # fallbacks="default": a refusal is retried server-side
    "thinking-display-updates-2026-08-18",  # between-tool-call progress notes as text
    "thinking-binding-controls-2026-08-01",  # drop, not reject, thinking blocks if history changed
]
MAX_JSON_RETRIES = 2

Event = tuple[str, Any]


class Model(Protocol):
    def stream(self, *, system: str, tools: list[dict], messages: list[dict]
               ) -> AsyncIterator[Event]: ...


class TutorModel:
    def __init__(self, client: Any = None):
        self.client = client or anthropic.AsyncAnthropic(max_retries=2, timeout=120.0)
        self.model = os.getenv("TUTOR_MODEL", DEFAULT_MODEL)
        # Opus 5.5 defaults to medium; set it explicitly so a default change can't move it
        self.effort = os.getenv("TUTOR_EFFORT", "medium")
        # Thinking counts toward max_tokens, so leave room beyond the ~150-word reply
        self.max_tokens = int(os.getenv("TUTOR_MAX_TOKENS", "8000"))

    def request(self, system: str, tools: list[dict], messages: list[dict]) -> dict[str, Any]:
        return {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "betas": BETAS,
            "fallbacks": "default",
            "thinking": {"type": "adaptive", "display": "updates",
                         "block_binding": {"prefix_mismatch_behavior": "drop_block"}},
            "output_config": {"effort": self.effort},
            # The system prompt is the same for every session; the history grows by
            # appending, so automatic caching reuses it turn after turn
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "cache_control": {"type": "ephemeral"},
            "tools": tools,
            "messages": messages,
        }

    async def stream(self, *, system: str, tools: list[dict], messages: list[dict]
                     ) -> AsyncIterator[Event]:
        kwargs = self.request(system, tools, messages)
        for attempt in range(MAX_JSON_RETRIES + 1):
            emitted = False
            try:
                async with self.client.beta.messages.stream(**kwargs) as stream:
                    async for event in stream:
                        if event.type != "content_block_delta":
                            continue
                        if event.delta.type == "text_delta":
                            emitted = True
                            yield ("text", event.delta.text)
                        elif event.delta.type == "thinking_delta" and event.delta.thinking:
                            emitted = True
                            yield ("progress", event.delta.thinking)
                    final = await stream.get_final_message()
                break
            except ValueError:
                # Tool-input JSON the SDK couldn't parse at all (eager input streaming).
                # Re-issue the call, unless text already reached the student
                if emitted or attempt == MAX_JSON_RETRIES:
                    raise
        yield ("final", {
            "content": [b.model_dump(mode="json", exclude_none=True) for b in final.content],
            "stop_reason": final.stop_reason,
            "usage": final.usage.model_dump(mode="json", exclude_none=True),
        })
