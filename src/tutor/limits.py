"""
Spend and abuse controls for the tutor (D-58).

The API is public (D-22), so the chat endpoint is what could run up an LLM bill.
Every control is a hard stop, not an alert:
- CHAT_ENABLED kill switch, off unless explicitly turned on
- a demo passcode to start a session
- per-session turn cap (carried in the signed token) and per-client rate limit
- a daily spend budget, estimated from token usage at conservative prices
The provider-side monthly spend limit (set in the Anthropic Console) is the backstop.

Counters are in-process: the demo runs one API replica. With more replicas each
would get its own budget, so lower TUTOR_DAILY_BUDGET_USD accordingly.
"""
import hmac
import os
import time
from collections import defaultdict, deque
from datetime import UTC, datetime

# Conservative $/MTok: Opus 5.5 is $4/$20, but a refusal fallback may run on Opus 4.8
# ($5/$25), so price everything at the higher rates
PRICE_PER_MTOK = {
    "input_tokens": 5.0,
    "cache_creation_input_tokens": 6.25,
    "cache_read_input_tokens": 0.50,
    "output_tokens": 25.0,
}


class LimitError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def enabled() -> bool:
    return os.getenv("CHAT_ENABLED", "false").lower() == "true"


def check_passcode(given: str) -> None:
    expected = os.getenv("TUTOR_PASSCODE")
    if not expected:
        raise LimitError(503, "The tutor isn't configured on this server")
    if not hmac.compare_digest(given.encode(), expected.encode()):
        raise LimitError(403, "Wrong passcode")


def max_turns() -> int:
    return int(os.getenv("TUTOR_MAX_TURNS", "30"))


def cost_usd(usage: dict[str, int]) -> float:
    return sum(usage.get(k, 0) * price for k, price in PRICE_PER_MTOK.items()) / 1e6


class RateLimiter:
    """Sliding window: at most `limit` turns per `window_s` seconds per client."""

    def __init__(self, limit: int = 10, window_s: float = 60.0):
        self.limit, self.window_s = limit, window_s
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, client: str, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        hits = self.hits[client]
        while hits and now - hits[0] > self.window_s:
            hits.popleft()
        if len(hits) >= self.limit:
            raise LimitError(429, "Too many messages; wait a minute")
        hits.append(now)


class DailyBudget:
    def __init__(self):
        self.day = ""
        self.spent_usd = 0.0

    def limit_usd(self) -> float:
        return float(os.getenv("TUTOR_DAILY_BUDGET_USD", "3.0"))

    def _roll(self) -> None:
        today = datetime.now(UTC).date().isoformat()
        if today != self.day:
            self.day, self.spent_usd = today, 0.0

    def check(self) -> None:
        self._roll()
        if self.spent_usd >= self.limit_usd():
            raise LimitError(429, "The tutor's daily budget is used up; try again tomorrow")

    def record(self, usage: dict[str, int]) -> float:
        self._roll()
        cost = cost_usd(usage)
        self.spent_usd += cost
        return cost


rate_limiter = RateLimiter()
budget = DailyBudget()
