"""
Tutor endpoints (D-56 to D-58).

    GET  /tutor/status   is the tutor on? (the UI hides it when it isn't)
    POST /tutor/session  passcode + case -> signed session token
    POST /tutor/commit   the student's read -> token with the answer tools unlocked
    POST /tutor/chat     token + history + message -> server-sent events

Chat streams JSON events: text and progress deltas, tool calls with their source
labels, notices, and a closing "done" event carrying the messages for the client
to append to its history and the next session token.
"""
import json
from collections.abc import AsyncIterator

import anthropic
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from src.api.routes import cases
from src.ml.inference.predictor import get_predictor
from src.ml.labels import SUPERCLASSES
from src.tutor import limits
from src.tutor import session as sessions
from src.tutor.chat import BadHistoryError, check_history, run_turn
from src.tutor.llm import Model, TutorModel
from src.tutor.tools import ToolBox

router = APIRouter(prefix="/tutor")

_toolbox: ToolBox | None = None
_model: Model | None = None


def toolbox() -> ToolBox:
    global _toolbox
    bank = cases.bank()  # 503 if the bank isn't loaded
    if _toolbox is None or _toolbox.bank is not bank:
        predictor = get_predictor()
        if not predictor.meta:
            raise HTTPException(503, "The served model has no metadata; the tutor needs it")
        _toolbox = ToolBox(bank, predictor, predictor.meta)
    return _toolbox


def model() -> Model:
    global _model
    if _model is None:
        _model = TutorModel()
    return _model


def require_enabled() -> None:
    if not limits.enabled():
        raise HTTPException(503, "The tutor is switched off on this server")


def verify(token: str) -> sessions.Session:
    try:
        return sessions.verify(token)
    except sessions.InvalidSessionError as e:
        raise HTTPException(401, str(e))


def client_id(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    return forwarded.split(",")[0].strip() if forwarded else (request.client or ("?",))[0]


class SessionRequest(BaseModel):
    case_id: str
    passcode: str


class CommitRequest(BaseModel):
    token: str
    answer: list[str] = Field(default_factory=list, max_length=len(SUPERCLASSES))

    @field_validator("answer")
    @classmethod
    def known_classes(cls, v: list[str]) -> list[str]:
        unknown = set(v) - set(SUPERCLASSES)
        if unknown:
            raise ValueError(f"Unknown classes {sorted(unknown)}")
        return v


class ChatRequest(BaseModel):
    token: str
    history: list[dict] = Field(default_factory=list)
    message: str = Field(min_length=1, max_length=2000)


class TokenResponse(BaseModel):
    token: str
    case_id: str
    phase: str


def token_response(s: sessions.Session) -> TokenResponse:
    return TokenResponse(token=sessions.sign(s), case_id=s.case_id, phase=s.phase)


@router.get("/status")
async def status() -> dict:
    return {"enabled": limits.enabled()}


@router.post("/session", response_model=TokenResponse)
async def start_session(body: SessionRequest) -> TokenResponse:
    require_enabled()
    try:
        limits.check_passcode(body.passcode)
    except limits.LimitError as e:
        raise HTTPException(e.status, str(e))
    cases.case(body.case_id)  # 404 for an unknown case
    return token_response(sessions.Session(case_id=body.case_id))


@router.post("/commit", response_model=TokenResponse)
async def commit(body: CommitRequest) -> TokenResponse:
    require_enabled()
    try:
        return token_response(verify(body.token).commit(body.answer))
    except ValueError as e:
        raise HTTPException(409, str(e))


def sse(event: dict) -> str:
    return f"data: {json.dumps(event, separators=(',', ':'))}\n\n"


@router.post("/chat")
async def chat(body: ChatRequest, request: Request) -> StreamingResponse:
    require_enabled()
    s = verify(body.token)
    try:
        if s.turns >= limits.max_turns():
            raise limits.LimitError(429, "This session has reached its message limit; "
                                         "start a new case")
        limits.rate_limiter.check(client_id(request))
        limits.budget.check()
        history = check_history(body.history, s)
    except limits.LimitError as e:
        raise HTTPException(e.status, str(e))
    except BadHistoryError as e:
        raise HTTPException(400, str(e))
    tb, m = toolbox(), model()

    async def events() -> AsyncIterator[str]:
        try:
            async for event in run_turn(m, tb, s, history, body.message):
                if event["type"] == "done":
                    cost = limits.budget.record(event["usage"])
                    event = {**event, "token": sessions.sign(s.next_turn()),
                             "cost_usd": round(cost, 4)}
                yield sse(event)
        except anthropic.APIError as e:
            print(f"⚠️  Tutor model call failed: {e!r}")
            yield sse({"type": "error", "message": "The tutor is unavailable right now; "
                                                   "try again shortly."})

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
