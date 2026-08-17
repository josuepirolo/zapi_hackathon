"""Consentimento trackeado via link — chat publico /promocoes.

Fluxo por participante (CONTEXTO §7 — 1 pessoa por grupo, admin + 1):
  send-text (link) -> confirmar -> group-create (#NNN) -> group-add-participant ->
  send-text (boas-vindas DM) -> send-image (primeira news do dia no grupo).

Persistencia em SQLite (mesmo banco); sessao do browser = UUID em localStorage.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import mcp_client
from app.phone_mask import mask_phone_digits
from app.campaign_defaults import (
    ADMIN_ALREADY_MEMBER_MESSAGE,
    ALREADY_MEMBER_MESSAGE,
    GROUP_ACCESS_LINK_DM,
    GROUP_NAME_PREFIX,
    INSTANCE_PHONE_BLOCKED_MESSAGE,
    JOINED_MESSAGE,
    LEAVE_ALREADY_GONE,
    LEAVE_GROUP_FAILED,
    LEAVE_GROUP_SUCCESS,
    LEAVE_LINK_CHAT_REPLY,
    LEAVE_LINK_DM,
    WELCOME_MESSAGE,
)
from app.config import (
    CHAT_HUMAN_VERIFY_TTL_HOURS,
    CONSENT_LINK_TTL_MINUTES,
    PUBLIC_BASE_URL,
    ZAPI_INSTANCE_PHONE,
)
from app.group_news import send_group_news
from app.models import Campaign, ChatConsentSession, ChatHumanVerification, ChatLinkStatus, ChatSessionFlow
from app.webhook import _lock_campaign

logger = logging.getLogger("delega.chat_consent")

_CONSENT_TTL = timedelta(minutes=CONSENT_LINK_TTL_MINUTES)
_HUMAN_VERIFY_TTL = timedelta(hours=CHAT_HUMAN_VERIFY_TTL_HOURS)

_LEAVE_INTENT_RE = re.compile(
    r"\b(sair do grupo|quero sair|encerrar (minha )?participa|leave the group|remover do grupo)\b",
    re.IGNORECASE,
)


def _utc_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def normalize_browser_session_id(raw: str | None) -> str:
    if not raw:
        return str(uuid.uuid4())
    try:
        return str(uuid.UUID(raw.strip()))
    except ValueError:
        return str(uuid.uuid4())


def confirm_url(token: str) -> str:
    return f"{PUBLIC_BASE_URL}/confirmar/{token}"


def leave_url(token: str) -> str:
    return f"{PUBLIC_BASE_URL}/sair/{token}"


def _is_expired(record: ChatConsentSession, now: datetime) -> bool:
    if record.status not in (ChatLinkStatus.PENDING, ChatLinkStatus.REMOVE_PENDING):
        return False
    return _utc_aware(record.created_at) + _CONSENT_TTL < now


async def _expire_if_needed(session: AsyncSession, record: ChatConsentSession, now: datetime) -> ChatConsentSession:
    if record.status in (ChatLinkStatus.PENDING, ChatLinkStatus.REMOVE_PENDING) and _is_expired(record, now):
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
            ChatConsentSession.status.in_(
                (ChatLinkStatus.PENDING, ChatLinkStatus.REMOVE_PENDING)
            ),
        )
    )
    for row in result.scalars().all():
        if except_id is not None and row.id == except_id:
            continue
        row.status = ChatLinkStatus.EXPIRED
    await session.commit()


async def _next_group_name(session: AsyncSession, campaign: Campaign) -> str:
    """Tech News IA & MCP #001, #002, ... — sequencial por grupos ja criados."""
    await _lock_campaign(session, campaign.id)
    result = await session.execute(
        select(func.count()).select_from(ChatConsentSession).where(
            ChatConsentSession.whatsapp_group_id.isnot(None)
        )
    )
    seq = int(result.scalar_one() or 0) + 1
    return f"{GROUP_NAME_PREFIX} #{seq:03d}"


async def _find_prior_personal_group(session: AsyncSession, phone: str) -> ChatConsentSession | None:
    """Ultima sessao aceita deste telefone (tolera variacao do 9o digito BR)."""
    result = await session.execute(
        select(ChatConsentSession)
        .where(
            ChatConsentSession.status == ChatLinkStatus.ACCEPTED,
            ChatConsentSession.flow == ChatSessionFlow.JOIN,
            ChatConsentSession.whatsapp_group_id.isnot(None),
        )
        .order_by(ChatConsentSession.id.desc())
        .limit(100)
    )
    for row in result.scalars():
        if mcp_client.phones_equivalent(row.phone, phone):
            return row
    return None


