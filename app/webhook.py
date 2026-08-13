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

Criacao lazy do grupo (RN-007): `group-create` do MCP rejeita `phones`
vazio ou so com o proprio numero da instancia (achado ao vivo). Por isso
o grupo nao e criado em `POST /campaigns` - so quando o PRIMEIRO contato
real aceita participar (`intent == ACCEPT`), usando o proprio contato
como participante inicial. Aceites seguintes usam `group-add-participant`
normalmente, ja com `campaign.whatsapp_group_id` preenchido.

Auto-recuperacao de aceite travado (RN-008): nao existe tool MCP para
listar em quais grupos um numero esta (achado da Fase 0) - entao nao da
para confirmar "de fora" se um contato ACCEPTED realmente foi adicionado.
Em vez de assumir que sim (ou pedir correcao manual no banco), qualquer
nova mensagem de um contato `ACCEPTED` com `membership_status=NONE`
tenta de novo criar/adicionar ao grupo automaticamente - cobre tanto
falha transitoria de MCP quanto registros antigos que ficaram
inconsistentes numa versao anterior do codigo.

Reentrada apos remocao (RN-010): contato `REMOVED` (saida voluntaria
#sairgrupozapi ou removido pelo admin) ou `DECLINED` que manda mensagem
com a `trigger_keyword` de novo reinicia o fluxo de consentimento
(PENDING + convite) em vez de ser ignorado.
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
from app.ai import generate_promo_image_base64, interpret_confirmation, interpret_intent
from app.config import WEBHOOK_SHARED_SECRET
from app.db import async_session
from app.models import Campaign, ConsentStatus, Contact, MembershipStatus

logger = logging.getLogger("delega.webhook")

router = APIRouter()

REMOVAL_TRIGGER = "#sairgrupozapi"


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


async def _ensure_group_membership(contact: Contact, campaign: Campaign) -> bool:
    """Garante que `contact` esta no grupo da campanha - cria o grupo se
    for o primeiro membro (RN-007), ou adiciona a um grupo ja existente.
    Retorna True e marca `membership_status=ADDED` só em sucesso confirmado
    (`mcp_client.tool_call_succeeded`) - nunca assume sucesso por não ter
    dado exceção (achado do incidente 2026-08-13: falha de negocio dentro
    de um envelope HTTP 200 tinha passado batido antes).

    Usa `contact.phone` (MSISDN puro) para as tools de GRUPO quando
    disponivel, nao `contact.chat_lid` (formato `@lid`) - `send-text`
    aceita LID no parametro `phone` (documentado), mas `group-create`/
    `group-add-participant` com LID retornaram "participants not found"
    mesmo com um contato real (achado ao vivo 2026-08-13); a correlacao
    interna continua por `chat_lid` (ADR-0001), so o parametro enviado ao
    MCP muda."""
    target_phone = contact.phone or contact.chat_lid

    if campaign.whatsapp_group_id:
        try:
            add_result = await mcp_client.call_tool(
                "group-add-participant",
                {"groupId": campaign.whatsapp_group_id, "phones": [target_phone], "autoInvite": True},
            )
        except Exception:
            logger.exception("Falha ao adicionar %s ao grupo via MCP", contact.chat_lid)
            return False
        if not mcp_client.tool_call_succeeded(add_result):
            logger.warning("group-add-participant recusou %s: %r", contact.chat_lid, add_result)
            return False
        contact.membership_status = MembershipStatus.ADDED
        return True

    # primeiro membro da campanha: cria o grupo agora (RN-007)
    try:
        create_result = await mcp_client.call_tool(
            "group-create",
            {"groupName": campaign.name, "phones": [target_phone], "autoInvite": True},
        )
    except Exception:
        logger.exception("Falha ao criar grupo via MCP para a campanha %s", campaign.id)
        return False
    group_id = mcp_client.extract_group_id(create_result)
    if group_id is None:
        logger.warning("group-create nao retornou groupId utilizavel: %r", create_result)
        return False
    campaign.whatsapp_group_id = group_id
    contact.membership_status = MembershipStatus.ADDED
    return True


async def _send_group_welcome(campaign: Campaign) -> None:
    """Boas-vindas no grupo ao aceitar: imagem gerada por IA em memoria
    (base64) enviada via `send-image` do MCP — nunca hospedada em URL
    publica. Legenda = `welcome_message` da campanha."""
    if not campaign.whatsapp_group_id:
        logger.warning("Campanha %s sem whatsapp_group_id - boas-vindas ao grupo ignorada.", campaign.id)
        return
    image_b64 = await generate_promo_image_base64()
    if image_b64 is None:
        logger.warning("Falha ao gerar imagem de boas-vindas - fallback send-text no grupo.")
        try:
            await mcp_client.call_tool(
                "send-text", {"phone": campaign.whatsapp_group_id, "message": campaign.welcome_message}
            )
        except Exception:
            logger.exception("Falha no fallback de boas-vindas via send-text no grupo %s", campaign.whatsapp_group_id)
        return
    try:
        await mcp_client.call_tool(
            "send-image",
            {
                "phone": campaign.whatsapp_group_id,
                "image": image_b64,
                "caption": campaign.welcome_message,
            },
        )
    except Exception:
        logger.exception("Falha ao enviar imagem de boas-vindas via MCP no grupo %s", campaign.whatsapp_group_id)


async def _retry_stuck_acceptance(session: AsyncSession, contact: Contact, campaign: Campaign) -> None:
    """Contato ja ACCEPTED mas nunca confirmado no grupo (ex.: MCP falhou
    na hora, ou o registro ficou de uma versao anterior do codigo que
    marcava ACCEPTED sem completar a adicao). Qualquer nova mensagem dele
    tenta de novo, em vez de ficar preso pra sempre - sem exigir
    intervencao manual no banco."""
    logger.info("Retentando adicao ao grupo para %s (ACCEPTED, membership_status=NONE).", contact.chat_lid)
    if await _ensure_group_membership(contact, campaign):
        await _send_group_welcome(campaign)
    await session.commit()


async def _start_removal_flow(session: AsyncSession, contact: Contact, campaign: Campaign) -> None:
    """Contato ja ADDED manda `#sairgrupozapi`: pergunta confirmacao antes
    de remover - nunca remove direto de uma unica mensagem (mesmo
    principio do consentimento de entrada: acao destrutiva exige
    confirmacao explicita, RN-004)."""
    contact.removal_pending = True
    try:
        await mcp_client.call_tool(
            "send-text",
            {
                "phone": contact.chat_lid,
                "message": f"Tem certeza que quer sair do grupo {campaign.name}? (responda SIM ou NAO)",
            },
        )
    except Exception:
        logger.exception("Falha ao perguntar confirmacao de saida via MCP para %s", contact.chat_lid)
    await session.commit()


async def _handle_removal_confirmation(session: AsyncSession, contact: Contact, campaign: Campaign, texto: str) -> None:
    confirmation = await interpret_confirmation(texto)

    if confirmation == "YES":
        if not campaign.whatsapp_group_id:
            logger.warning("Confirmacao de saida para campanha %s sem whatsapp_group_id - nada a remover.", campaign.id)
            contact.removal_pending = False
            await session.commit()
            return
        target_phone = contact.phone or contact.chat_lid
        try:
            remove_result = await mcp_client.call_tool(
                "group-remove-participant",
                {"groupId": campaign.whatsapp_group_id, "phones": [target_phone]},
            )
        except Exception:
            logger.exception("Falha ao remover %s do grupo via MCP", contact.chat_lid)
            return  # mantem removal_pending=True, tenta de novo na proxima mensagem
        if not mcp_client.tool_call_succeeded(remove_result):
            logger.warning("group-remove-participant recusou %s: %r", contact.chat_lid, remove_result)
            return
        contact.membership_status = MembershipStatus.REMOVED
        contact.removal_pending = False
        try:
            await mcp_client.call_tool("send-text", {"phone": contact.chat_lid, "message": "Voce foi removido do grupo."})
        except Exception:
            logger.exception("Falha ao confirmar remocao via MCP para %s", contact.chat_lid)

    elif confirmation == "NO":
        contact.removal_pending = False
        try:
            await mcp_client.call_tool(
                "send-text", {"phone": contact.chat_lid, "message": "Combinado, voce continua no grupo."}
            )
        except Exception:
            logger.exception("Falha ao confirmar permanencia via MCP para %s", contact.chat_lid)

    else:  # UNCLEAR
        try:
            await mcp_client.call_tool(
                "send-text",
                {"phone": contact.chat_lid, "message": "Nao entendi. Quer mesmo sair do grupo? (responda SIM ou NAO)"},
            )
        except Exception:
            logger.exception("Falha ao reperguntar confirmacao de saida via MCP para %s", contact.chat_lid)

    await session.commit()


async def _handle_reentry(session: AsyncSession, contact: Contact, campaign: Campaign) -> None:
    """Contato REMOVED ou DECLINED pede entrada de novo via palavra-chave
    (RN-010) — reinicia consentimento do zero, sem reutilizar aceite anterior."""
    logger.info("Reentrada solicitada por %s (consent=%s, membership=%s).", contact.chat_lid, contact.consent_status, contact.membership_status)
    contact.consent_status = ConsentStatus.PENDING
    contact.membership_status = MembershipStatus.NONE
    contact.removal_pending = False
    contact.consent_at = None
    contact.is_admin = False
    try:
        await mcp_client.call_tool("send-text", {"phone": contact.chat_lid, "message": campaign.invitation_message})
    except Exception:
        logger.exception("Falha ao reenviar convite via MCP para %s", contact.chat_lid)
    await session.commit()


async def _handle_pending_contact(session: AsyncSession, contact: Contact, campaign: Campaign, texto: str) -> None:
    intent = await interpret_intent(texto)

    if intent == "ACCEPT":
        if not await _ensure_group_membership(contact, campaign):
            return  # nao avanca consent_status se a adicao/criacao falhar

        contact.consent_status = ConsentStatus.ACCEPTED
        contact.consent_at = datetime.now(timezone.utc)
        await _send_group_welcome(campaign)

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
        elif contact.removal_pending:
            campaign_result = await session.get(Campaign, contact.campaign_id)
            if campaign_result is not None:
                await _handle_removal_confirmation(session, contact, campaign_result, texto)
        elif REMOVAL_TRIGGER in texto.lower() and contact.membership_status == MembershipStatus.ADDED:
            campaign_result = await session.get(Campaign, contact.campaign_id)
            if campaign_result is not None:
                await _start_removal_flow(session, contact, campaign_result)
        elif contact.consent_status == ConsentStatus.PENDING:
            campaign_result = await session.get(Campaign, contact.campaign_id)
            if campaign_result is not None:
                await _handle_pending_contact(session, contact, campaign_result, texto)
        elif contact.consent_status == ConsentStatus.ACCEPTED and contact.membership_status == MembershipStatus.NONE:
            campaign_result = await session.get(Campaign, contact.campaign_id)
            if campaign_result is not None:
                await _retry_stuck_acceptance(session, contact, campaign_result)
        elif (
            contact.membership_status == MembershipStatus.REMOVED or contact.consent_status == ConsentStatus.DECLINED
        ):
            campaign_result = await session.get(Campaign, contact.campaign_id)
            if campaign_result is not None and campaign_result.trigger_keyword.lower() in texto.lower():
                await _handle_reentry(session, contact, campaign_result)
        else:
            logger.info(
                "Mensagem de %s com consent_status=%s/membership_status=%s (fora do fluxo de consentimento) - ignorada.",
                chat_lid,
                contact.consent_status,
                contact.membership_status,
            )

        if message_id:
            contact_after = await _get_contact(session, chat_lid)
            if contact_after is not None:
                contact_after.last_message_id = message_id
                await session.commit()

    return JSONResponse(content={"status": "received"}, status_code=200)
