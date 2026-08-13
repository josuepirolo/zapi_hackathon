"""Interpretacao de intencao (SIM/NAO/linguagem natural) e geracao de imagem
promocional via OpenAI API.

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


# Prompt fixo e controlado (nao aceita input do usuario/webhook) - evita
# prompt injection via geracao de imagem. Confirmado contra a doc oficial
# da OpenAI (2026-08-13, developers.openai.com/api/docs/guides/image-generation)
# antes de implementar: client.images.generate(model="gpt-image-2", ...,
# response_format="b64_json") retorna base64 direto, sem precisar hospedar
# a imagem em lugar nenhum - `send-image` do MCP aceita base64 no campo
# `image`.
_PROMO_IMAGE_PROMPT = (
    "Banner promocional vibrante e moderno para um grupo de ofertas no "
    "WhatsApp. Estilo flat design, cores vivas (verde e dourado), "
    "elementos de compras/promocao, sem nenhum texto ou letras na imagem."
)
_IMAGE_MODEL = "gpt-image-2"


async def generate_promo_image_base64() -> str | None:
    """Gera a imagem promocional padrao e retorna como string base64
    (`b64_json`), pronta pra usar direto no `send-image` do MCP.
    `None` em qualquer falha - o chamador decide como reagir."""
    try:
        result = await _client.images.generate(
            model=_IMAGE_MODEL,
            prompt=_PROMO_IMAGE_PROMPT,
            size="1024x1024",
            quality="medium",
            response_format="b64_json",
        )
        return result.data[0].b64_json
    except Exception:
        logger.exception("Falha ao gerar imagem promocional via OpenAI")
        return None
