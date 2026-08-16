"""API do chat publico (pagina /promocoes)."""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat_agent import run_chat_turn
from app.db import get_session

logger = logging.getLogger("delega.chat_api")

router = APIRouter(prefix="/api", tags=["chat"])


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: list[HistoryMessage] = Field(default_factory=list, max_length=40)


class ChatResponse(BaseModel):
    reply: str
    tools_used: list[str]


@router.post("/chat", response_model=ChatResponse)
async def public_chat(body: ChatRequest, session: AsyncSession = Depends(get_session)) -> ChatResponse:
    history = [{"role": m.role, "content": m.content} for m in body.history]
    reply, tools_used = await run_chat_turn(session, history, body.message.strip())
    return ChatResponse(reply=reply, tools_used=tools_used)
