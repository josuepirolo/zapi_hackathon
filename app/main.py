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

from fastapi import FastAPI
from fastapi.responses import FileResponse

from app import mcp_client
from app.admin_api import router as admin_router
from app.chat_api import router as chat_router
from app.db import init_models
from app.webhook import router as webhook_router

STATIC_DIR = Path(__file__).resolve().parent / "static"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await init_models()
    yield


app = FastAPI(title="DELEGA - Gestao de Grupo de WhatsApp com Consentimento", lifespan=lifespan)
app.include_router(webhook_router)
app.include_router(admin_router)
app.include_router(chat_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


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
