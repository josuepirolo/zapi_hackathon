"""Assets de noticias — servir PNG publico e upload manual."""

from __future__ import annotations

import logging

from fastapi import APIRouter, File, Header, HTTPException, UploadFile
from pydantic import BaseModel

from app.ai import news_image_public_url, save_news_image_bytes, _find_news_image_path
from app.config import WEBHOOK_SHARED_SECRET
from app.news_content import DEFAULT_GROUP_NEWS

logger = logging.getLogger("delega.news_assets")

router = APIRouter(prefix="/api", tags=["news-assets"])


class NewsAssetUploadResponse(BaseModel):
    ok: bool
    news_id: str
    url: str
    bytes: int


def _validate_news_id(news_id: str) -> str:
    cleaned = "".join(ch for ch in news_id.strip() if ch.isalnum() or ch in "-_")
    if not cleaned or len(cleaned) > 64:
        raise HTTPException(status_code=400, detail="news_id invalido")
    return cleaned


@router.post("/news-assets/{news_id}", response_model=NewsAssetUploadResponse)
async def upload_news_asset(
    news_id: str,
    file: UploadFile = File(...),
    x_webhook_secret: str = Header(alias="X-Webhook-Secret"),
) -> NewsAssetUploadResponse:
    """Upload da imagem da noticia (ex.: zapi-mcp-intro.png). Requer header X-Webhook-Secret."""
    if x_webhook_secret != WEBHOOK_SHARED_SECRET:
        raise HTTPException(status_code=403, detail="Nao autorizado")

    safe_id = _validate_news_id(news_id)
    content_type = (file.content_type or "").lower()
    if content_type and content_type not in ("image/png", "image/jpeg", "image/webp"):
        raise HTTPException(status_code=400, detail="Envie PNG, JPEG ou WebP")

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Arquivo vazio")

    try:
        path = await save_news_image_bytes(safe_id, raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    url = news_image_public_url(safe_id)
    logger.info("Upload news asset %s -> %s", safe_id, path)
    return NewsAssetUploadResponse(
        ok=True, news_id=safe_id, url=url, bytes=path.stat().st_size
    )


@router.get("/news-assets/{news_id}/info")
async def news_asset_info(news_id: str) -> dict[str, str | bool]:
    safe_id = _validate_news_id(news_id)
    path = _find_news_image_path(safe_id)
    return {
        "news_id": safe_id,
        "exists": path is not None,
        "url": news_image_public_url(safe_id),
        "bytes": path.stat().st_size if path else 0,
        "default_id": DEFAULT_GROUP_NEWS.id,
    }
