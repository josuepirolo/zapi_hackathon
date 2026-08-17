"""Interpretacao de intencao (SIM/NAO/linguagem natural) e geracao de imagem
promocional via OpenAI API.

Unico ponto de import do SDK da OpenAI do projeto - ver
`.sdds/harness/consentimento-grupo.harness.md`, secao 8 (Centralizacao).

`OPENAI_MODEL` (default `gpt-4o-mini`, ver `.sdds/TECH_STACK.md` -
A_CONFIRMAR_OPERACIONAL, o usuario so confirmou o provider OpenAI, nao o
modelo exato) e configuravel via variavel de ambiente sem mudar codigo.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from io import BytesIO
from pathlib import Path
from typing import Literal

from openai import AsyncOpenAI
from PIL import Image

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
_NEWS_IMAGE_MAX_PX = 1024
_NEWS_IMAGE_JPEG_QUALITY = 82


def _sanitize_news_id(news_id: str) -> str:
    return "".join(ch for ch in news_id if ch.isalnum() or ch in "-_")


def _news_image_path(news_id: str, ext: str = "jpg") -> Path:
    return NEWS_ASSETS_DIR / f"{_sanitize_news_id(news_id)}.{ext}"


def _find_news_image_path(news_id: str) -> Path | None:
    safe = _sanitize_news_id(news_id)
    for name in (f"{safe}.jpg", f"{safe}.jpeg", f"{safe}.png"):
        path = NEWS_ASSETS_DIR / name
        if path.is_file():
            return path
    return None


def _compress_news_image(content: bytes) -> tuple[bytes, str]:
    """Redimensiona e comprime para JPEG leve (WhatsApp / fetch MCP)."""
    original = len(content)
    img = Image.open(BytesIO(content))
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1])
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")

    width, height = img.size
    max_side = max(width, height)
    if max_side > _NEWS_IMAGE_MAX_PX:
        scale = _NEWS_IMAGE_MAX_PX / max_side
        img = img.resize(
            (max(1, int(width * scale)), max(1, int(height * scale))),
            Image.Resampling.LANCZOS,
        )

    buf = BytesIO()
    img.save(buf, format="JPEG", quality=_NEWS_IMAGE_JPEG_QUALITY, optimize=True, progressive=True)
    data = buf.getvalue()
    logger.info(
        "Imagem da noticia comprimida %d -> %d bytes (max %dpx, q=%d)",
        original,
        len(data),
        _NEWS_IMAGE_MAX_PX,
        _NEWS_IMAGE_JPEG_QUALITY,
    )
    return data, "jpg"


def _remove_stale_news_images(news_id: str, keep_ext: str) -> None:
    safe = _sanitize_news_id(news_id)
    for ext in ("png", "jpg", "jpeg"):
        if ext == keep_ext:
            continue
        path = NEWS_ASSETS_DIR / f"{safe}.{ext}"
        if path.is_file():
            path.unlink(missing_ok=True)


async def _write_news_image(news_id: str, content: bytes) -> Path:
    compressed, ext = await asyncio.to_thread(_compress_news_image, content)
    _remove_stale_news_images(news_id, ext)
    path = _news_image_path(news_id, ext)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(compressed)
    return path


def news_image_public_url(news_id: str) -> str:
    """URL publica (com ?v= para bust de cache no browser)."""
    path = _find_news_image_path(news_id)
    safe_id = _sanitize_news_id(news_id)
    if path is None:
        return f"{PUBLIC_BASE_URL}/assets/news/{safe_id}.jpg"
    base = f"{PUBLIC_BASE_URL}/assets/news/{path.name}"
    return f"{base}?v={int(path.stat().st_mtime)}"


def news_image_mcp_url(news_id: str) -> str | None:
    """URL limpa para send-image — Z-API rejeita query string (?v=) com 400."""
    path = _find_news_image_path(news_id)
    if path is None:
        return None
    return f"{PUBLIC_BASE_URL}/assets/news/{path.name}"


def news_image_data_uri(news_id: str) -> str | None:
    """Base64 com prefixo data: — fallback se fetch da URL falhar no Z-API."""
    path = _find_news_image_path(news_id)
    if path is None:
        return None
    raw = base64.b64encode(path.read_bytes()).decode("ascii")
    mime = "image/jpeg" if path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
    return f"data:{mime};base64,{raw}"


async def ensure_news_image_file(news_id: str, prompt: str) -> bool:
    """Garante imagem no disco (cache local comprimido ou geracao OpenAI)."""
    existing = _find_news_image_path(news_id)
    if existing is not None:
        if existing.suffix.lower() == ".png":
            try:
                await _write_news_image(news_id, existing.read_bytes())
            except OSError:
                logger.exception("Falha ao recomprimir PNG legado da noticia %s", news_id)
        else:
            logger.info("Imagem da noticia %s carregada do cache", news_id)
        return True

    b64 = await _generate_image_base64(prompt)
    if b64 is None:
        return False

    try:
        path = await _write_news_image(news_id, base64.b64decode(b64))
        logger.info("Imagem da noticia %s gerada e salva em %s", news_id, path)
        return True
    except OSError:
        logger.exception("Falha ao salvar cache da imagem %s", news_id)
        return False


async def resolve_news_image_url(news_id: str, prompt: str) -> str | None:
    """Retorna URL limpa para MCP se existir ou puder ser gerada."""
    if await ensure_news_image_file(news_id, prompt):
        return news_image_mcp_url(news_id)
    return None


async def save_news_image_bytes(news_id: str, content: bytes) -> Path:
    """Persiste imagem enviada manualmente (upload), comprimida para JPEG."""
    if len(content) > 5 * 1024 * 1024:
        raise ValueError("Imagem maior que 5 MB")
    path = await _write_news_image(news_id, content)
    logger.info(
        "Imagem da noticia %s salva via upload em %s (%d bytes)",
        news_id,
        path,
        path.stat().st_size,
    )
    return path


async def get_cached_news_image_base64(news_id: str, prompt: str) -> str | None:
    """Legado — preferir `resolve_news_image_url` (evita 413 no MCP com base64 grande)."""
    if not await ensure_news_image_file(news_id, prompt):
        return None
    path = _find_news_image_path(news_id)
    if path is None:
        return None
    return base64.b64encode(path.read_bytes()).decode("ascii")


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
