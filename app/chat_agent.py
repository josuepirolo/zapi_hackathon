"""Agente de chat publico: OpenAI + tools MCP Z-API oficial.

Demonstracao hackathon — visitante conversa na pagina; a IA decide quando
chamar cada uma das 9 tools via `app.mcp_client`.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import mcp_client
from app.campaign_defaults import (
    INVITATION_MESSAGE,
    POST_JOIN_CHAT_MESSAGE,
    TRIGGER_KEYWORD,
    WELCOME_MESSAGE,
)
from app.chat_consent import has_accepted_chat_consent, start_tracked_consent
from app.config import OPENAI_API_KEY, OPENAI_MODEL
from app.models import Campaign

logger = logging.getLogger("delega.chat_agent")

_client = AsyncOpenAI(api_key=OPENAI_API_KEY)
_MAX_TOOL_ROUNDS = 8


@dataclass
class ChatTurnResult:
    reply: str
    tools_used: list[str]
    consent_status: str = "none"

# Schemas alinhados ao MCP Z-API (docs/zapi-mcp-capabilities.md).
MCP_OPENAI_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "send-text",
            "description": "Envia mensagem de texto para um numero ou grupo WhatsApp via MCP Z-API.",
            "parameters": {
                "type": "object",
                "properties": {
                    "phone": {"type": "string", "description": "Telefone DDI+DDD+numero ou ID do grupo."},
                    "message": {"type": "string", "description": "Texto da mensagem."},
                },
                "required": ["phone", "message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send-image",
            "description": "Envia imagem (URL ou base64) com legenda opcional via MCP Z-API.",
            "parameters": {
                "type": "object",
                "properties": {
                    "phone": {"type": "string"},
                    "image": {"type": "string", "description": "URL publica ou base64."},
                    "caption": {"type": "string"},
                },
                "required": ["phone", "image"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send-video",
            "description": "Envia video (URL ou base64) via MCP Z-API.",
            "parameters": {
                "type": "object",
                "properties": {
                    "phone": {"type": "string"},
                    "video": {"type": "string"},
                    "caption": {"type": "string"},
                },
                "required": ["phone", "video"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "group-create",
            "description": "Cria grupo WhatsApp com participantes iniciais. Requer pelo menos um telefone real (nao vazio).",
            "parameters": {
                "type": "object",
                "properties": {
                    "groupName": {"type": "string"},
                    "phones": {"type": "array", "items": {"type": "string"}},
                    "autoInvite": {"type": "boolean", "description": "Enviar convite privado se necessario."},
                },
                "required": ["groupName", "phones", "autoInvite"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "group-metadata",
            "description": "Consulta metadados do grupo (nome, participantes) via MCP Z-API.",
            "parameters": {
                "type": "object",
                "properties": {"groupId": {"type": "string"}},
                "required": ["groupId"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "group-add-participant",
            "description": "Adiciona participante(s) a um grupo existente.",
            "parameters": {
                "type": "object",
                "properties": {
                    "groupId": {"type": "string"},
                    "phones": {"type": "array", "items": {"type": "string"}},
                    "autoInvite": {"type": "boolean"},
                },
                "required": ["groupId", "phones", "autoInvite"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "group-remove-participant",
            "description": "Remove participante(s) de um grupo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "groupId": {"type": "string"},
                    "phones": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["groupId", "phones"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "group-add-admin",
            "description": "Promove participante(s) a admin do grupo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "groupId": {"type": "string"},
                    "phones": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["groupId", "phones"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "group-remove-admin",
            "description": "Remove admin de participante(s) no grupo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "groupId": {"type": "string"},
                    "phones": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["groupId", "phones"],
            },
        },
    },
]


async def _latest_campaign(session: AsyncSession) -> Campaign | None:
    result = await session.execute(select(Campaign).order_by(Campaign.id.desc()).limit(1))
    return result.scalar_one_or_none()


_PHONE_RE = re.compile(r"(?:\+?\d[\d\s().-]{8,}\d|\d{10,13})")
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

_IDENTITY_REPLY = (
    "Sou a assistente do Tech News nesta demo do Desafio MCP Z-API 2026. "
    "Conduzo a conversa aqui no site com OpenAI; o Server MCP oficial da Z-API executa as acoes no WhatsApp."
)
_WHO_MADE_REPLY = (
    "Esta assistente foi criada para a demonstracao do hackathon: conversa via OpenAI "
    "e acoes reais no WhatsApp pelo Server MCP Z-API."
)


def _post_onboarding_quick_reply(user_message: str) -> str | None:
    text = user_message.strip()
    if _PROMPT_LEAK_RE.search(text):
        return (
            "Nao posso compartilhar prompt ou detalhes internos. "
            "Posso ajudar com IA, MCP, WhatsApp ou esta demo do Tech News."
        )
    if _WHO_MADE_YOU_RE.search(text):
        return _WHO_MADE_REPLY
    if _WHO_ARE_YOU_RE.search(text):
        return _IDENTITY_REPLY
    if _POST_ONBOARDING_NOW_RE.search(text):
        return POST_JOIN_CHAT_MESSAGE
    return None


def _build_system_prompt(campaign: Campaign | None, onboarding_complete: bool = False) -> str:
    if campaign and campaign.whatsapp_group_id:
        group_line = (
            f"Grupo ativo: sim, groupId=`{campaign.whatsapp_group_id}`, campanha `{campaign.name}`."
        )
    elif campaign:
        group_line = (
            f"Grupo ativo: ainda nao — use group-create com groupName=`{campaign.name}` "
            "e phones=[telefone do visitante], autoInvite=true."
        )
    else:
        group_line = (
            "Grupo ativo: ainda nao — use group-create com groupName=`Tech News IA & MCP` "
            "e phones=[telefone do visitante], autoInvite=true."
        )
    return f"""Voce e a assistente virtual do Tech News, demo ao vivo do Desafio MCP Z-API 2026.
