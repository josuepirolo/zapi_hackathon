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
from pydantic import BaseModel, Field
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
    # Mensagem de contato novo so inicia consentimento se contiver essa
    # palavra (case-insensitive) - ver app/webhook.py, RN-006. Sem isso,
    # qualquer mensagem de qualquer numero desconhecido virava convite
    # automatico (incidente real 2026-08-13).
    trigger_keyword: str = Field(min_length=1)
    invitation_message: str
    welcome_message: str


class CampaignOut(BaseModel):
    id: int
    name: str
    description: str | None
    whatsapp_group_id: str | None
    trigger_keyword: str
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


@router.post("", response_model=CampaignOut, status_code=201)
async def create_campaign(body: CampaignCreate, session: AsyncSession = Depends(get_session)) -> Campaign:
    # Sem group-create aqui: o grupo so existe quando o primeiro contato
    # real aceita participar - ver app/webhook.py (RN-007). Evita precisar
    # de um "seed_phones" artificial e o erro "participants not found" ao
    # tentar adicionar o proprio numero da instancia como participante.
    campaign = Campaign(
        name=body.name,
        description=body.description,
        trigger_keyword=body.trigger_keyword,
        invitation_message=body.invitation_message,
        welcome_message=body.welcome_message,
    )
    session.add(campaign)
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
