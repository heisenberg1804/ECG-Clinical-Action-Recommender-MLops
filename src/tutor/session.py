"""
Signed tutor session state (D-57).

The server stays stateless: a session's case, phase and committed answer travel
in an HMAC-signed token that the client sends back every turn. Tools that would
reveal the answer are gated on the phase in the token, so editing the client's
copy of the conversation can't unlock them early.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import asdict, dataclass, field, replace

READING = "reading"  # the student is reading the ECG; nothing about the answer is available
COMMITTED = "committed"  # the student committed a read; reveal tools are unlocked
PHASES = (READING, COMMITTED)

TOKEN_TTL_S = 4 * 3600  # a demo session, not a login


class InvalidSessionError(Exception):
    """The token is malformed, expired, or wasn't signed by this server."""


@dataclass(frozen=True)
class Session:
    case_id: str
    phase: str = READING
    answer: tuple[str, ...] = ()  # the student's committed read
    turns: int = 0
    session_id: str = field(default_factory=lambda: secrets.token_hex(8))
    issued_at: int = field(default_factory=lambda: int(time.time()))

    def commit(self, answer: list[str]) -> "Session":
        if self.phase != READING:
            raise ValueError("This session's read is already committed")
        return replace(self, phase=COMMITTED, answer=tuple(answer))

    def next_turn(self) -> "Session":
        return replace(self, turns=self.turns + 1)


def _secret() -> bytes:
    secret = os.getenv("TUTOR_SESSION_SECRET")
    if not secret:
        raise RuntimeError("TUTOR_SESSION_SECRET is not set")
    return secret.encode()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def sign(session: Session) -> str:
    payload = _b64(json.dumps(asdict(session), sort_keys=True, separators=(",", ":")).encode())
    mac = hmac.new(_secret(), payload.encode(), hashlib.sha256).digest()
    return f"{payload}.{_b64(mac)}"


def verify(token: str, now: float | None = None) -> Session:
    try:
        payload, mac = token.split(".")
        expected = hmac.new(_secret(), payload.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _unb64(mac)):
            raise InvalidSessionError("Bad signature")
        data = json.loads(_unb64(payload))
        session = Session(**{**data, "answer": tuple(data["answer"])})
    except InvalidSessionError:
        raise
    except (ValueError, TypeError, KeyError) as e:
        raise InvalidSessionError(f"Malformed session token: {e}") from e
    if session.phase not in PHASES:
        raise InvalidSessionError(f"Unknown phase {session.phase!r}")
    if (now or time.time()) - session.issued_at > TOKEN_TTL_S:
        raise InvalidSessionError("Session expired; start a new one")
    return session
