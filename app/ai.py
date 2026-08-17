"""Interpretacao de intencao (SIM/NAO/linguagem natural) e geracao de imagem
promocional via OpenAI API.

Unico ponto de import do SDK da OpenAI do projeto - ver
`.sdds/harness/consentimento-grupo.harness.md`, secao 8 (Centralizacao).

`OPENAI_MODEL` (default `gpt-4o-mini`, ver `.sdds/TECH_STACK.md` -
A_CONFIRMAR_OPERACIONAL, o usuario so confirmou o provider OpenAI, nao o
modelo exato) e configuravel via variavel de ambiente sem mudar codigo.
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Literal

from openai import AsyncOpenAI

from app.config import NEWS_ASSETS_DIR, OPENAI_API_KEY, OPENAI_MODEL, PUBLIC_BASE_URL

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


# Confirmado contra doc oficial OpenAI (2026-08-16): `gpt-image-2` exige
# >= 655360 pixels — `512x512` retorna 400 "below minimum pixel budget".
_IMAGE_MODEL = "gpt-image-2"


def _sanitize_news_id(news_id: str) -> str:
    return "".join(ch for ch in news_id if ch.isalnum() or ch in "-_")


def _news_image_path(news_id: str) -> Path:
    return NEWS_ASSETS_DIR / f"{_sanitize_news_id(news_id)}.png"


def news_image_public_url(news_id: str) -> str:
    """URL publica servida por GET /assets/news/{id}.png — Z-API send-image aceita link."""
    safe_id = _sanitize_news_id(news_id)
    base = f"{PUBLIC_BASE_URL}/assets/news/{safe_id}.png"
    path = _news_image_path(news_id)
    if path.is_file():
        # ?v= evita CDN servir PNG antigo apos upload (Cloudflare cacheia URL sem query).
        return f"{base}?v={int(path.stat().st_mtime)}"
    return base


async def ensure_news_image_file(news_id: str, prompt: str) -> bool:
    """Garante PNG no disco (cache local ou geracao OpenAI)."""
    path = _news_image_path(news_id)
    if path.is_file():
        logger.info("Imagem da noticia %s carregada do cache (%s)", news_id, path)
        return True

    b64 = await _generate_image_base64(prompt)
    if b64 is None:
        return False

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(base64.b64decode(b64))
        logger.info("Imagem da noticia %s gerada e salva em %s", news_id, path)
        return True
    except OSError:
        logger.exception("Falha ao salvar cache da imagem %s em %s", news_id, path)
        return False


async def resolve_news_image_url(news_id: str, prompt: str) -> str | None:
    """Retorna URL publica da imagem se existir ou puder ser gerada."""
    if await ensure_news_image_file(news_id, prompt):
        return news_image_public_url(news_id)
    return None


async def save_news_image_bytes(news_id: str, content: bytes) -> Path:
    """Persiste PNG enviado manualmente (upload)."""
    if len(content) > 5 * 1024 * 1024:
        raise ValueError("Imagem maior que 5 MB")
    path = _news_image_path(news_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    logger.info("Imagem da noticia %s salva via upload em %s (%d bytes)", news_id, path, len(content))
    return path


async def get_cached_news_image_base64(news_id: str, prompt: str) -> str | None:
    """Legado — preferir `resolve_news_image_url` (evita 413 no MCP com base64 grande)."""
    if not await ensure_news_image_file(news_id, prompt):
        return None
    return base64.b64encode(_news_image_path(news_id).read_bytes()).decode("ascii")


async def _generate_image_base64(prompt: str) -> str | None:
    try:
        result = await _client.images.generate(
            model=_IMAGE_MODEL,
            prompt=prompt,
            size="1024x1024",
            quality="low",
        )
        b64 = result.data[0].b64_json
        if not b64:
            logger.error("OpenAI retornou imagem sem b64_json (modelo=%s)", _IMAGE_MODEL)
            return None
        return b64
    except Exception:
        logger.exception("Falha ao gerar imagem via OpenAI (modelo=%s)", _IMAGE_MODEL)
        return None


async def generate_promo_image_base64() -> str | None:
    """Compatibilidade — preferir `resolve_news_image_url`."""
    from app.news_content import DEFAULT_GROUP_NEWS

    return await get_cached_news_image_base64(DEFAULT_GROUP_NEWS.id, DEFAULT_GROUP_NEWS.image_prompt)
