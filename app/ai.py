"""Interpretacao de intencao (SIM/NAO/linguagem natural) via OpenAI API.

Unico ponto de import do SDK da OpenAI do projeto - ver
`.sdds/harness/consentimento-grupo.harness.md`, secao 8 (Centralizacao).

`OPENAI_MODEL` (default `gpt-4o-mini`, ver `.sdds/TECH_STACK.md` -
A_CONFIRMAR_OPERACIONAL, o usuario so confirmou o provider OpenAI, nao o
modelo exato) e configuravel via variavel de ambiente sem mudar codigo.
"""

from __future__ import annotations

import logging
from typing import Literal

from openai import AsyncOpenAI

from app.config import OPENAI_API_KEY, OPENAI_MODEL

logger = logging.getLogger("delega.ai")

Intent = Literal["ACCEPT", "DECLINE", "UNCLEAR"]
_VALID_INTENTS: set[str] = {"ACCEPT", "DECLINE", "UNCLEAR"}

_client = AsyncOpenAI(api_key=OPENAI_API_KEY)

_SYSTEM_PROMPT = (
    "Voce classifica a resposta de uma pessoa a um convite para participar "
    "de um grupo de WhatsApp. Responda com EXATAMENTE uma palavra: "
    "ACCEPT se a pessoa aceitar (ex.: 'sim', 'quero entrar', 'pode me colocar', 'tenho interesse'), "
    "DECLINE se recusar (ex.: 'nao', 'agora nao', 'prefiro nao participar'), "
    "ou UNCLEAR se a resposta nao permitir concluir com seguranca. "
    "Nunca responda outra coisa alem de ACCEPT, DECLINE ou UNCLEAR."
)


async def interpret_intent(texto: str) -> Intent:
    """Classifica a resposta do interessado. Falha/ambiguidade -> UNCLEAR (RN-004)."""
    try:
        completion = await _client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": texto},
            ],
            max_tokens=5,
            temperature=0,
        )
        raw = (completion.choices[0].message.content or "").strip().upper()
    except Exception:
        logger.exception("Falha ao chamar OpenAI para interpret_intent")
        return "UNCLEAR"

    if raw not in _VALID_INTENTS:
        logger.warning("Resposta inesperada da OpenAI para interpret_intent: %r", raw)
        return "UNCLEAR"
    return raw  # type: ignore[return-value]


Confirmation = Literal["YES", "NO", "UNCLEAR"]
_VALID_CONFIRMATIONS: set[str] = {"YES", "NO", "UNCLEAR"}

_CONFIRMATION_SYSTEM_PROMPT = (
    "Voce classifica a resposta de uma pessoa a uma pergunta de confirmacao "
    "SIM/NAO generica (nao necessariamente sobre entrar em algo). Responda "
    "com EXATAMENTE uma palavra: YES se a pessoa confirmar, NO se negar, "
    "ou UNCLEAR se a resposta nao permitir concluir com seguranca. "
    "Nunca responda outra coisa alem de YES, NO ou UNCLEAR."
)


async def interpret_confirmation(texto: str) -> Confirmation:
    """Classificador SIM/NAO generico - usado por fluxos de confirmacao que
    nao sao o convite inicial de entrada (ex.: confirmar saida de grupo,
    #sairgrupozapi). Falha/ambiguidade -> UNCLEAR, mesmo principio do
    `interpret_intent` (RN-004): nunca assumir confirmacao por erro do LLM."""
    try:
        completion = await _client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": _CONFIRMATION_SYSTEM_PROMPT},
                {"role": "user", "content": texto},
            ],
            max_tokens=5,
            temperature=0,
        )
        raw = (completion.choices[0].message.content or "").strip().upper()
    except Exception:
        logger.exception("Falha ao chamar OpenAI para interpret_confirmation")
        return "UNCLEAR"

    if raw not in _VALID_CONFIRMATIONS:
        logger.warning("Resposta inesperada da OpenAI para interpret_confirmation: %r", raw)
        return "UNCLEAR"
    return raw  # type: ignore[return-value]
