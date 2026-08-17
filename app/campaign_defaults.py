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
    "Tudo pronto! Enviei o link do seu grupo Tech News no WhatsApp — toque nele para abrir direto. "
    "A novidade do dia tambem ja foi publicada la. 🚀"
)

GROUP_ACCESS_LINK_DM = (
    "Acesse seu grupo *{group_name}* por aqui:\n{link}\n\n"
    "Toque no link para abrir direto no WhatsApp."
)

POST_JOIN_CHAT_MESSAGE = (
    "Abra seu WhatsApp agora — a novidade ja esta la. 📱 "
    "Depois disso, pode me perguntar sobre IA, MCP ou esta demo."
)

LEAVE_GROUP_ASK = (
    "Tem certeza que quer sair do grupo *{group_name}* e encerrar sua participacao nesta demo? "
    "Responda SIM ou NAO."
)

LEAVE_LINK_DM = (
    "Voce pediu sair do grupo *{group_name}* da demo Tech News.\n\n"
    "Toque no link para confirmar a saida:\n{link}\n\n"
    "O link expira em {minutes} minutos."
)

LEAVE_LINK_CHAT_REPLY = (
    "Enviei um link de confirmacao de saida no WhatsApp para {masked}. "
    "Abra a mensagem no celular, toque no link e confirme — vou aguardar aqui ate voce confirmar."
)

LEAVE_GROUP_SUCCESS = (
    "Pronto — voce foi removido do grupo *{group_name}*. "
    "Enviei a confirmacao no seu WhatsApp. Para entrar de novo, e so pedir aqui no chat."
)

LEAVE_GROUP_FAILED = (
    "Nao consegui te remover do grupo agora. Tente de novo em instantes ou diga "
    "\"quero sair do grupo\" outra vez."
)

LEAVE_ALREADY_GONE = (
    "Voce ja nao esta no grupo *{group_name}*. Para entrar de novo, diga que quer participar e informe seu WhatsApp."
)
