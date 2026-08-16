"""Configuracao via variaveis de ambiente.

Sem carregamento de .env em runtime (mesmo padrao do webhook_receiver
original): as variaveis sao injetadas pelo ambiente (docker-compose
`environment:` em producao, shell local em dev).
"""

from __future__ import annotations

import os


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} nao configurado. Defina como variavel de ambiente antes de subir o app.")
    return value


WEBHOOK_SHARED_SECRET = _required("WEBHOOK_SHARED_SECRET")
# Nome da env var confirmado contra o .env real do projeto (OPENAPI_KEY,
# nao o OPENAI_API_KEY "padrao") - ver .env do projeto.
OPENAI_API_KEY = _required("OPENAPI_KEY")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:////app/data/app.db")
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "https://desafiozapi.py.tec.br").rstrip("/")
CONSENT_LINK_TTL_MINUTES = int(os.environ.get("CONSENT_LINK_TTL_MINUTES", "30"))

# Cloudflare Turnstile — aceita nome NEXT_PUBLIC_* (convencao front) ou TURNSTILE_SITE_KEY.
TURNSTILE_SECRET_KEY = os.environ.get("TURNSTILE_SECRET_KEY", "").strip()
TURNSTILE_SITE_KEY = (
    os.environ.get("NEXT_PUBLIC_TURNSTILE_SITE_KEY") or os.environ.get("TURNSTILE_SITE_KEY") or ""
).strip()
TURNSTILE_ENABLED = bool(TURNSTILE_SECRET_KEY and TURNSTILE_SITE_KEY)

# Rate limit chat publico (in-memory por IP; suficiente pro hackathon).
CHAT_RATE_LIMIT_PER_MINUTE = int(os.environ.get("CHAT_RATE_LIMIT_PER_MINUTE", "8"))
CHAT_POLL_RATE_LIMIT_PER_MINUTE = int(os.environ.get("CHAT_POLL_RATE_LIMIT_PER_MINUTE", "90"))
CHAT_ACCEPT_RATE_LIMIT_PER_MINUTE = int(os.environ.get("CHAT_ACCEPT_RATE_LIMIT_PER_MINUTE", "15"))
CHAT_HUMAN_VERIFY_TTL_HOURS = int(os.environ.get("CHAT_HUMAN_VERIFY_TTL_HOURS", "12"))
