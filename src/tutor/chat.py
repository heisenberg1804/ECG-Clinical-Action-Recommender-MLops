"""
One tutor turn: the student's message in, a streamed reply out (D-56, D-57).

The client keeps the conversation and sends it back each turn. The server
checks it, appends the student's message (and, once, the operator note that the
read is committed), then runs the model-tool loop. Messages are only ever
appended, never edited, so the cached prefix and replayed thinking stay valid.
"""
import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from src.tutor.llm import Model
from src.tutor.prompt import SYSTEM, commit_notice
from src.tutor.session import COMMITTED, Session
from src.tutor.tools import ToolBox

MAX_TOOL_ROUNDS = 6  # model calls that use tools, per student turn
MAX_HISTORY_BYTES = 400_000
MAX_HISTORY_MESSAGES = 400

DECLINED = ("The tutor couldn't answer that one. Try rephrasing, or ask about the tracing "
            "itself.")
TRUNCATED = "The reply was cut off before it finished. Ask again, perhaps more narrowly."


class BadHistoryError(ValueError):
    """The conversation sent by the client isn't one this server could have produced."""


@dataclass
class Usage:
    input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    output_tokens: int = 0

    def add(self, usage: dict[str, Any]) -> None:
        for k in vars(self):
            setattr(self, k, getattr(self, k) + int(usage.get(k) or 0))


def check_history(history: Any, session: Session) -> list[dict]:
    """Structural checks on the client's copy of the conversation."""
    if not isinstance(history, list) or len(history) > MAX_HISTORY_MESSAGES:
        raise BadHistoryError("history must be a list of at most "
                              f"{MAX_HISTORY_MESSAGES} messages")
    if len(json.dumps(history)) > MAX_HISTORY_BYTES:
        raise BadHistoryError("history is too long; start a new session")
    notice = commit_notice(session)
    for i, msg in enumerate(history):
        if not isinstance(msg, dict) or msg.get("role") not in ("user", "assistant", "system"):
            raise BadHistoryError(f"message {i}: role must be user, assistant or system")
        if msg["role"] == "system" and (session.phase != COMMITTED or msg.get("content") != notice):
            # Only this server writes operator notes; a forged one could fake a commit
            raise BadHistoryError(f"message {i}: unexpected system message")
        if not isinstance(msg.get("content"), str | list):
            raise BadHistoryError(f"message {i}: content must be a string or a list of blocks")
    if history and history[0]["role"] != "user":
        raise BadHistoryError("history must start with a user message")
    return history


def new_messages(history: list[dict], session: Session, text: str) -> list[dict]:
    msgs = [{"role": "user", "content": [{"type": "text", "text": text}]}]
    if session.phase == COMMITTED and not any(m["role"] == "system" for m in history):
        msgs.append({"role": "system", "content": commit_notice(session)})
    return msgs


async def run_turn(model: Model, toolbox: ToolBox, session: Session, history: list[dict],
                   text: str) -> AsyncIterator[dict[str, Any]]:
    """
    Yield UI events: {"type": "text" | "progress", "text"}, {"type": "tool", ...},
    {"type": "notice", "text"}, and finally {"type": "done", "append", "usage"},
    where `append` is what the client adds to its history.
    """
    appended = new_messages(history, session, text)
    usage = Usage()
    tools = toolbox.schemas()
    # One more call after the limit, so the model can answer with what it has
    for round_no in range(MAX_TOOL_ROUNDS + 2):
        final = None
        async for kind, payload in model.stream(system=SYSTEM, tools=tools,
                                                messages=history + appended):
            if kind == "final":
                final = payload
            else:
                yield {"type": kind, "text": payload}
        usage.add(final["usage"])
        stop, content = final["stop_reason"], final["content"]
        tool_uses = [b for b in content if b.get("type") == "tool_use"]

        if stop == "refusal":
            # Fallbacks already retried server-side; keep the history valid and move on
            if content and not tool_uses:
                appended.append({"role": "assistant", "content": content})
            yield {"type": "notice", "text": DECLINED}
            break
        if stop == "max_tokens":
            # A truncated tool call would parse as a valid partial input: never run it,
            # and drop the turn, since a tool_use without its result breaks the history
            if content and not tool_uses:
                appended.append({"role": "assistant", "content": content})
            yield {"type": "notice", "text": TRUNCATED}
            break
        appended.append({"role": "assistant", "content": content})
        if stop != "tool_use" or not tool_uses:
            break

        results = []
        for block in tool_uses:
            if round_no >= MAX_TOOL_ROUNDS:
                result_text, is_error, source = json.dumps(
                    {"error": "tool_limit", "message": "No more tool calls this turn. Answer "
                     "with what you have."}), True, "Tool limit"
            else:
                r = await asyncio.to_thread(toolbox.run, block["name"], block.get("input"),
                                            session)
                result_text, is_error, source = r.as_text(), r.is_error, r.source
            yield {"type": "tool", "name": block["name"], "source": source,
                   "is_error": is_error}
            results.append({"type": "tool_result", "tool_use_id": block["id"],
                            "content": result_text, **({"is_error": True} if is_error else {})})
        appended.append({"role": "user", "content": results})
    yield {"type": "done", "append": without_stranded_notice(appended), "usage": vars(usage)}


def without_stranded_notice(msgs: list[dict]) -> list[dict]:
    """A system message must be followed by an assistant turn. If the turn ended without
    one (a refusal or a truncated tool call), leave the notice out; the next turn adds it."""
    return [m for i, m in enumerate(msgs)
            if m["role"] != "system" or (i + 1 < len(msgs) and msgs[i + 1]["role"] == "assistant")]
