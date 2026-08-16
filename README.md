# DELEGA — Hackathon MCP Z-API

FastAPI + SQLite + OpenAI + **Server MCP oficial** (`https://mcp.z-api.io/mcp`).

## Rotas públicas

| Rota | Descrição |
|------|-----------|
| `/` | Painel admin (campanhas, checklist MCP) |
| `/participar` | Landing WhatsApp (palavra-chave `#desafiozapi`) |
| `/promocoes` | Landing promo + **chat flutuante** (IA → 9 tools MCP) |
| `POST /api/chat` | Backend do chat (`message`, `history[]` → `reply`, `tools_used[]`) |
| `/health` | Health check |
| `/tools-usage` | Checklist das 9 tools já usadas nesta execução |

## Deploy (VM)

```bash
git pull
docker compose up -d --build
```

Variáveis no `.env`: `WEBHOOK_SHARED_SECRET`, `OPENAPI_KEY`, opcional `OPENAI_MODEL`.

Tokens MCP OAuth em `/mnt/api-zapi-desafio-hackathon/mcp_auth` (volume Docker).

## Demo chat (`/promocoes`)

1. Abrir `https://desafiozapi.py.tec.br/promocoes`
2. Informar WhatsApp com DDI e confirmar o número
3. Receber **link trackeado** no WhatsApp (`send-text` via MCP)
4. Tocar no link → `/confirmar/{token}` → entra no grupo
5. O chat faz **polling** (`GET /api/chat/consent/{session_id}`) até detectar aceite

Sessão do browser: UUID em `localStorage` (`delega_chat_session`) — cookie não é obrigatório.
Estado do link: SQLite (`chat_consent_sessions`), sem Redis.
