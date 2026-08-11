"""Receiver minimo para o experimento da metade EVENT do loop do DELEGA.

NAO e codigo de produto: nao ha Task Engine, Agent Orchestrator, banco de
dados, correlacao ou dashboard aqui. O unico objetivo e capturar o payload
REAL que a Z-API envia para on-message-received e deixa-lo disponivel para
inspecao, sem assumir o schema.

Endpoints:
    POST /webhooks/zapi/on-message-received  -> recebe o evento, grava em
        disco (JSONL, um evento por linha) e responde 200 imediatamente.
    GET  /webhooks/zapi/events                -> lista os ultimos eventos
        capturados, para inspecao sem precisar entrar na VM.
    GET  /health                               -> healthcheck simples.

Nunca loga ou persiste o header Authorization/Client-Token caso presente.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("delega.webhook_receiver")

DATA_DIR = Path(__file__).resolve().parent / "data"
EVENTS_FILE = DATA_DIR / "events.jsonl"

SENSITIVE_HEADERS = {"authorization", "client-token", "cookie"}

app = FastAPI(title="DELEGA - Webhook Receiver (experimento Fase 0)")


def _sanitize_headers(headers: dict[str, str]) -> dict[str, str]:
    return {k: ("<redacted>" if k.lower() in SENSITIVE_HEADERS else v) for k, v in headers.items()}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/webhooks/zapi/on-message-received")
async def on_message_received(request: Request) -> JSONResponse:
    raw_body = await request.body()
    try:
        payload: Any = json.loads(raw_body)
    except json.JSONDecodeError:
        payload = {"_raw_unparseable": raw_body.decode("utf-8", errors="replace")}

    event = {
        "received_at": datetime.now(timezone.utc).isoformat(),
        "headers": _sanitize_headers(dict(request.headers)),
        "payload": payload,
    }

    DATA_DIR.mkdir(exist_ok=True)
    with EVENTS_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")

    logger.info("Evento recebido: %s", json.dumps(event, ensure_ascii=False))

    # Responde rapido e com sucesso - a Z-API so precisa de um 200.
    return JSONResponse(content={"status": "received"}, status_code=200)


@app.get("/webhooks/zapi/events")
async def list_events(limit: int = 20) -> list[dict[str, Any]]:
    if not EVENTS_FILE.exists():
        return []
    lines = EVENTS_FILE.read_text(encoding="utf-8").strip().splitlines()
    last_lines = lines[-limit:]
    return [json.loads(line) for line in last_lines]