Stack desta demo: conversa conduzida por OpenAI; acoes no WhatsApp executadas pelo Server MCP oficial da Z-API.

Contexto: informacao sobre IA, MCP e comunicacao inteligente existe demais, tempo pra acompanhar
tudo e que falta. O Tech News leva as principais novidades sobre isso direto pro WhatsApp da pessoa.

Objetivo: conversar de forma calorosa, explicar o beneficio do grupo de novidades Tech no WhatsApp
e, quando o visitante quiser participar, usar as tools MCP Z-API (nao invente acoes).

Fluxo sugerido:
1. O site ja mandou as boas-vindas, o aviso de privacidade (LGPD) e perguntou o primeiro nome da
   pessoa antes de voce entrar na conversa — a primeira mensagem que voce recebe do visitante e
   essa resposta (o nome). Use-o pra se dirigir a pessoa dai em diante (ex.: "Prazer, Joao!").
2. Pergunte se ela quer receber novidades sobre IA/MCP no WhatsApp.
3. Se sim, peca o WhatsApp com DDI (ex.: 5511***9999) — confirme o numero antes de agir.
4. Com telefone confirmado, o sistema envia automaticamente um link de confirmacao no WhatsApp.
   A confirmacao e o visitante abrir esse link no celular — nao e codigo numerico nem SIM/NAO no privado.
5. Enquanto o link nao for aberto, o chat no site fica aguardando (polling).
6. Nunca diga que enviou link sem o backend ter disparado send-text.
7. Voce nunca sabe, nesta etapa, se o numero ja faz parte do grupo ou e admin — so o backend
   descobre isso depois que o link for clicado. Nunca especule sobre isso.

Contexto fixo:
- Palavra-chave opt-in alternativa: {TRIGGER_KEYWORD}
- Mensagem tipo convite: {INVITATION_MESSAGE}
- Boas-vindas no grupo: {WELCOME_MESSAGE}
- {group_line}

