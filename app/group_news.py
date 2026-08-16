"""Publicacao da novidade do dia no grupo via MCP (`send-image` + legenda)."""

from __future__ import annotations

import logging

from app import mcp_client
from app.ai import get_cached_news_image_base64
from app.news_content import DEFAULT_GROUP_NEWS

logger = logging.getLogger("delega.group_news")


async def send_group_news(group_id: str) -> None:
    """Primeira news do dia: imagem cacheada + legenda com link Z-API MCP."""
    news = DEFAULT_GROUP_NEWS
    image_b64 = await get_cached_news_image_base64(news.id, news.image_prompt)
    if image_b64 is None:
        logger.warning("Falha ao obter imagem da noticia %s - fallback send-text no grupo.", news.id)
        try:
            await mcp_client.call_tool("send-text", {"phone": group_id, "message": news.caption})
        except Exception:
            logger.exception("Falha no fallback send-text da noticia no grupo %s", group_id)
        return
    try:
        await mcp_client.call_tool(
            "send-image",
            {"phone": group_id, "image": image_b64, "caption": news.caption},
        )
    except Exception:
        logger.exception("Falha ao enviar imagem da noticia via MCP no grupo %s", group_id)
        try:
            await mcp_client.call_tool("send-text", {"phone": group_id, "message": news.caption})
        except Exception:
            logger.exception("Falha no fallback send-text da noticia no grupo %s", group_id)
