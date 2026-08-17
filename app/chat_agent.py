"""Agente de chat publico /promocoes — roteiro deterministico + consentimento trackeado.

Sem OpenAI no chat (economia de tokens): onboarding fixo (nome → interesse → telefone),
link WhatsApp via `start_tracked_consent`, news no grupo via backend/MCP.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.campaign_defaults import (
    DEMO_FINISHED_MESSAGE,
    DEMO_SCOPE_ONLY_MESSAGE,
    POST_JOIN_CHAT_MESSAGE,
)
from app.chat_consent import (
    has_accepted_chat_consent,
    start_tracked_consent,
    try_leave_group_from_chat,
)
from app.phone_mask import mask_phone_digits

logger = logging.getLogger("delega.chat_agent")


@dataclass
class ChatTurnResult:
    reply: str
    tools_used: list[str]
    consent_status: str = "none"


_PHONE_RE = re.compile(r"(?:\+?\d[\d\s().-]{8,}\d|\d{10,13})")
_ASK_INTEREST_RE = re.compile(
    r"\b(participar|sim ou nao|sim ou não|novidade|z-api|mcp)\b", re.IGNORECASE
)
_ASK_PHONE_RE = re.compile(r"\b(whatsapp|ddi|telefone|numero|número)\b", re.IGNORECASE)
_YES_RE = re.compile(r"\b(sim|quero|pode|ok|okay|bora|vamos|tenho interesse)\b", re.IGNORECASE)
_NO_RE = re.compile(r"\b(nao|não|agora nao|agora não|depois|prefiro nao|prefiro não)\b", re.IGNORECASE)
_CONFIRM_RE = re.compile(
    r"\b(sim|confirmo|confirmar|correto|certo|isso|pode|ok|okay|envia|envie|manda|mande)\b",
    re.IGNORECASE,
)
_ASK_CONFIRM_RE = re.compile(
    r"\b(confirm|correto|certo|numero|número|whatsapp|ddi|telefone)\b",
    re.IGNORECASE,
)


def _normalize_phone(raw: str) -> str | None:
    digits = re.sub(r"\D", "", raw)
    if len(digits) < 10:
        return None
    if len(digits) in (10, 11) and not digits.startswith("55"):
        digits = "55" + digits
    if len(digits) < 12 or len(digits) > 13:
        return None
    return digits


def _extract_phone(text: str) -> str | None:
    for match in _PHONE_RE.findall(text):
        normalized = _normalize_phone(match)
        if normalized:
            return normalized
    return None


def _phones_from_context(history: list[dict[str, str]], user_message: str) -> list[str]:
    found: list[str] = []
    for item in [*history[-12:], {"role": "user", "content": user_message}]:
        if item.get("role") != "user":
            continue
        phone = _extract_phone((item.get("content") or "").strip())
        if phone and phone not in found:
            found.append(phone)
    return found


def _latest_assistant_text(history: list[dict[str, str]]) -> str:
    for item in reversed(history[-8:]):
        if item.get("role") == "assistant":
            return (item.get("content") or "").strip()
    return ""


def _is_explicit_confirmation(text: str) -> bool:
    return bool(_CONFIRM_RE.search(text.strip()))


def _assistant_asked_phone_confirmation(history: list[dict[str, str]]) -> bool:
    return bool(_ASK_CONFIRM_RE.search(_latest_assistant_text(history)))


def _should_send_whatsapp_invite(history: list[dict[str, str]], user_message: str) -> str | None:
    """Telefone confirmado pelo visitante — dispara send-text de forma deterministica."""
    text = user_message.strip()
    phone_in_message = _extract_phone(text)
    phones = _phones_from_context(history, user_message)

    if phone_in_message and (_is_explicit_confirmation(text) or _assistant_asked_phone_confirmation(history)):
        return phone_in_message

    if _is_explicit_confirmation(text) and phones:
        return phones[-1]

    if phone_in_message and len(phones) >= 2 and phone_in_message == phones[-1]:
        # Visitante corrigiu o numero depois que a assistente pediu confirmacao.
        return phone_in_message

    return None


_NAME_ASK_RE = re.compile(r"\bnome\b", re.IGNORECASE)
_NAME_STRIP_RE = re.compile(r"[^A-Za-zÀ-ÖØ-öø-ÿ'’-]")


def _looks_like_phone_or_digits(text: str) -> bool:
    return len(re.sub(r"\D", "", text)) >= 8


def _extract_name_from_history(history: list[dict[str, str]], user_message: str) -> str | None:
    """Acha o primeiro nome do visitante procurando, de tras pra frente, o
    ultimo par (assistente perguntou o nome) -> (visitante respondeu).
    Nunca confia que a resposta veio no formato certo — pega so o primeiro
    token e normaliza pra Xxxxx via `.capitalize()` (Unicode-aware, cobre
    acentuacao: "joão" -> "João", "MARIA CLARA" -> "Maria")."""
    combined = [*history[-16:], {"role": "user", "content": user_message}]
    for i in range(len(combined) - 1, 0, -1):
        item = combined[i]
        prev = combined[i - 1]
        if item.get("role") != "user" or prev.get("role") != "assistant":
            continue
        if not _NAME_ASK_RE.search((prev.get("content") or "")):
            continue
        raw = (item.get("content") or "").strip()
        if not raw or _looks_like_phone_or_digits(raw):
            continue
        first_token = raw.split()[0]
        cleaned = _NAME_STRIP_RE.sub("", first_token)
        if cleaned:
            return cleaned.capitalize()
    return None


def _try_deterministic_onboarding_reply(
    history: list[dict[str, str]], user_message: str
) -> str | None:
    """Roteiro fixo da demo — sem OpenAI (economia de tokens)."""
    text = user_message.strip()
    last = _latest_assistant_text(history)

    if _NAME_ASK_RE.search(last):
        name = _extract_name_from_history(history, user_message)
        if name:
            return (
                f"Prazer, {name}! Esta demo envia uma novidade sobre Z-API + MCP no seu WhatsApp. "
                "Quer participar? Responda sim ou nao."
            )
        return "Me diga so seu primeiro nome (ex.: Maria) para comecarmos."

    if _ASK_INTEREST_RE.search(last) or last.startswith("Prazer,"):
        if _YES_RE.search(text):
            return (
                "Otimo! Informe seu WhatsApp com DDI (ex.: 5511999999999). "
                "Confirmo o numero antes de enviar o link."
            )
        if _NO_RE.search(text):
            return (
                "Sem problemas. Se quiser ver a novidade Z-API + MCP depois, "
                "volte aqui e diga que quer participar."
            )

    phone = _extract_phone(text)
    if phone and not _is_explicit_confirmation(text):
        if _ASK_PHONE_RE.search(last) or "Confirma o numero" in last or "Informe seu WhatsApp" in last:
            masked = mask_phone_digits(phone)
            return (
                f"Confirma o numero {masked}? "
                "Responda sim para eu enviar o link de confirmacao no WhatsApp."
            )

    return None


_POST_ONBOARDING_NOW_RE = re.compile(
    r"\b(e agora|e dai|e depois|proximo passo|what now|what next)\b", re.IGNORECASE
)
_WHO_ARE_YOU_RE = re.compile(
    r"\b(quem (e|é) vc|quem (e|é) voce|quem (e|é) você|what are you|who are you)\b", re.IGNORECASE
)
_WHO_MADE_YOU_RE = re.compile(
    r"\b(quem (te )?fez|quem (te )?criou|who (made|created) you)\b", re.IGNORECASE
)
_PROMPT_LEAK_RE = re.compile(r"\b(prompt|system prompt|instrucoes internas|regras internas)\b", re.IGNORECASE)


def _post_onboarding_quick_reply(user_message: str) -> str:
    """Pos-onboarding: sem OpenAI — respostas fixas ou encerramento da demo."""
    text = user_message.strip()
    if _PROMPT_LEAK_RE.search(text):
        return DEMO_FINISHED_MESSAGE
    if _WHO_MADE_YOU_RE.search(text) or _WHO_ARE_YOU_RE.search(text):
        return DEMO_FINISHED_MESSAGE
    if _POST_ONBOARDING_NOW_RE.search(text):
        return POST_JOIN_CHAT_MESSAGE
    return DEMO_FINISHED_MESSAGE


async def run_chat_turn(
    session: AsyncSession,
    history: list[dict[str, str]],
    user_message: str,
    browser_session_id: str,
) -> ChatTurnResult:
    """Executa um turno do chat publico (roteiro deterministico, sem OpenAI)."""
    confirmed_phone = _should_send_whatsapp_invite(history, user_message)
    if confirmed_phone:
        visitor_name = _extract_name_from_history(history, user_message)
        ok, auto_reply, auto_tools, consent_status = await start_tracked_consent(
            session, browser_session_id, confirmed_phone, visitor_name
        )
        return ChatTurnResult(reply=auto_reply, tools_used=auto_tools, consent_status=consent_status)

    onboarding_complete = await has_accepted_chat_consent(session, browser_session_id)

    leave_result = await try_leave_group_from_chat(session, browser_session_id, user_message)
    if leave_result is not None:
        ok, reply, tools, consent_status = leave_result
        return ChatTurnResult(reply=reply, tools_used=tools, consent_status=consent_status)

    if onboarding_complete:
        return ChatTurnResult(reply=_post_onboarding_quick_reply(user_message), tools_used=[])

    deterministic = _try_deterministic_onboarding_reply(history, user_message)
    if deterministic:
        return ChatTurnResult(reply=deterministic, tools_used=[])

    return ChatTurnResult(reply=DEMO_SCOPE_ONLY_MESSAGE, tools_used=[])
