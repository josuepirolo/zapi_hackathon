"""Publicacao da novidade do dia no grupo via MCP.

Envio em duas etapas (mais confiavel no WhatsApp): `send-image` sem legenda,
depois `send-text` com o texto completo da noticia.
"""

from __future__ import annotations

import logging

from app import mcp_client
from app.ai import get_cached_news_image_base64
from app.news_content import DEFAULT_GROUP_NEWS

logger = logging.getLogger("delega.group_news")


async def send_group_news(group_id: str) -> list[str]:
    """Publica a news do dia. Retorna as tools MCP efetivamente usadas."""
    news = DEFAULT_GROUP_NEWS
    tools_used: list[str] = []

    image_b64 = await get_cached_news_image_base64(news.id, news.image_prompt)
    if image_b64 is not None:
        try:
            result = await mcp_client.call_tool(
                "send-image",
                {"phone": group_id, "image": image_b64},
            )
            if mcp_client.tool_call_succeeded(result):
                tools_used.append("send-image")
            else:
                logger.warning(
                    "send-image recusou noticia %s no grupo %s: %r",
                    news.id,
                    group_id,
                    result,
                )
        except Exception:
            logger.exception("Falha send-image da noticia no grupo %s", group_id)
    else:
        logger.warning("Falha ao obter imagem da noticia %s — so legenda via send-text.", news.id)

    try:
        result = await mcp_client.call_tool(
            "send-text",
            {"phone": group_id, "message": news.caption},
        )
        if mcp_client.tool_call_succeeded(result):
            tools_used.append("send-text")
        else:
            logger.warning(
                "send-text da noticia recusou no grupo %s: %r",
                group_id,
                result,
            )
    except Exception:
        logger.exception("Falha send-text da noticia no grupo %s", group_id)

    return tools_used
