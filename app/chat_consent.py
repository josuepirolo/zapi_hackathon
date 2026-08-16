"""Consentimento trackeado via link — chat publico /promocoes.

Fluxo: visitante confirma telefone no chat -> send-text com link unico ->
visitante abre link no celular -> polling no browser ate status=accepted ->
group-add/group-create via MCP.

Persistencia em SQLite (mesmo banco); nao precisa Redis pro hackathon.
A sessao do browser e identificada por UUID em localStorage (session_id).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import mcp_client
from app.campaign_defaults import WELCOME_MESSAGE
from app.config import CHAT_HUMAN_VERIFY_TTL_HOURS, CONSENT_LINK_TTL_MINUTES, PUBLIC_BASE_URL
from app.models import Campaign, ChatConsentSession, ChatHumanVerification, ChatLinkStatus
from app.webhook import _lock_campaign, _send_group_welcome

logger = logging.getLogger("delega.chat_consent")

_CONSENT_TTL = timedelta(minutes=CONSENT_LINK_TTL_MINUTES)
_HUMAN_VERIFY_TTL = timedelta(hours=CHAT_HUMAN_VERIFY_TTL_HOURS)


def normalize_browser_session_id(raw: str | None) -> str:
    if not raw:
        return str(uuid.uuid4())
    try:
        return str(uuid.UUID(raw.strip()))
    except ValueError:
        return str(uuid.uuid4())


def confirm_url(token: str) -> str:
    return f"{PUBLIC_BASE_URL}/confirmar/{token}"


def _is_expired(record: ChatConsentSession, now: datetime) -> bool:
    return record.created_at + _CONSENT_TTL < now


async def _expire_if_needed(session: AsyncSession, record: ChatConsentSession, now: datetime) -> ChatConsentSession:
    if record.status == ChatLinkStatus.PENDING and _is_expired(record, now):
        record.status = ChatLinkStatus.EXPIRED
        await session.commit()
    return record


async def _latest_campaign(session: AsyncSession) -> Campaign | None:
    result = await session.execute(select(Campaign).order_by(Campaign.id.desc()).limit(1))
    return result.scalar_one_or_none()


async def _expire_other_pending(
    session: AsyncSession, browser_session_id: str, except_id: int | None = None
) -> None:
    result = await session.execute(
        select(ChatConsentSession).where(
            ChatConsentSession.browser_session_id == browser_session_id,
            ChatConsentSession.status == ChatLinkStatus.PENDING,
        )
    )
    for row in result.scalars().all():
        if except_id is not None and row.id == except_id:
            continue
        row.status = ChatLinkStatus.EXPIRED
    await session.commit()


async def ensure_phone_in_group(session: AsyncSession, campaign: Campaign, phone: str) -> bool:
    """Adiciona MSISDN ao grupo da campanha (mesma logica do webhook, sem Contact)."""
    locked = await _lock_campaign(session, campaign.id)
    if locked is None:
        return False
    campaign = locked

    if campaign.whatsapp_group_id:
        try:
            add_result = await mcp_client.call_tool(
                "group-add-participant",
                {"groupId": campaign.whatsapp_group_id, "phones": [phone], "autoInvite": True},
            )
        except Exception:
            logger.exception("Chat link: falha group-add-participant para %s", phone)
            return False
        if not mcp_client.tool_call_succeeded(add_result):
            logger.warning("Chat link: group-add-participant recusou %s: %r", phone, add_result)
            return False
        return True

    try:
        create_result = await mcp_client.call_tool(
            "group-create",
            {"groupName": campaign.name, "phones": [phone], "autoInvite": True},
        )
    except Exception:
        logger.exception("Chat link: falha group-create campanha %s", campaign.id)
        return False
    group_id = mcp_client.extract_group_id(create_result)
    if group_id is None:
        logger.warning("Chat link: group-create sem groupId: %r", create_result)
        return False
    campaign.whatsapp_group_id = group_id
    await session.flush()
    return True


async def start_tracked_consent(
    session: AsyncSession,
    browser_session_id: str,
    phone: str,
) -> tuple[bool, str, list[str], str]:
    """Cria registro, envia link no WhatsApp. Retorna (ok, reply, tools, consent_status)."""
    campaign = await _latest_campaign(session)
    token = uuid.uuid4().hex
    now = datetime.now(timezone.utc)

    await _expire_other_pending(session, browser_session_id)

    record = ChatConsentSession(
        browser_session_id=browser_session_id,
        token=token,
        phone=phone,
        campaign_id=campaign.id if campaign else None,
        status=ChatLinkStatus.PENDING,
        created_at=now,
    )
    session.add(record)
    await session.commit()

    link = confirm_url(token)
    campaign_name = campaign.name if campaign else "Promocoes Z-API"
    message = (
        f"Ola! Voce pediu para entrar no grupo *{campaign_name}* pelo site.\n\n"
        f"Toque no link para confirmar sua entrada:\n{link}\n\n"
        f"O link expira em {CONSENT_LINK_TTL_MINUTES} minutos."
    )

    logger.info("Chat link send-text phone=%s token=%s session=%s", phone, token, browser_session_id)
    try:
        result = await mcp_client.call_tool("send-text", {"phone": phone, "message": message})
    except Exception:
        logger.exception("Chat link: falha send-text")
        record.status = ChatLinkStatus.EXPIRED
        await session.commit()
        return (
            False,
            "Nao consegui enviar o link no WhatsApp. Verifique o numero com DDI (ex.: 5544999999999).",
            [],
            "none",
        )

    if not mcp_client.tool_call_succeeded(result):
        logger.warning("Chat link: send-text recusou: %r", result)
        record.status = ChatLinkStatus.EXPIRED
        await session.commit()
        return (
            False,
            "WhatsApp nao aceitou esse numero. Use DDI+DDD+numero, so digitos.",
            ["send-text"],
            "none",
        )

    reply = (
        f"Enviei um link de confirmacao no WhatsApp para {phone}. "
        "Abra a mensagem no celular, toque no link e confirme — "
        "vou aguardar aqui ate voce aceitar."
    )
    return True, reply, ["send-text"], "waiting"


async def get_consent_poll_status(session: AsyncSession, browser_session_id: str) -> dict[str, str | list[str]]:
    now = datetime.now(timezone.utc)
    result = await session.execute(
        select(ChatConsentSession)
        .where(ChatConsentSession.browser_session_id == browser_session_id)
        .order_by(ChatConsentSession.id.desc())
        .limit(1)
    )
    record = result.scalar_one_or_none()
    if record is None:
        return {"status": "none"}

    record = await _expire_if_needed(session, record, now)
    payload: dict[str, str | list[str]] = {"status": record.status.value}
    if record.status == ChatLinkStatus.ACCEPTED:
        payload["tools_used"] = record_tools_for_accept(record)
    return payload


def record_tools_for_accept(record: ChatConsentSession) -> list[str]:
    # Heuristica simples pro chip da UI — detalhe fino nao e critico pro demo.
    return ["send-text", "group-add-participant"]


async def accept_consent_by_token(session: AsyncSession, token: str) -> tuple[bool, str]:
    now = datetime.now(timezone.utc)
    result = await session.execute(select(ChatConsentSession).where(ChatConsentSession.token == token))
    record = result.scalar_one_or_none()
    if record is None:
        return False, "Link invalido ou ja utilizado."

    record = await _expire_if_needed(session, record, now)
    if record.status == ChatLinkStatus.EXPIRED:
        return False, "Este link expirou. Volte ao chat e solicite um novo convite."
    if record.status == ChatLinkStatus.ACCEPTED:
        return True, "Entrada ja confirmada! Pode voltar ao chat no site."

    campaign: Campaign | None = None
    if record.campaign_id:
        campaign = await session.get(Campaign, record.campaign_id)
    if campaign is None:
        campaign = await _latest_campaign(session)

    if campaign is None:
        return False, "Nenhuma campanha ativa no momento."

    if not await ensure_phone_in_group(session, campaign, record.phone):
        return False, "Nao foi possivel adicionar voce ao grupo agora. Tente novamente pelo chat."

    record.status = ChatLinkStatus.ACCEPTED
    record.accepted_at = now
    await session.commit()
    await session.refresh(campaign)

    await _send_group_welcome(campaign)
    try:
        await mcp_client.call_tool(
            "send-text",
            {"phone": record.phone, "message": WELCOME_MESSAGE},
        )
    except Exception:
        logger.exception("Chat link: falha send-text pos-aceite para %s", record.phone)

    logger.info("Chat link aceito token=%s phone=%s session=%s", token, record.phone, record.browser_session_id)
    return True, "Pronto! Voce entrou no grupo de promocoes. Pode voltar ao chat no site."


async def is_human_verified(session: AsyncSession, browser_session_id: str) -> bool:
    now = datetime.now(timezone.utc)
    row = await session.get(ChatHumanVerification, browser_session_id)
    if row is None:
        return False
    if row.expires_at < now:
        await session.delete(row)
        await session.commit()
        return False
    return True


async def mark_human_verified(session: AsyncSession, browser_session_id: str) -> None:
    now = datetime.now(timezone.utc)
    expires = now + _HUMAN_VERIFY_TTL
    row = await session.get(ChatHumanVerification, browser_session_id)
    if row is None:
        session.add(
            ChatHumanVerification(
                browser_session_id=browser_session_id,
                verified_at=now,
                expires_at=expires,
            )
        )
    else:
        row.verified_at = now
        row.expires_at = expires
    await session.commit()
