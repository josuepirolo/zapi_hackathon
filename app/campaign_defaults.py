"""Textos fixos do fluxo de consentimento — nao configuraveis pelo admin.

O painel so cria/exclui campanhas e dispara acoes MCP pro checklist; as
mensagens do fluxo (landing → keyword → convite → boas-vindas) ficam aqui.
"""

from __future__ import annotations

TRIGGER_KEYWORD = "#desafiozapi"

LANDING_DESCRIPTION = (
    "Receba ofertas e novidades exclusivas direto no WhatsApp — entre no grupo com um clique."
)

INVITATION_MESSAGE = (
    "Ola! Voce pediu para entrar no nosso grupo de promocoes. "
    "Posso te adicionar? (responda SIM ou NAO)"
)

WELCOME_MESSAGE = (
    "Bem-vindo(a) ao grupo! Em breve teremos novidades e ofertas exclusivas por aqui."
)

ALREADY_MEMBER_MESSAGE = (
    "Voce ja faz parte do nosso grupo! Que bom ter voce conosco. "
    "Em breve teremos novidades por la — fique de olho!"
)

DEMO_GROUP_MESSAGE = "Novidade no ar! Fique de olho nas proximas promocoes do grupo."
