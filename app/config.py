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
