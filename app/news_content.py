"""Conteudo de novidades publicadas no grupo Tech News.

Cada item tem um `id` estavel — a imagem gerada pela OpenAI e cacheada em
`NEWS_ASSETS_DIR / {id}.png` para nao regerar a cada entrada no grupo.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GroupNewsItem:
    id: str
    url: str
    caption: str
    image_prompt: str


ZAPI_MCP_INTRO = GroupNewsItem(
    id="zapi-mcp-intro",
    url="https://developer.z-api.io/mcp/introduction",
    caption=(
        "📰 Novidade no ar — Z-API + MCP Server!\n\n"
        "*A API mais estavel e intuitiva agora tem servidor MCP para facilitar* "
        "a comunicacao entre sua LLM preferida e seu WhatsApp.\n\n"
        "Saiba mais: https://developer.z-api.io/mcp/introduction"
    ),
    image_prompt=(
        "Modern flat infographic explaining Model Context Protocol (MCP): "
        "a glowing AI assistant connected via plug-like connectors to external "
        "tools — include WhatsApp and API/server icons. Clean tech illustration, "
        "blue and teal palette, minimal, absolutely no text or letters in the image."
    ),
)

DEFAULT_GROUP_NEWS = ZAPI_MCP_INTRO