async def _detect_existing_participant(
    session: AsyncSession, phone: str
) -> tuple[str | None, ChatConsentSession | None]:
    """Retorna (kind, sessao anterior) se o telefone ja concluiu onboarding."""
    prior = await _find_prior_personal_group(session, phone)
    if prior is None or not prior.whatsapp_group_id:
        return None, None
    try:
        meta = await mcp_client.call_tool("group-metadata", {"groupId": prior.whatsapp_group_id})
        participant = mcp_client.find_participant(meta, phone)
        if participant is None:
            return None, None
        kind = "admin" if (participant.get("isAdmin") or participant.get("isSuperAdmin")) else "member"
        return kind, prior
    except Exception:
        logger.exception("Falha group-metadata ao checar participante existente %s", phone)
        return "member", prior


def _returning_member_chat_message(
    prior: ChatConsentSession,
    kind: str,
    *,
    dm_sent: bool,
    invite_link_sent: bool,
    news_tools: list[str],
) -> str:
    label = prior.group_name or GROUP_NAME_PREFIX
    prefix = (
        f"Voce ja administra o grupo *{label}*!"
        if kind == "admin"
        else f"Voce ja esta no grupo *{label}*!"
    )
    parts = [prefix]
    if dm_sent and invite_link_sent:
        parts.append("Enviei o link de acesso no WhatsApp.")
    elif dm_sent:
        parts.append("Enviei uma mensagem no seu WhatsApp sobre o grupo.")
    else:
        parts.append("Nao consegui enviar mensagem no WhatsApp agora — tente informar seu numero de novo.")
    if news_tools:
        parts.append("Republicamos a novidade de hoje la.")
    else:
        parts.append("A novidade de hoje nao foi republicada — tente de novo em instantes.")
    return " ".join(parts)


async def _finish_returning_member(
    session: AsyncSession,
    browser_session_id: str,
    name: str | None,
    kind: str,
    prior: ChatConsentSession,
    campaign: Campaign | None,
) -> tuple[bool, str, list[str], str]:
    """Quem ja tem grupo pessoal: pula link, republica news e conclui no chat."""
    now = datetime.now(timezone.utc)
    await _expire_other_pending(session, browser_session_id)

    record = ChatConsentSession(
        browser_session_id=browser_session_id,
        token=uuid.uuid4().hex,
        phone=prior.phone,
        name=name or prior.name,
        campaign_id=campaign.id if campaign else prior.campaign_id,
        status=ChatLinkStatus.PREPARING_CONTENT,
        existing_member_kind=kind,
        whatsapp_group_id=prior.whatsapp_group_id,
        group_name=prior.group_name,
        created_at=now,
    )
    session.add(record)
    await session.commit()

    dm_sent, invite_link_sent = await _send_group_access_dm(
        prior.phone, prior.whatsapp_group_id, prior.group_name
    )
    news_tools = await send_group_news(prior.whatsapp_group_id)

    record.status = ChatLinkStatus.ACCEPTED
    record.accepted_at = now
    await session.commit()

    logger.info(
        "Chat returning member browser=%s phone=%s grupo=%s kind=%s dm_sent=%s invite_link=%s news_tools=%s",
        browser_session_id,
        prior.phone,
        prior.whatsapp_group_id,
        kind,
        dm_sent,
        invite_link_sent,
        news_tools,
    )
    reply = _returning_member_chat_message(
        prior, kind, dm_sent=dm_sent, invite_link_sent=invite_link_sent, news_tools=news_tools
    )
    tools: list[str] = ["group-metadata"]
    if dm_sent:
        tools.append("send-text")
    tools.extend(news_tools)
    return True, reply, tools, "accepted"


