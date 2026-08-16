"""API do chat publico (pagina /promocoes)."""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat_agent import run_chat_turn
from app.chat_consent import (
    accept_consent_by_token,
    get_consent_poll_status,
    is_human_verified,
    mark_human_verified,
    normalize_browser_session_id,
)
from app.config import (
    CHAT_ACCEPT_RATE_LIMIT_PER_MINUTE,
    CHAT_POLL_RATE_LIMIT_PER_MINUTE,
    CHAT_RATE_LIMIT_PER_MINUTE,
    TURNSTILE_ENABLED,
    TURNSTILE_SITE_KEY,
)
from app.db import get_session
from app.phone_mask import mask_phones_in_text
from app.rate_limit import allow
from app.turnstile import verify_turnstile

logger = logging.getLogger("delega.chat_api")

router = APIRouter(prefix="/api", tags=["chat"])


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _rate_limit_or_429(request: Request, bucket: str, max_calls: int, window_seconds: int = 60) -> None:
    ip = _client_ip(request)
    if not allow(f"{bucket}:{ip}", max_calls=max_calls, window_seconds=window_seconds):
        raise HTTPException(status_code=429, detail="Muitas requisicoes. Aguarde um minuto e tente de novo.")


async def _verify_turnstile_token(request: Request, turnstile_token: str | None) -> None:
    if not await verify_turnstile(turnstile_token, _client_ip(request)):
        raise HTTPException(status_code=403, detail="Verificacao anti-bot falhou. Recarregue a pagina e tente de novo.")


async def _require_human_session(db: AsyncSession, browser_session_id: str) -> None:
    if not TURNSTILE_ENABLED:
        return
    if not await is_human_verified(db, browser_session_id):
        raise HTTPException(
            status_code=403,
            detail="Complete a verificacao anti-bot no chat antes de enviar mensagens.",
        )


class ChatPublicConfig(BaseModel):
    turnstile_enabled: bool
    turnstile_site_key: str | None = None


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: list[HistoryMessage] = Field(default_factory=list, max_length=40)
    session_id: str | None = Field(default=None, max_length=64)


class VerifyHumanRequest(BaseModel):
    session_id: str | None = Field(default=None, max_length=64)
    turnstile_token: str = Field(min_length=1, max_length=4096)


class VerifyHumanResponse(BaseModel):
    ok: bool
    session_id: str


class HumanStatusResponse(BaseModel):
    verified: bool
    session_id: str


class ChatResponse(BaseModel):
    reply: str
    tools_used: list[str]
    consent_status: Literal["none", "waiting", "accepted", "expired"] = "none"
    session_id: str


class ConsentPollResponse(BaseModel):
    status: Literal["none", "pending", "accepted", "expired"]
    tools_used: list[str] = Field(default_factory=list)


class ConsentAcceptRequest(BaseModel):
    turnstile_token: str | None = Field(default=None, max_length=4096)


class ConsentAcceptResponse(BaseModel):
    ok: bool
    message: str


@router.get("/chat/config", response_model=ChatPublicConfig)
async def chat_public_config() -> ChatPublicConfig:
    return ChatPublicConfig(
        turnstile_enabled=TURNSTILE_ENABLED,
        turnstile_site_key=TURNSTILE_SITE_KEY if TURNSTILE_ENABLED else None,
    )


@router.get("/chat/human/{session_id}", response_model=HumanStatusResponse)
async def human_verification_status(
    session_id: str,
    session: AsyncSession = Depends(get_session),
) -> HumanStatusResponse:
    browser_session_id = normalize_browser_session_id(session_id)
    verified = await is_human_verified(session, browser_session_id) if TURNSTILE_ENABLED else True
    return HumanStatusResponse(verified=verified, session_id=browser_session_id)


@router.post("/chat/verify-human", response_model=VerifyHumanResponse)
async def verify_human_once(
    body: VerifyHumanRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> VerifyHumanResponse:
    _rate_limit_or_429(request, "chat_verify_human", 10)
    if not TURNSTILE_ENABLED:
        browser_session_id = normalize_browser_session_id(body.session_id)
        return VerifyHumanResponse(ok=True, session_id=browser_session_id)

    await _verify_turnstile_token(request, body.turnstile_token)
    browser_session_id = normalize_browser_session_id(body.session_id)
    await mark_human_verified(session, browser_session_id)
    return VerifyHumanResponse(ok=True, session_id=browser_session_id)


@router.post("/chat", response_model=ChatResponse)
async def public_chat(
    body: ChatRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> ChatResponse:
    _rate_limit_or_429(request, "chat_post", CHAT_RATE_LIMIT_PER_MINUTE)
    browser_session_id = normalize_browser_session_id(body.session_id)
    await _require_human_session(session, browser_session_id)

    history = [{"role": m.role, "content": m.content} for m in body.history]
    result = await run_chat_turn(session, history, body.message.strip(), browser_session_id)
    status = result.consent_status
    if status not in ("none", "waiting", "accepted", "expired"):
        status = "none"
    return ChatResponse(
        reply=mask_phones_in_text(result.reply),
        tools_used=result.tools_used,
        consent_status=status,  # type: ignore[arg-type]
        session_id=browser_session_id,
    )


@router.get("/chat/consent/{session_id}", response_model=ConsentPollResponse)
async def poll_chat_consent(
    session_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> ConsentPollResponse:
    _rate_limit_or_429(request, "chat_poll", CHAT_POLL_RATE_LIMIT_PER_MINUTE)
    browser_session_id = normalize_browser_session_id(session_id)
    data = await get_consent_poll_status(session, browser_session_id)
    status = data.get("status", "none")
    if status not in ("none", "pending", "accepted", "expired"):
        status = "none"
    tools = data.get("tools_used")
    return ConsentPollResponse(
        status=status,  # type: ignore[arg-type]
        tools_used=list(tools) if isinstance(tools, list) else [],
    )


@router.post("/chat/consent/accept/{token}", response_model=ConsentAcceptResponse)
async def accept_chat_consent(
    token: str,
    request: Request,
    body: ConsentAcceptRequest = ConsentAcceptRequest(),
    session: AsyncSession = Depends(get_session),
) -> ConsentAcceptResponse:
    _rate_limit_or_429(request, "chat_accept", CHAT_ACCEPT_RATE_LIMIT_PER_MINUTE)
    await _verify_turnstile_token(request, body.turnstile_token)

    token = token.strip()
    if not token or len(token) > 128:
        raise HTTPException(status_code=400, detail="Token invalido")
    ok, message = await accept_consent_by_token(session, token)
    return ConsentAcceptResponse(ok=ok, message=message)
