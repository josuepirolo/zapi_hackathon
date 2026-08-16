"""Verificacao Cloudflare Turnstile (anti-bot no chat publico)."""

from __future__ import annotations

import logging

import httpx

from app.config import TURNSTILE_ENABLED, TURNSTILE_SECRET_KEY

logger = logging.getLogger("delega.turnstile")

_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


async def verify_turnstile(token: str | None, remote_ip: str | None) -> bool:
    if not TURNSTILE_ENABLED:
        return True
    if not token or not token.strip():
        return False
    payload: dict[str, str] = {
        "secret": TURNSTILE_SECRET_KEY,
        "response": token.strip(),
    }
    if remote_ip:
        payload["remoteip"] = remote_ip
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(_VERIFY_URL, data=payload)
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        logger.exception("Falha ao verificar Turnstile")
        return False
    if not data.get("success"):
        logger.warning("Turnstile rejeitou token: %s", data.get("error-codes"))
        return False
    return True
