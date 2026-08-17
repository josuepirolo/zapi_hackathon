"""App unico FastAPI: webhook de consentimento + admin API.

Substitui `webhook_receiver/` (experimento de Fase 0, sem logica de
negocio nem persistencia) - ver ADR-0002 e
`.sdds/specs/consentimento-grupo.spec.md`.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response

from app import mcp_client
from app.admin_api import router as admin_router
from app.chat_api import router as chat_router
from app.config import NEWS_ASSETS_DIR
from app.db import init_models
from app.news_assets_api import router as news_assets_router
from app.webhook import router as webhook_router

STATIC_DIR = Path(__file__).resolve().parent / "static"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    from app.config import TURNSTILE_ENABLED

    await init_models()
    NEWS_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    if not TURNSTILE_ENABLED:
        logging.getLogger("delega").warning(
            "Turnstile desativado (defina NEXT_PUBLIC_TURNSTILE_SITE_KEY + TURNSTILE_SECRET_KEY em producao)."
        )
    yield


app = FastAPI(title="DELEGA - Gestao de Grupo de WhatsApp com Consentimento", lifespan=lifespan)
app.include_router(webhook_router)
app.include_router(admin_router)
app.include_router(chat_router)
app.include_router(news_assets_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


def _news_asset_path(filename: str) -> tuple[Path, str]:
    """Valida nome e retorna (path, media_type) ou levanta 404."""
    allowed = (".png", ".jpg", ".jpeg")
    if not any(filename.endswith(ext) for ext in allowed) or filename.count(".") != 1:
        raise HTTPException(status_code=404, detail="Nao encontrado")
    stem, ext = filename.rsplit(".", 1)
    if not stem or not all(ch.isalnum() or ch in "-_" for ch in stem):
        raise HTTPException(status_code=404, detail="Nao encontrado")
    path = NEWS_ASSETS_DIR / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Nao encontrado")
    media_type = "image/jpeg" if ext in ("jpg", "jpeg") else "image/png"
    return path, media_type


@app.api_route("/assets/news/{filename}", methods=["GET", "HEAD"])
async def serve_news_asset(filename: str, request: Request) -> FileResponse | Response:
    """Imagem publica para Z-API `send-image` via URL. HEAD evita 400 no fetch do Z-API."""
    path, media_type = _news_asset_path(filename)
    cache_headers = {"Cache-Control": "no-store, no-cache, must-revalidate"}
    if request.method == "HEAD":
        return Response(
            status_code=200,
            headers={
                **cache_headers,
                "Content-Type": media_type,
                "Content-Length": str(path.stat().st_size),
            },
        )
    return FileResponse(path, media_type=media_type, headers=cache_headers)


@app.get("/tools-usage")
async def tools_usage() -> dict[str, bool]:
    """Checklist de quais das 9 tools do MCP ja foram chamadas com sucesso
    nesta execucao do processo - alimenta o painel (demonstra uso real do
    MCP). Em memoria, reinicia com o container."""
    return mcp_client.get_tool_usage()


@app.get("/")
async def panel() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/participar")
async def landing() -> FileResponse:
    return FileResponse(STATIC_DIR / "landing.html")


@app.get("/promocoes")
async def promocoes() -> FileResponse:
    return FileResponse(STATIC_DIR / "promocoes.html")


@app.get("/confirmar/{token}")
async def confirmar_link(token: str) -> FileResponse:
    return FileResponse(STATIC_DIR / "confirmar.html")


@app.get("/sair/{token}")
async def confirmar_saida_link(token: str) -> FileResponse:
    return FileResponse(STATIC_DIR / "confirmar_saida.html")