async def _create_personal_group(
    session: AsyncSession, campaign: Campaign, phone: str, record: ChatConsentSession
) -> tuple[str | None, str | None]:
    """Cria grupo exclusivo (admin da instancia + 1 participante).

    Retorna (group_id, erro_mcp) — tenta variantes do 9o digito BR."""
    group_name = await _next_group_name(session, campaign)
    last_error: str | None = None

    for candidate in mcp_client.mcp_phone_candidates(phone):
        try:
            create_result = await mcp_client.call_tool(
                "group-create",
                {"groupName": group_name, "phones": [candidate], "autoInvite": True},
            )
        except Exception:
            logger.exception("Chat link: falha group-create para %s", candidate)
            continue

        last_error = mcp_client.mcp_error_message(create_result) or last_error
        group_id = mcp_client.extract_group_id(create_result)
        if group_id is None:
            logger.warning(
                "Chat link: group-create recusou candidato %s (original %s): %r",
                candidate,
                phone,
                create_result,
            )
            continue

        if candidate != phone:
            logger.info("Chat link: group-create ok com variante %s (digitado %s)", candidate, phone)
            record.phone = candidate

        record.whatsapp_group_id = group_id
        record.group_name = group_name
        await session.flush()

        try:
            await mcp_client.call_tool("group-metadata", {"groupId": group_id})
        except Exception:
            logger.exception("Chat link: falha group-metadata pos-create %s", group_id)

        try:
            add_result = await mcp_client.call_tool(
                "group-add-participant",
                {"groupId": group_id, "phones": [candidate], "autoInvite": True},
            )
            if not mcp_client.tool_call_succeeded(add_result):
                logger.warning("Chat link: group-add-participant pos-create %s: %r", candidate, add_result)
        except Exception:
            logger.exception("Chat link: falha group-add-participant pos-create %s", candidate)

        return group_id, None

    return None, last_error


def _group_create_user_message(mcp_message: str | None) -> str:
    hint = (mcp_message or "").lower()
    if "participants not found" in hint:
        return INSTANCE_PHONE_BLOCKED_MESSAGE
    return "Nao foi possivel criar seu grupo agora. Tente novamente pelo chat."


def _is_instance_phone(phone: str) -> bool:
    if not ZAPI_INSTANCE_PHONE:
        return False
    return mcp_client.phones_equivalent(phone, ZAPI_INSTANCE_PHONE)


def _welcome_dm_text(record: ChatConsentSession) -> str:
    if record.name:
        return f"Oi, {record.name}! {WELCOME_MESSAGE}"
    return WELCOME_MESSAGE


async def _is_still_group_member(record: ChatConsentSession) -> bool:
    """Confere no WhatsApp se o telefone ainda esta no grupo pessoal."""
    if not record.whatsapp_group_id:
        return False
    try:
        meta = await mcp_client.call_tool("group-metadata", {"groupId": record.whatsapp_group_id})
        return mcp_client.find_participant(meta, record.phone) is not None
    except Exception:
        logger.exception(
            "Falha group-metadata ao checar membro %s no grupo %s",
            record.phone,
            record.whatsapp_group_id,
        )
        # Falha transiente no MCP: nao invalidar participacao ativa.
        return True


async def _record_membership_ended(
    session: AsyncSession,
    join_record: ChatConsentSession,
    *,
    reason: str = "not_in_group",
) -> None:
    """Registra saida (sintetica) para liberar re-entrada no chat do browser."""
    result = await session.execute(
        select(ChatConsentSession.id).where(
            ChatConsentSession.browser_session_id == join_record.browser_session_id,
            ChatConsentSession.flow == ChatSessionFlow.LEAVE,
            ChatConsentSession.status == ChatLinkStatus.REMOVED,
            ChatConsentSession.id > join_record.id,
        ).limit(1)
    )
    if result.scalar_one_or_none() is not None:
        return

    now = datetime.now(timezone.utc)
    session.add(
        ChatConsentSession(
            browser_session_id=join_record.browser_session_id,
            token=uuid.uuid4().hex,
            phone=join_record.phone,
            name=join_record.name,
            campaign_id=join_record.campaign_id,
            flow=ChatSessionFlow.LEAVE,
            status=ChatLinkStatus.REMOVED,
            whatsapp_group_id=join_record.whatsapp_group_id,
            group_name=join_record.group_name,
            created_at=now,
            accepted_at=now,
        )
    )
    await session.commit()
    logger.info(
        "Chat membership ended browser=%s phone=%s grupo=%s reason=%s",
        join_record.browser_session_id,
        join_record.phone,
        join_record.whatsapp_group_id,
        reason,
    )