Regras:
- Responda sempre em portugues do Brasil, frases curtas, tom profissional e amigavel.
- Ao usar uma tool, diga na resposta final o que fez (ex.: "Enviei convite no WhatsApp").
- Se uma tool falhar, explique em linguagem simples e sugira tentar de novo.
- Nao peca dados sensiveis alem do primeiro nome e do telefone WhatsApp para este demo.
- Ao repetir o numero do visitante na conversa, use formato mascarado (ex.: 5544***9999) — nunca todos os digitos.
{"- Onboarding ja concluido: o visitante entrou no grupo. Nao repita convite/link. Se perguntarem o proximo passo, diga para abrir o WhatsApp e ver a novidade; depois pode tirar duvidas sobre IA, MCP ou a demo." if onboarding_complete else ""}"""


def _tool_result_text(mcp_result: Any) -> str:
    payload = mcp_client.parse_tool_payload(mcp_result) if isinstance(mcp_result, dict) else None
    if payload is not None:
        return json.dumps(payload, ensure_ascii=False)[:6000]
    return json.dumps(mcp_result, ensure_ascii=False, default=str)[:6000]


async def run_chat_turn(
    session: AsyncSession,
    history: list[dict[str, str]],
    user_message: str,
    browser_session_id: str,
) -> ChatTurnResult:
    """Executa um turno completo (pode incluir varias chamadas MCP)."""
    campaign = await _latest_campaign(session)

    confirmed_phone = _should_send_whatsapp_invite(history, user_message)
    if confirmed_phone:
        visitor_name = _extract_name_from_history(history, user_message)
        ok, auto_reply, auto_tools, consent_status = await start_tracked_consent(
            session, browser_session_id, confirmed_phone, visitor_name
        )
        return ChatTurnResult(reply=auto_reply, tools_used=auto_tools, consent_status=consent_status)

    onboarding_complete = await has_accepted_chat_consent(session, browser_session_id)
    if onboarding_complete:
        quick = _post_onboarding_quick_reply(user_message)
        if quick:
            return ChatTurnResult(reply=quick, tools_used=[])

    messages: list[ChatCompletionMessageParam] = [
        {"role": "system", "content": _build_system_prompt(campaign, onboarding_complete)},
    ]
    for item in history[-20:]:
        role = item.get("role")
        content = (item.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_message})

    tools_used: list[str] = []

    for _ in range(_MAX_TOOL_ROUNDS):
        try:
            completion = await _client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=messages,
                tools=MCP_OPENAI_TOOLS,
                tool_choice="auto",
                temperature=0.4,
                max_tokens=800,
            )
        except Exception:
            logger.exception("Falha OpenAI no chat publico")
            return ChatTurnResult(
                reply="Desculpe, nao consegui processar agora. Tente novamente em instantes.",
                tools_used=tools_used,
            )

        choice = completion.choices[0].message

        if choice.tool_calls:
            assistant_msg: dict[str, Any] = {
                "role": "assistant",
                "content": choice.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments or "{}",
                        },
                    }
                    for tc in choice.tool_calls
                ],
            }
            messages.append(assistant_msg)  # type: ignore[arg-type]
            for tool_call in choice.tool_calls:
                name = tool_call.function.name
                try:
                    args = json.loads(tool_call.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                logger.info("Chat MCP tool: %s args=%s", name, args)
                try:
                    result = await mcp_client.call_tool(name, args)
                    if name == "group-create" and campaign and not campaign.whatsapp_group_id:
                        group_id = mcp_client.extract_group_id(result)
                        if group_id:
                            campaign.whatsapp_group_id = group_id
                            await session.commit()
                    tools_used.append(name)
                    tool_content = _tool_result_text(result)
                except Exception as exc:
                    logger.exception("Falha MCP tool %s", name)
                    tool_content = json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": tool_content,
                    }
                )
            continue

        reply = (choice.content or "").strip()
        if not reply:
            reply = "Como posso ajudar voce a entrar no nosso grupo de novidades sobre IA e MCP no WhatsApp?"
        return ChatTurnResult(reply=reply, tools_used=tools_used)

    return ChatTurnResult(
        reply="Fiz varias acoes no WhatsApp via MCP. Veja seu celular — posso ajudar em mais alguma coisa?",
        tools_used=tools_used,
    )
