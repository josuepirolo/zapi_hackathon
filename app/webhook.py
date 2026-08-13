"""Webhook `on-message-received` — fluxo de consentimento.

Ver `.sdds/specs/consentimento-grupo.spec.md` secao 11 (fluxos principais)
e `.sdds/contracts/consentimento-grupo.contract.md`.

Reaproveita o padrao de seguranca do `webhook_receiver/app.py` original:
segredo obrigatorio no path (`secrets.compare_digest`, 404 se invalido) e
redacao de headers sensiveis.

Decisao pragmatica (nao coberta explicitamente no plano recuperado): como
o payload do webhook nao identifica a campanha, uma mensagem de um
contato novo (sem `Contact` existente) e associada a campanha mais
recente (`Campaign` com maior `id`). Correto para o cenario de demo
(uma campanha ativa por vez); com multiplas campanhas simultaneas isso
precisaria de outro mecanismo de roteamento - `Ponto em aberto`.
"""

from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import mcp_client
from app.ai import interpret_intent
from app.config import WEBHOOK_SHARED_SECRET
from app.db import async_session
from app.models import Campaign, ConsentStatus, Contact, MembershipStatus

logger = logging.getLogger("delega.webhook")

router = APIRouter()


def _check_secret(secret: str) -> None:
    if not secrets.compare_digest(secret, WEBHOOK_SHARED_SECRET):
        raise HTTPException(status_code=404)


async def _latest_campaign(session: AsyncSession) -> Campaign | None:
    result = await session.execute(select(Campaign).order_by(Campaign.id.desc()).limit(1))
    return result.scalar_one_or_none()


async def _get_contact(session: AsyncSession, chat_lid: str) -> Contact | None:
    result = await session.execute(select(Contact).where(Contact.chat_lid == chat_lid))
    return result.scalar_one_or_none()


async def _handle_new_contact(session: AsyncSession, chat_lid: str, phone: str | None) -> None:
    campaign = await _latest_campaign(session)
    if campaign is None:
        logger.warning("Mensagem de %s recebida sem nenhuma campanha cadastrada - ignorada.", chat_lid)
        return

    contact = Contact(campaign_id=campaign.id, chat_lid=chat_lid, phone=phone, consent_status=ConsentStatus.PENDING)
    session.add(contact)
    await session.flush()

    try:
        await mcp_client.call_tool("send-text", {"phone": chat_lid, "message": campaign.invitation_message})
    except Exception:
        logger.exception("Falha ao enviar convite via MCP para %s", chat_lid)
    await session.commit()


async def _handle_pending_contact(session: AsyncSession, contact: Contact, campaign: Campaign, texto: str) -> None:
    intent = await interpret_intent(texto)

    if intent == "ACCEPT":
        if campaign.whatsapp_group_id:
            try:
                await mcp_client.call_tool(
                    "group-add-participant",
                    {"groupId": campaign.whatsapp_group_id, "phones": [contact.chat_lid], "autoInvite": True},
                )
            except Exception:
                logger.exception("Falha ao adicionar %s ao grupo via MCP", contact.chat_lid)
                return  # nao avanca o estado se a adicao falhar
            contact.membership_status = MembershipStatus.ADDED
        else:
            logger.warning("Campanha %s sem whatsapp_group_id - contato aceito mas nao adicionado.", campaign.id)

        contact.consent_status = ConsentStatus.ACCEPTED
        contact.consent_at = datetime.now(timezone.utc)
        try:
            await mcp_client.call_tool("send-text", {"phone": contact.chat_lid, "message": campaign.welcome_message})
        except Exception:
            logger.exception("Falha ao enviar mensagem de boas-vindas via MCP para %s", contact.chat_lid)

    elif intent == "DECLINE":
        contact.consent_status = ConsentStatus.DECLINED
        contact.consent_at = datetime.now(timezone.utc)
        try:
            await mcp_client.call_tool(
                "send-text",
                {"phone": contact.chat_lid, "message": "Tudo bem! Se mudar de ideia, e so chamar novamente."},
            )
        except Exception:
            logger.exception("Falha ao enviar mensagem de encerramento via MCP para %s", contact.chat_lid)

    else:  # UNCLEAR
        try:
            await mcp_client.call_tool(
                "send-text",
                {
                    "phone": contact.chat_lid,
                    "message": f"Nao entendi. {campaign.invitation_message} (responda SIM ou NAO)",
                },
            )
        except Exception:
            logger.exception("Falha ao reperguntar via MCP para %s", contact.chat_lid)

    await session.commit()


@router.post("/webhooks/zapi/{secret}/on-message-received")
async def on_message_received(secret: str, request: Request) -> JSONResponse:
    _check_secret(secret)
    raw_body = await request.body()
    try:
        payload: dict[str, Any] = json.loads(raw_body)
    except json.JSONDecodeError:
        logger.warning("Payload nao-JSON recebido no webhook, ignorado.")
        return JSONResponse(content={"status": "received"}, status_code=200)

    if payload.get("fromMe"):
        return JSONResponse(content={"status": "received"}, status_code=200)

    chat_lid = payload.get("chatLid")
    if not chat_lid:
        logger.warning("Evento sem chatLid recebido, nao pode ser correlacionado - ignorado. messageId=%s", payload.get("messageId"))
        return JSONResponse(content={"status": "received"}, status_code=200)

    message_id = payload.get("messageId")
    texto = (payload.get("text") or {}).get("message", "")
    phone = payload.get("phone")

    async with async_session() as session:
        contact = await _get_contact(session, chat_lid)

        if contact is not None and message_id and contact.last_message_id == message_id:
            logger.info("messageId %s ja processado para %s - ignorado (idempotencia).", message_id, chat_lid)
            return JSONResponse(content={"status": "received"}, status_code=200)

        if contact is None:
            await _handle_new_contact(session, chat_lid, phone)
        elif contact.consent_status == ConsentStatus.PENDING:
            campaign_result = await session.get(Campaign, contact.campaign_id)
            if campaign_result is not None:
                await _handle_pending_contact(session, contact, campaign_result, texto)
        else:
            logger.info(
                "Mensagem de %s com consent_status=%s (fora do fluxo de consentimento) - ignorada.",
                chat_lid,
                contact.consent_status,
            )

        if message_id:
            contact_after = await _get_contact(session, chat_lid)
            if contact_after is not None:
                contact_after.last_message_id = message_id
                await session.commit()

    return JSONResponse(content={"status": "received"}, status_code=200)
