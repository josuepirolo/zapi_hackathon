"""API do chat publico (pagina /promocoes)."""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat_agent import run_chat_turn
from app.chat_consent import accept_consent_by_token, get_consent_poll_status, normalize_browser_session_id
from app.db import get_session

logger = logging.getLogger("delega.chat_api")

router = APIRouter(prefix="/api", tags=["chat"])


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: list[HistoryMessage] = Field(default_factory=list, max_length=40)
    session_id: str | None = Field(default=None, max_length=64)


class ChatResponse(BaseModel):
    reply: str
    tools_used: list[str]
    consent_status: Literal["none", "waiting", "accepted", "expired"] = "none"
    session_id: str


class ConsentPollResponse(BaseModel):
    status: Literal["none", "pending", "accepted", "expired"]
    tools_used: list[str] = Field(default_factory=list)


class ConsentAcceptResponse(BaseModel):
    ok: bool
    message: str


@router.post("/chat", response_model=ChatResponse)
async def public_chat(body: ChatRequest, session: AsyncSession = Depends(get_session)) -> ChatResponse:
    browser_session_id = normalize_browser_session_id(body.session_id)
    history = [{"role": m.role, "content": m.content} for m in body.history]
    result = await run_chat_turn(session, history, body.message.strip(), browser_session_id)
    status = result.consent_status
    if status not in ("none", "waiting", "accepted", "expired"):
        status = "none"
    return ChatResponse(
        reply=result.reply,
        tools_used=result.tools_used,
        consent_status=status,  # type: ignore[arg-type]
        session_id=browser_session_id,
    )


@router.get("/chat/consent/{session_id}", response_model=ConsentPollResponse)
async def poll_chat_consent(session_id: str, session: AsyncSession = Depends(get_session)) -> ConsentPollResponse:
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
async def accept_chat_consent(token: str, session: AsyncSession = Depends(get_session)) -> ConsentAcceptResponse:
    token = token.strip()
    if not token or len(token) > 128:
        raise HTTPException(status_code=400, detail="Token invalido")
    ok, message = await accept_consent_by_token(session, token)
    return ConsentAcceptResponse(ok=ok, message=message)
