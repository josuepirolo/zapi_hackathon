"""Webhook `on-message-received` — fluxo de consentimento.

Ver `.sdds/specs/consentimento-grupo.spec.md` secao 11 (fluxos principais)
e `.sdds/contracts/consentimento-grupo.contract.md`.

Reaproveita o padrao de seguranca do `webhook_receiver/app.py` original:
segredo obrigatorio no path (`secrets.compare_digest`, 404 se invalido) e
redacao de headers sensiveis.

Correlacao de campanha por palavra-chave (RN-006, incidente real
2026-08-13): o payload do webhook nao identifica a campanha, e a versao
anterior tratava QUALQUER mensagem de QUALQUER numero desconhecido como
"quer entrar" e mandava convite automatico - isso enviou mensagens nao
solicitadas para contatos sem relacao com o hackathon assim que uma
mensagem real chegou num numero ja usado para outros fins. Corrigido:
uma mensagem de contato novo so inicia o fluxo de consentimento se
contiver a `trigger_keyword` de alguma campanha (case-insensitive,
substring). Sem match: mensagem e completamente ignorada (sem Contact
criado, sem resposta enviada).
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


async def _match_campaign_by_keyword(session: AsyncSession, texto: str) -> Campaign | None:
    result = await session.execute(select(Campaign).order_by(Campaign.id.desc()))
    texto_lower = texto.lower()
    matches = [c for c in result.scalars().all() if c.trigger_keyword and c.trigger_keyword.lower() in texto_lower]
    if not matches:
        return None
    if len(matches) > 1:
        logger.warning(
            "Mensagem bateu com %d campanhas por palavra-chave (%s) - usando a mais recente.",
            len(matches),
            [c.id for c in matches],
        )
    return matches[0]


async def _get_contact(session: AsyncSession, chat_lid: str) -> Contact | None:
    result = await session.execute(select(Contact).where(Contact.chat_lid == chat_lid))
    return result.scalar_one_or_none()


async def _handle_new_contact(session: AsyncSession, chat_lid: str, phone: str | None, texto: str) -> None:
    campaign = await _match_campaign_by_keyword(session, texto)
    if campaign is None:
        logger.info(
            "Mensagem de %s nao contem palavra-chave de nenhuma campanha - ignorada (sem Contact, sem resposta).",
            chat_lid,
        )
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
                add_result = await mcp_client.call_tool(
                    "group-add-participant",
                    {"groupId": campaign.whatsapp_group_id, "phones": [contact.chat_lid], "autoInvite": True},
                )
            except Exception:
                logger.exception("Falha ao adicionar %s ao grupo via MCP", contact.chat_lid)
                return  # nao avanca o estado se a adicao falhar
            if not mcp_client.tool_call_succeeded(add_result):
                logger.warning("group-add-participant recusou %s: %r", contact.chat_lid, add_result)
                return  # idem - falha de negocio, nao de transporte
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
            await _handle_new_contact(session, chat_lid, phone, texto)
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
