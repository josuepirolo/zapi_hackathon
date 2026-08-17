"""Publicacao da novidade do dia no grupo via MCP.

Envio em duas etapas (mais confiavel no WhatsApp): `send-image` (URL publica)
depois `send-text` com o texto completo da noticia. Sem base64 no MCP (413).
"""

from __future__ import annotations

import logging

import httpx

from app import mcp_client
from app.ai import resolve_news_image_url
from app.news_content import DEFAULT_GROUP_NEWS

logger = logging.getLogger("delega.group_news")


async def _verify_public_image_url(url: str) -> bool:
    """Confere se a URL responde 200 antes do Z-API tentar baixar."""
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(url)
        content_type = (resp.headers.get("content-type") or "").lower()
        if resp.status_code == 200 and content_type.startswith("image/"):
            return True
        logger.warning(
            "URL da imagem inacessivel (status=%s type=%s url=%s)",
            resp.status_code,
            content_type or "—",
            url,
        )
    except Exception:
        logger.exception("Falha ao verificar URL publica da imagem %s", url)
    return False


async def send_group_news(group_id: str) -> list[str]:
    """Publica a news do dia. Retorna as tools MCP efetivamente usadas."""
    news = DEFAULT_GROUP_NEWS
    tools_used: list[str] = []

    image_url = await resolve_news_image_url(news.id, news.image_prompt)

    if image_url is None:
        logger.warning(
            "Sem imagem da noticia %s — envie via POST /api/news-assets/%s",
            news.id,
            news.id,
        )
    elif not await _verify_public_image_url(image_url):
        logger.warning(
            "send-image ignorado: URL da noticia %s nao respondeu 200 (%s)",
            news.id,
            image_url,
        )
    else:
        try:
            result = await mcp_client.call_tool(
                "send-image",
                {"phone": group_id, "image": image_url},
            )
            if mcp_client.tool_call_succeeded(result):
                tools_used.append("send-image")
                logger.info("send-image noticia %s via URL %s", news.id, image_url)
            else:
                logger.warning(
                    "send-image recusou noticia %s no grupo %s (url=%s): %r",
                    news.id,
                    group_id,
                    image_url,
                    result,
                )
        except Exception:
            logger.exception("Falha send-image da noticia no grupo %s url=%s", group_id, image_url)

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
