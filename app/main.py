"""App unico FastAPI: webhook de consentimento + admin API.

Substitui `webhook_receiver/` (experimento de Fase 0, sem logica de
negocio nem persistencia) - ver ADR-0002 e
`.sdds/specs/consentimento-grupo.spec.md`.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from app.admin_api import router as admin_router
from app.db import init_models
from app.webhook import router as webhook_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await init_models()
    yield


app = FastAPI(title="DELEGA - Gestao de Grupo de WhatsApp com Consentimento", lifespan=lifespan)
app.include_router(webhook_router)
app.include_router(admin_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
