"""Agente de chat publico: OpenAI + tools MCP Z-API oficial.

Demonstracao hackathon — visitante conversa na pagina; a IA decide quando
chamar cada uma das 9 tools via `app.mcp_client`.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import mcp_client
from app.campaign_defaults import INVITATION_MESSAGE, TRIGGER_KEYWORD, WELCOME_MESSAGE
from app.config import OPENAI_API_KEY, OPENAI_MODEL
from app.models import Campaign

logger = logging.getLogger("delega.chat_agent")

_client = AsyncOpenAI(api_key=OPENAI_API_KEY)
_MAX_TOOL_ROUNDS = 8

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


def _build_system_prompt(campaign: Campaign | None) -> str:
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
            "Grupo ativo: ainda nao — use group-create com groupName=`Promocoes Z-API` "
            "e phones=[telefone do visitante], autoInvite=true."
        )
    return f"""Voce e a assistente virtual de promocoes do desafio MCP Z-API (demo ao vivo).

Objetivo: conversar de forma calorosa, explicar beneficios do grupo de promocoes no WhatsApp
e, quando o visitante quiser participar, usar as tools MCP Z-API (nao invente acoes).

Fluxo sugerido:
1. Apresente-se e pergunte se a pessoa quer receber novidades/promocoes no WhatsApp.
2. Se sim, peca o WhatsApp com DDI (ex.: 5511999999999) — confirme antes de agir.
3. Com telefone confirmado:
   - Se ja existe grupo: prefira group-add-participant com groupId abaixo.
   - Se nao existe grupo: group-create com groupName da campanha e phones=[telefone], autoInvite=true.
   - Envie send-text privado explicando proximo passo (palavra-chave ou convite).
4. Nunca envie spam; so chame tools quando o visitante concordar explicitamente.

Contexto fixo:
- Palavra-chave opt-in alternativa: {TRIGGER_KEYWORD}
- Mensagem tipo convite: {INVITATION_MESSAGE}
- Boas-vindas no grupo: {WELCOME_MESSAGE}
- {group_line}

Regras:
- Responda sempre em portugues do Brasil, frases curtas, tom profissional e amigavel.
- Ao usar uma tool, diga na resposta final o que fez (ex.: "Enviei convite no WhatsApp").
- Se uma tool falhar, explique em linguagem simples e sugira tentar de novo.
- Nao peca dados sensiveis alem do telefone WhatsApp para este demo."""


def _tool_result_text(mcp_result: Any) -> str:
    payload = mcp_client.parse_tool_payload(mcp_result) if isinstance(mcp_result, dict) else None
    if payload is not None:
        return json.dumps(payload, ensure_ascii=False)[:6000]
    return json.dumps(mcp_result, ensure_ascii=False, default=str)[:6000]


async def run_chat_turn(
    session: AsyncSession,
    history: list[dict[str, str]],
    user_message: str,
) -> tuple[str, list[str]]:
    """Executa um turno completo (pode incluir varias chamadas MCP)."""
    campaign = await _latest_campaign(session)
    messages: list[ChatCompletionMessageParam] = [
        {"role": "system", "content": _build_system_prompt(campaign)},
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
            return (
                "Desculpe, nao consegui processar agora. Tente novamente em instantes.",
                tools_used,
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
            reply = "Como posso ajudar voce com nossas promocoes no WhatsApp?"
        return reply, tools_used

    return (
        "Fiz varias acoes no WhatsApp via MCP. Veja seu celular — posso ajudar em mais alguma coisa?",
        tools_used,
    )
