"""Publicacao da novidade do dia no grupo via MCP.

Envio em duas etapas (mais confiavel no WhatsApp): `send-image` sem legenda,
depois `send-text` com o texto completo da noticia.
"""

from __future__ import annotations

import logging

from app import mcp_client
from app.ai import news_image_data_uri, resolve_news_image_url
from app.news_content import DEFAULT_GROUP_NEWS

logger = logging.getLogger("delega.group_news")


async def send_group_news(group_id: str) -> list[str]:
    """Publica a news do dia. Retorna as tools MCP efetivamente usadas."""
    news = DEFAULT_GROUP_NEWS
    tools_used: list[str] = []

    image_url = await resolve_news_image_url(news.id, news.image_prompt)

    if image_url is not None:
        sent_image = False
        try:
            result = await mcp_client.call_tool(
                "send-image",
                {"phone": group_id, "image": image_url},
            )
            if mcp_client.tool_call_succeeded(result):
                tools_used.append("send-image")
                sent_image = True
                logger.info("send-image noticia %s via URL %s", news.id, image_url)
            else:
                logger.warning(
                    "send-image URL falhou noticia %s no grupo %s (url=%s): %r",
                    news.id,
                    group_id,
                    image_url,
                    result,
                )
        except Exception:
            logger.exception("Falha send-image URL da noticia no grupo %s url=%s", group_id, image_url)

        if not sent_image:
            data_uri = news_image_data_uri(news.id)
            if data_uri:
                try:
                    result = await mcp_client.call_tool(
                        "send-image",
                        {"phone": group_id, "image": data_uri},
                    )
                    if mcp_client.tool_call_succeeded(result):
                        tools_used.append("send-image")
                        logger.info("send-image noticia %s via base64 fallback (~%d bytes)", news.id, len(data_uri))
                    else:
                        logger.warning(
                            "send-image base64 falhou noticia %s no grupo %s: %r",
                            news.id,
                            group_id,
                            result,
                        )
                except Exception:
                    logger.exception("Falha send-image base64 da noticia no grupo %s", group_id)
            else:
                logger.warning("Sem data URI para fallback send-image noticia %s", news.id)
    else:
        logger.warning(
            "Sem imagem da noticia %s — envie via POST /api/news-assets/%s ou aguarde geracao OpenAI.",
            news.id,
            news.id,
        )

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
