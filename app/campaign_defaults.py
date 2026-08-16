"""Textos fixos do fluxo de consentimento — nao configuraveis pelo admin.

O painel so cria/exclui campanhas e dispara acoes MCP pro checklist; as
mensagens do fluxo (landing → keyword → convite → boas-vindas) ficam aqui.

Storytelling (ver CONTEXTO_HACKATHON_FINAL.md): Tech News IA & MCP - grupo
de novidades sobre IA, MCP e comunicacao inteligente, nao promocoes/ofertas.
"""

from __future__ import annotations

TRIGGER_KEYWORD = "#desafiozapi"

LANDING_DESCRIPTION = (
    "Novidades sobre IA, MCP e o futuro da comunicação inteligente, direto no seu WhatsApp — entre com um clique."
)

INVITATION_MESSAGE = (
    "Ola! Voce pediu para entrar no nosso grupo de novidades Tech (IA, MCP e comunicacao inteligente). "
    "Posso te adicionar? (responda SIM ou NAO)"
)

WELCOME_MESSAGE = (
    "Bem-vindo(a) ao Tech News! Em breve vamos trazer as principais novidades sobre IA, MCP e comunicacao inteligente por aqui."
)

ALREADY_MEMBER_MESSAGE = (
    "Voce ja faz parte do nosso grupo de novidades Tech! Que bom ter voce conosco. "
    "Fique de olho nas proximas novidades sobre IA e MCP."
)

DEMO_GROUP_MESSAGE = "Novidade no ar! Fique de olho nas proximas atualizacoes sobre IA e MCP no grupo."
