"""Admin API: campanhas, participantes e conteudo.

Ver `.sdds/specs/consentimento-grupo.spec.md` secao 2 e
`.sdds/contracts/consentimento-grupo.contract.md`.

Sem autenticacao neste vertical slice (Ponto em aberto na spec, secao 14)
- aceitavel para demo controlada do hackathon, nao para producao real.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import mcp_client
from app.db import get_session
from app.models import Campaign, Contact

logger = logging.getLogger("delega.admin_api")

router = APIRouter(prefix="/campaigns", tags=["admin"])


class CampaignCreate(BaseModel):
    name: str
    description: str | None = None
    invitation_message: str
    welcome_message: str


class CampaignOut(BaseModel):
    id: int
    name: str
    description: str | None
    whatsapp_group_id: str | None
    invitation_message: str
    welcome_message: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ContactOut(BaseModel):
    id: int
    chat_lid: str
    phone: str | None
    name: str | None
    consent_status: str
    membership_status: str

    model_config = {"from_attributes": True}


class ContentCreate(BaseModel):
    kind: Literal["text"]
    text: str


def _extract_group_id(mcp_result: dict) -> str | None:
    """`group-create` ainda nao teve o schema de retorno confirmado ao vivo
    (ver docs/zapi-mcp-capabilities.md). Tenta as chaves mais prováveis;
    se nenhuma bater, loga o retorno bruto para inspecao manual."""
    content = mcp_result.get("content") if isinstance(mcp_result, dict) else None
    candidates: list[dict] = [mcp_result] if isinstance(mcp_result, dict) else []
    if isinstance(content, list):
        candidates.extend(c for c in content if isinstance(c, dict))
    for candidate in candidates:
        for key in ("groupId", "id", "phone"):
            value = candidate.get(key)
            if value:
                return str(value)
    logger.warning("Nao foi possivel extrair groupId do retorno de group-create: %r", mcp_result)
    return None


@router.post("", response_model=CampaignOut, status_code=201)
async def create_campaign(body: CampaignCreate, session: AsyncSession = Depends(get_session)) -> Campaign:
    campaign = Campaign(
        name=body.name,
        description=body.description,
        invitation_message=body.invitation_message,
        welcome_message=body.welcome_message,
    )
    session.add(campaign)
    await session.flush()

    try:
        result = await mcp_client.call_tool(
            "group-create", {"groupName": body.name, "phones": [], "autoInvite": True}
        )
        campaign.whatsapp_group_id = _extract_group_id(result)
    except Exception:
        logger.exception("Falha ao criar grupo via MCP para a campanha %s", campaign.id)

    await session.commit()
    await session.refresh(campaign)
    return campaign


@router.get("/{campaign_id}/contacts", response_model=list[ContactOut])
async def list_contacts(campaign_id: int, session: AsyncSession = Depends(get_session)) -> list[Contact]:
    result = await session.execute(select(Contact).where(Contact.campaign_id == campaign_id))
    return list(result.scalars().all())


@router.post("/{campaign_id}/content", status_code=202)
async def send_content(campaign_id: int, body: ContentCreate, session: AsyncSession = Depends(get_session)) -> dict:
    campaign = await session.get(Campaign, campaign_id)
    if campaign is None or campaign.whatsapp_group_id is None:
        raise HTTPException(status_code=404, detail="Campanha ou grupo nao encontrado")

    result = await mcp_client.call_tool("send-text", {"phone": campaign.whatsapp_group_id, "message": body.text})
    return {"status": "sent", "mcp_result": result}
