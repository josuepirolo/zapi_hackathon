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

from app import ai, mcp_client
from app.db import get_session
from app.models import Campaign, Contact, MembershipStatus

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
    removal_pending: bool
    is_admin: bool

    model_config = {"from_attributes": True}


class ContentCreate(BaseModel):
    kind: Literal["text", "ai_image"]
    # Obrigatorio se kind == "text". Ignorado se kind == "ai_image" - o
    # prompt da imagem e fixo (app.ai._PROMO_IMAGE_PROMPT), nao vem do
    # usuario (evita prompt injection na geracao de imagem).
    text: str | None = None


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


@router.get("", response_model=list[CampaignOut])
async def list_campaigns(session: AsyncSession = Depends(get_session)) -> list[Campaign]:
    result = await session.execute(select(Campaign).order_by(Campaign.id.desc()))
    return list(result.scalars().all())


@router.get("/{campaign_id}/contacts", response_model=list[ContactOut])
async def list_contacts(campaign_id: int, session: AsyncSession = Depends(get_session)) -> list[Contact]:
    result = await session.execute(select(Contact).where(Contact.campaign_id == campaign_id))
    return list(result.scalars().all())


@router.post("/{campaign_id}/content", status_code=202)
async def send_content(campaign_id: int, body: ContentCreate, session: AsyncSession = Depends(get_session)) -> dict:
    campaign = await session.get(Campaign, campaign_id)
    if campaign is None or campaign.whatsapp_group_id is None:
        raise HTTPException(status_code=404, detail="Campanha ou grupo nao encontrado")

    if body.kind == "ai_image":
        image_b64 = await ai.generate_promo_image_base64()
        if image_b64 is None:
            raise HTTPException(status_code=502, detail="Falha ao gerar imagem via OpenAI")
        result = await mcp_client.call_tool(
            "send-image", {"phone": campaign.whatsapp_group_id, "image": image_b64, "caption": body.text or ""}
        )
    else:
        if not body.text:
            raise HTTPException(status_code=422, detail="text e obrigatorio para kind='text'")
        result = await mcp_client.call_tool("send-text", {"phone": campaign.whatsapp_group_id, "message": body.text})

    return {"status": "sent", "mcp_result": result}


@router.delete("/{campaign_id}", status_code=204)
async def delete_campaign(campaign_id: int, session: AsyncSession = Depends(get_session)) -> None:
    """Apaga o registro da campanha e seus contatos - so o nosso rastreio,
    nunca chama o MCP (nao existe tool pra apagar o grupo em si, ver
    docs/zapi-mcp-capabilities.md). O grupo real no WhatsApp, se existir,
    fica intacto/abandonado; a proxima campanha cria um grupo novo."""
    campaign = await session.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campanha nao encontrada")
    result = await session.execute(select(Contact).where(Contact.campaign_id == campaign_id))
    for contact in result.scalars().all():
        await session.delete(contact)
    await session.delete(campaign)
    await session.commit()


async def _get_contact_in_campaign(session: AsyncSession, campaign_id: int, contact_id: int) -> Contact:
    contact = await session.get(Contact, contact_id)
    if contact is None or contact.campaign_id != campaign_id:
        raise HTTPException(status_code=404, detail="Contato nao encontrado nesta campanha")
    return contact


@router.post("/{campaign_id}/contacts/{contact_id}/remove", response_model=ContactOut)
async def remove_contact(
    campaign_id: int, contact_id: int, session: AsyncSession = Depends(get_session)
) -> Contact:
    """Remocao disparada pelo admin - equivalente ao YES do fluxo
    #sairgrupozapi (app/webhook.py), so que iniciada pelo painel em vez de
    pelo proprio contato."""
    contact = await _get_contact_in_campaign(session, campaign_id, contact_id)
    campaign = await session.get(Campaign, campaign_id)
    if campaign is None or not campaign.whatsapp_group_id:
        raise HTTPException(status_code=404, detail="Campanha sem grupo")
    if contact.membership_status != MembershipStatus.ADDED:
        raise HTTPException(status_code=409, detail="Contato nao esta no grupo")

    target_phone = contact.phone or contact.chat_lid
    result = await mcp_client.call_tool(
        "group-remove-participant", {"groupId": campaign.whatsapp_group_id, "phones": [target_phone]}
    )
    if not mcp_client.tool_call_succeeded(result):
        raise HTTPException(status_code=502, detail=f"MCP recusou a remocao: {result}")

    contact.membership_status = MembershipStatus.REMOVED
    contact.is_admin = False
    await session.commit()
    await session.refresh(contact)
    return contact


@router.post("/{campaign_id}/contacts/{contact_id}/promote", response_model=ContactOut)
async def promote_contact(
    campaign_id: int, contact_id: int, session: AsyncSession = Depends(get_session)
) -> Contact:
    contact = await _get_contact_in_campaign(session, campaign_id, contact_id)
    campaign = await session.get(Campaign, campaign_id)
    if campaign is None or not campaign.whatsapp_group_id:
        raise HTTPException(status_code=404, detail="Campanha sem grupo")
    if contact.membership_status != MembershipStatus.ADDED:
        raise HTTPException(status_code=409, detail="Contato precisa estar no grupo pra virar admin")

    target_phone = contact.phone or contact.chat_lid
    result = await mcp_client.call_tool(
        "group-add-admin", {"groupId": campaign.whatsapp_group_id, "phones": [target_phone]}
    )
    if not mcp_client.tool_call_succeeded(result):
        raise HTTPException(status_code=502, detail=f"MCP recusou a promocao: {result}")

    contact.is_admin = True
    await session.commit()
    await session.refresh(contact)
    return contact


@router.post("/{campaign_id}/contacts/{contact_id}/demote", response_model=ContactOut)
async def demote_contact(
    campaign_id: int, contact_id: int, session: AsyncSession = Depends(get_session)
) -> Contact:
    contact = await _get_contact_in_campaign(session, campaign_id, contact_id)
    campaign = await session.get(Campaign, campaign_id)
    if campaign is None or not campaign.whatsapp_group_id:
        raise HTTPException(status_code=404, detail="Campanha sem grupo")

    target_phone = contact.phone or contact.chat_lid
    result = await mcp_client.call_tool(
        "group-remove-admin", {"groupId": campaign.whatsapp_group_id, "phones": [target_phone]}
    )
    if not mcp_client.tool_call_succeeded(result):
        raise HTTPException(status_code=502, detail=f"MCP recusou a remocao de admin: {result}")

    contact.is_admin = False
    await session.commit()
    await session.refresh(contact)
    return contact