async def get_accepted_consent_session(
    session: AsyncSession, browser_session_id: str
) -> ChatConsentSession | None:
    result = await session.execute(
        select(ChatConsentSession)
        .where(
            ChatConsentSession.browser_session_id == browser_session_id,
            ChatConsentSession.flow == ChatSessionFlow.JOIN,
            ChatConsentSession.status == ChatLinkStatus.ACCEPTED,
            ChatConsentSession.whatsapp_group_id.isnot(None),
        )
        .order_by(ChatConsentSession.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def try_leave_group_from_chat(
    session: AsyncSession,
    browser_session_id: str,
    user_message: str,
) -> tuple[bool, str, list[str], str] | None:
    """Inicia saida trackeada via link no WhatsApp (mesmo padrao da entrada)."""
    if not _LEAVE_INTENT_RE.search(user_message.strip()):
        return None
    return await start_tracked_leave(session, browser_session_id)


async def start_tracked_leave(
    session: AsyncSession,
    browser_session_id: str,
) -> tuple[bool, str, list[str], str]:
    join_record = await get_accepted_consent_session(session, browser_session_id)
    if join_record is None or not join_record.whatsapp_group_id:
        return False, "Voce ainda nao entrou em um grupo nesta demo.", [], "none"

    label = join_record.group_name or GROUP_NAME_PREFIX

    try:
        meta = await mcp_client.call_tool("group-metadata", {"groupId": join_record.whatsapp_group_id})
        if mcp_client.find_participant(meta, join_record.phone) is None:
            await _record_membership_ended(session, join_record, reason="leave_precheck_absent")
            return False, LEAVE_ALREADY_GONE.format(group_name=label), [], "removed"
    except Exception:
        logger.exception("Chat leave: falha group-metadata pre-check %s", join_record.whatsapp_group_id)

    token = uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    await _expire_other_pending(session, browser_session_id)

    record = ChatConsentSession(
        browser_session_id=browser_session_id,
        token=token,
        phone=join_record.phone,
        name=join_record.name,
        campaign_id=join_record.campaign_id,
        flow=ChatSessionFlow.LEAVE,
        status=ChatLinkStatus.REMOVE_PENDING,
        whatsapp_group_id=join_record.whatsapp_group_id,
        group_name=join_record.group_name,
        created_at=now,
    )
    session.add(record)
    await session.commit()

    link = leave_url(token)
    message = LEAVE_LINK_DM.format(
        group_name=label,
        link=link,
        minutes=CONSENT_LINK_TTL_MINUTES,
    )

    logger.info(
        "Chat leave link send-text phone=%s token=%s session=%s grupo=%s",
        join_record.phone,
        token,
        browser_session_id,
        join_record.whatsapp_group_id,
    )

    if not await _send_text_dm(join_record.phone, message):
        record.status = ChatLinkStatus.EXPIRED
        await session.commit()
        return (
            False,
            "Nao consegui enviar o link de confirmacao de saida no WhatsApp. Tente de novo em instantes.",
            [],
            "none",
        )

    masked = mask_phone_digits(join_record.phone)
    reply = LEAVE_LINK_CHAT_REPLY.format(masked=masked)
    return True, reply, ["send-text"], "waiting"


async def accept_leave_by_token(session: AsyncSession, token: str) -> tuple[bool, str]:
    now = datetime.now(timezone.utc)
    result = await session.execute(select(ChatConsentSession).where(ChatConsentSession.token == token))
    record = result.scalar_one_or_none()
    if record is None or record.flow != ChatSessionFlow.LEAVE:
        return False, "Link invalido ou ja utilizado."

    record = await _expire_if_needed(session, record, now)
    if record.status == ChatLinkStatus.EXPIRED:
        return False, "Este link expirou. Volte ao chat e solicite sair do grupo novamente."
    if record.status == ChatLinkStatus.REMOVED:
        return True, LEAVE_GROUP_SUCCESS.format(group_name=record.group_name or GROUP_NAME_PREFIX)
    if record.status != ChatLinkStatus.REMOVE_PENDING:
        return False, "Este link nao pode mais ser usado."

    if not record.whatsapp_group_id:
        return False, "Nao encontrei seu grupo. Tente novamente pelo chat."

    label = record.group_name or GROUP_NAME_PREFIX
    record.status = ChatLinkStatus.REMOVING
    await session.commit()

    removed = await _remove_from_personal_group(record.whatsapp_group_id, record.phone)
    tools_used: list[str] = ["group-remove-participant", "group-metadata"]

    if not removed:
        record.status = ChatLinkStatus.REMOVE_PENDING
        await session.commit()
        return False, LEAVE_GROUP_FAILED

    dm = f"Voce foi removido do grupo {label}. Obrigado por participar da demo Tech News!"
    if await _send_text_dm(record.phone, dm):
        tools_used.append("send-text")

    record.status = ChatLinkStatus.REMOVED
    record.accepted_at = now
    await session.commit()

    logger.info(
        "Chat leave confirmado token=%s phone=%s grupo=%s session=%s",
        token,
        record.phone,
        record.whatsapp_group_id,
        record.browser_session_id,
    )
    return True, LEAVE_GROUP_SUCCESS.format(group_name=label)


async def _send_text_dm(phone: str, message: str) -> bool:
    """send-text no privado — tenta variantes do 9o digito BR."""
    for candidate in mcp_client.mcp_phone_candidates(phone):
        try:
            result = await mcp_client.call_tool("send-text", {"phone": candidate, "message": message})
        except Exception:
            logger.exception("Chat: falha send-text DM para %s (candidato %s)", phone, candidate)
            continue
        if mcp_client.tool_call_succeeded(result):
            if candidate != phone:
                logger.info("Chat: send-text DM ok com variante %s (original %s)", candidate, phone)
            return True
        logger.warning("Chat: send-text DM recusou candidato %s: %r", candidate, result)
    return False


async def _remove_from_personal_group(group_id: str, phone: str) -> bool:
    for candidate in mcp_client.mcp_phone_candidates(phone):
        try:
            result = await mcp_client.call_tool(
                "group-remove-participant",
                {"groupId": group_id, "phones": [candidate]},
            )
        except Exception:
            logger.exception("Chat: falha group-remove-participant %s grupo %s", candidate, group_id)
            continue
        if not mcp_client.tool_call_succeeded(result):
            logger.warning("Chat: group-remove-participant recusou %s: %r", candidate, result)
            continue
        try:
            meta = await mcp_client.call_tool("group-metadata", {"groupId": group_id})
            if mcp_client.find_participant(meta, phone) is None:
                return True
            logger.warning("Chat: group-remove-participant ok mas participante ainda listado %s", phone)
            return True
        except Exception:
            logger.exception("Chat: falha group-metadata pos-remove %s", group_id)
            return True
    return False


async def _send_welcome_dm(phone: str, record: ChatConsentSession) -> bool:
    return await _send_text_dm(phone, _welcome_dm_text(record))


async def _fetch_group_invitation_link(group_id: str) -> str | None:
    try:
        meta = await mcp_client.call_tool("group-metadata", {"groupId": group_id})
        link = mcp_client.extract_invitation_link(meta)
        if link:
            return link
        payload = mcp_client.parse_tool_payload(meta)
        if isinstance(payload, dict) and payload.get("invitationLinkError"):
            logger.warning(
                "Chat: invitationLinkError grupo %s: %s",
                group_id,
                payload.get("invitationLinkError"),
            )
    except Exception:
        logger.exception("Chat link: falha group-metadata para invitationLink %s", group_id)
    return None


async def _send_group_access_dm(phone: str, group_id: str, group_name: str | None) -> tuple[bool, bool]:
    """Retorna (dm_enviado, continha_link_chat_whatsapp)."""
    link = await _fetch_group_invitation_link(group_id)
    label = group_name or GROUP_NAME_PREFIX
    if link:
        message = GROUP_ACCESS_LINK_DM.format(group_name=label, link=link)
    else:
        logger.warning("Chat: invitationLink indisponivel para grupo %s — fallback texto", group_id)
        message = (
            f"Seu grupo *{label}* esta ativo no WhatsApp. "
            "Abra a conversa do grupo na lista de chats — se nao achar, peca o link de novo aqui no site."
        )
    sent = await _send_text_dm(phone, message)
    return sent, bool(link)


async def _complete_onboarding(
    session: AsyncSession,
    record: ChatConsentSession,
    group_id: str,
    *,
    resend_welcome: bool,
) -> None:
    """Boas-vindas DM (opcional) + primeira news no grupo pessoal."""
    if resend_welcome:
        await _send_welcome_dm(record.phone, record)

    await _send_group_access_dm(record.phone, group_id, record.group_name)

    record.status = ChatLinkStatus.PREPARING_CONTENT
    await session.commit()

    await send_group_news(group_id)


async def start_tracked_consent(
    session: AsyncSession,
    browser_session_id: str,
    phone: str,
    name: str | None = None,
) -> tuple[bool, str, list[str], str]:
    if _is_instance_phone(phone):
        logger.info("Chat link recusado: numero da instancia Z-API (admin) phone=%s session=%s", phone, browser_session_id)
        return False, INSTANCE_PHONE_BLOCKED_MESSAGE, [], "none"

    campaign = await _latest_campaign(session)

    existing_kind, prior = await _detect_existing_participant(session, phone)
    if existing_kind and prior:
        return await _finish_returning_member(
            session, browser_session_id, name, existing_kind, prior, campaign
        )

    token = uuid.uuid4().hex
    now = datetime.now(timezone.utc)

    await _expire_other_pending(session, browser_session_id)

    tools_used: list[str] = []

    record = ChatConsentSession(
        browser_session_id=browser_session_id,
        token=token,
        phone=phone,
        name=name,
        campaign_id=campaign.id if campaign else None,
        status=ChatLinkStatus.PENDING,
        existing_member_kind=None,
        created_at=now,
    )
    session.add(record)
    await session.commit()

    link = confirm_url(token)
    campaign_name = campaign.name if campaign else GROUP_NAME_PREFIX
    greeting = f"Ola, {name}!" if name else "Ola!"
    message = (
        f"{greeting} Voce pediu para confirmar seu WhatsApp no *{campaign_name}* pelo site.\n\n"
        f"Toque no link para confirmar seu numero:\n{link}\n\n"
        f"O link expira em {CONSENT_LINK_TTL_MINUTES} minutos."
    )

    logger.info(
        "Chat link send-text phone=%s token=%s session=%s",
        phone, token, browser_session_id,
    )
    try:
        result = await mcp_client.call_tool("send-text", {"phone": phone, "message": message})
    except Exception:
        logger.exception("Chat link: falha send-text")
        record.status = ChatLinkStatus.EXPIRED
        await session.commit()
        return (
            False,
            "Nao consegui enviar o link no WhatsApp. Verifique o numero com DDI (ex.: 5544***9999).",
            tools_used,
            "none",
        )

    if not mcp_client.tool_call_succeeded(result):
        logger.warning("Chat link: send-text recusou: %r", result)
        record.status = ChatLinkStatus.EXPIRED
        await session.commit()
        return (
            False,
            "WhatsApp nao aceitou esse numero. Use DDI+DDD+numero, so digitos.",
            tools_used + ["send-text"],
            "none",
        )

    tools_used = tools_used + ["send-text"]
    masked = mask_phone_digits(phone)
    reply = (
        f"Enviei um link de confirmacao no WhatsApp para {masked}. "
        "Abra a mensagem no celular, toque no link e confirme — "
        "vou aguardar aqui ate voce confirmar."
    )
    return True, reply, tools_used, "waiting"


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

    if (
        record.flow == ChatSessionFlow.JOIN
        and record.status == ChatLinkStatus.ACCEPTED
        and record.whatsapp_group_id
        and not await _is_still_group_member(record)
    ):
        await _record_membership_ended(session, record, reason="poll_stale_accepted")
        return {"status": "none"}

    payload: dict[str, str | list[str]] = {"status": str(record.status)}
    if record.flow == ChatSessionFlow.LEAVE and record.status == ChatLinkStatus.REMOVED:
        payload["tools_used"] = ["group-remove-participant", "group-metadata", "send-text"]
        payload["message"] = LEAVE_GROUP_SUCCESS.format(
            group_name=record.group_name or GROUP_NAME_PREFIX
        )
    elif record.status == ChatLinkStatus.ACCEPTED:
        payload["tools_used"] = record_tools_for_accept(record)
        payload["message"] = _accepted_message_for(record)
    return payload


def _accepted_message_for(record: ChatConsentSession) -> str:
    if record.group_name and record.existing_member_kind:
        return _returning_member_chat_message(
            record,
            record.existing_member_kind,
            dm_sent=True,
            invite_link_sent=True,
            news_tools=["send-image", "send-text"],
        )
    if record.existing_member_kind == "admin":
        return ADMIN_ALREADY_MEMBER_MESSAGE
    if record.existing_member_kind == "member":
        return ALREADY_MEMBER_MESSAGE
    return JOINED_MESSAGE


def record_tools_for_accept(record: ChatConsentSession) -> list[str]:
    if record.existing_member_kind:
        return ["group-metadata", "send-text", "send-image", "send-text"]
    return [
        "group-create",
        "group-metadata",
        "group-add-participant",
        "send-text",
        "send-text",
        "send-image",
        "send-text",
    ]


async def accept_consent_by_token(session: AsyncSession, token: str) -> tuple[bool, str]:
    now = datetime.now(timezone.utc)
    result = await session.execute(select(ChatConsentSession).where(ChatConsentSession.token == token))
    record = result.scalar_one_or_none()
    if record is None:
        return False, "Link invalido ou ja utilizado."
    if record.flow != ChatSessionFlow.JOIN:
        return False, "Link invalido para entrada."

    record = await _expire_if_needed(session, record, now)
    if record.status == ChatLinkStatus.EXPIRED:
        return False, "Este link expirou. Volte ao chat e solicite um novo convite."
    if record.status == ChatLinkStatus.ACCEPTED:
        return True, "Entrada ja confirmada! Pode voltar ao chat no site."

    if _is_instance_phone(record.phone):
        logger.info("Chat link accept recusado: numero da instancia Z-API token=%s phone=%s", token, record.phone)
        return False, INSTANCE_PHONE_BLOCKED_MESSAGE

    campaign: Campaign | None = None
    if record.campaign_id:
        campaign = await session.get(Campaign, record.campaign_id)
    if campaign is None:
        campaign = await _latest_campaign(session)
    if campaign is None:
        return False, "Nenhuma campanha ativa no momento."

    if record.existing_member_kind:
        kind, prior = await _detect_existing_participant(session, record.phone)
        if prior is None or not prior.whatsapp_group_id:
            return False, "Nao encontrei seu grupo anterior. Tente novamente pelo chat."

        record.whatsapp_group_id = prior.whatsapp_group_id
        record.group_name = prior.group_name
        record.status = ChatLinkStatus.ADDING_PARTICIPANT
        await session.commit()

        await _complete_onboarding(session, record, prior.whatsapp_group_id, resend_welcome=True)

        record.status = ChatLinkStatus.ACCEPTED
        record.accepted_at = now
        await session.commit()

        logger.info(
            "Chat link confirmado (contato ja existente, kind=%s) token=%s phone=%s",
            record.existing_member_kind, token, record.phone,
        )
        return True, _returning_member_chat_message(
            prior,
            record.existing_member_kind,
            dm_sent=True,
            invite_link_sent=True,
            news_tools=["send-image", "send-text"],
        )

    record.status = ChatLinkStatus.CREATING_GROUP
    await session.commit()

    group_id, create_error = await _create_personal_group(session, campaign, record.phone, record)
    if group_id is None:
        record.status = ChatLinkStatus.PENDING
        await session.commit()
        return False, _group_create_user_message(create_error)

    record.status = ChatLinkStatus.ADDING_PARTICIPANT
    await session.commit()

    await _send_welcome_dm(record.phone, record)

    await _complete_onboarding(session, record, group_id, resend_welcome=False)

    record.status = ChatLinkStatus.ACCEPTED
    record.accepted_at = now
    await session.commit()

    logger.info(
        "Chat link aceito token=%s phone=%s grupo=%s session=%s",
        token, record.phone, group_id, record.browser_session_id,
    )
    return True, JOINED_MESSAGE


async def has_accepted_chat_consent(session: AsyncSession, browser_session_id: str) -> bool:
    join = await get_accepted_consent_session(session, browser_session_id)
    if join is None:
        return False
    result = await session.execute(
        select(ChatConsentSession.id)
        .where(
            ChatConsentSession.browser_session_id == browser_session_id,
            ChatConsentSession.flow == ChatSessionFlow.LEAVE,
            ChatConsentSession.status == ChatLinkStatus.REMOVED,
            ChatConsentSession.id > join.id,
        )
        .limit(1)
    )
    if result.scalar_one_or_none() is not None:
        return False
    if not await _is_still_group_member(join):
        await _record_membership_ended(session, join, reason="chat_stale_accepted")
        return False
    return True


async def is_human_verified(session: AsyncSession, browser_session_id: str) -> bool:
    now = datetime.now(timezone.utc)
    row = await session.get(ChatHumanVerification, browser_session_id)
    if row is None:
        return False
    if _utc_aware(row.expires_at) < now:
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
