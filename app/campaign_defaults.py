"""Textos fixos do fluxo de consentimento — nao configuraveis pelo admin.

O painel so cria/exclui campanhas e dispara acoes MCP pro checklist; as
mensagens do fluxo (landing → keyword → convite → boas-vindas) ficam aqui.

Storytelling (ver CONTEXTO_HACKATHON_FINAL.md): Tech News IA & MCP - grupo
de novidades sobre IA, MCP e comunicacao inteligente, nao promocoes/ofertas.
"""

from __future__ import annotations

TRIGGER_KEYWORD = "#desafiozapi"

GROUP_NAME_PREFIX = "Tech News IA & MCP"

INSTANCE_PHONE_BLOCKED_MESSAGE = (
    "Esse e o numero conectado a instancia Z-API desta demonstracao — voce e o admin. "
    "O grupo pessoal nao pode ser criado com o mesmo WhatsApp da instancia. "
    "Para a apresentacao, informe outro celular com DDI (ex.: de quem vai participar da demo)."
)

LANDING_DESCRIPTION = (
    "Novidades sobre IA, MCP e o futuro da comunicação inteligente, direto no seu WhatsApp — entre com um clique."
)

INVITATION_MESSAGE = (
    "Ola! Voce pediu para entrar no nosso grupo de novidades Tech (IA, MCP e comunicacao inteligente). "
    "Posso te adicionar? (responda SIM ou NAO)"
)

WELCOME_MESSAGE = (
    "Bem-vindo(a) ao seu grupo Tech News! Seu espaco exclusivo foi criado — "
    "em instantes a primeira novidade do dia aparece por la."
)

ALREADY_MEMBER_MESSAGE = (
    "Voce ja faz parte do nosso grupo de novidades Tech! Acabei de publicar a novidade de hoje la — "
    "confira no WhatsApp."
)

ADMIN_ALREADY_MEMBER_MESSAGE = (
    "Esse numero ja e administrador do nosso grupo de novidades Tech! "
    "A novidade de hoje foi publicada no grupo — confira la."
)

DEMO_GROUP_MESSAGE = (
    "📰 Novidade no ar — Z-API + MCP Server!\n\n"
    "*A API mais estavel e intuitiva agora tem servidor MCP para facilitar* "
    "a comunicacao entre sua LLM preferida e seu WhatsApp.\n\n"
    "Saiba mais: https://developer.z-api.io/mcp/introduction"
)

JOINED_MESSAGE = (
    "Tudo pronto! Voce ja esta no grupo Tech News e a primeira novidade foi enviada no seu WhatsApp. 🚀"
)

POST_JOIN_CHAT_MESSAGE = (
    "Abra seu WhatsApp agora — a novidade ja esta la. 📱 "
    "Depois disso, pode me perguntar sobre IA, MCP ou esta demo."
)
