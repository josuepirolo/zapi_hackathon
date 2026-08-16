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

Variáveis no `.env`: `WEBHOOK_SHARED_SECRET`, `OPENAPI_KEY`, opcional `OPENAI_MODEL`, `PUBLIC_BASE_URL`.

Anti-bot (chat `/promocoes`): `NEXT_PUBLIC_TURNSTILE_SITE_KEY`, `TURNSTILE_SECRET_KEY` (Cloudflare Turnstile).
Rate limit in-memory por IP: `CHAT_RATE_LIMIT_PER_MINUTE` (default 8), `CHAT_POLL_RATE_LIMIT_PER_MINUTE` (90), `CHAT_ACCEPT_RATE_LIMIT_PER_MINUTE` (15).

Tokens MCP OAuth em `/mnt/api-zapi-desafio-hackathon/mcp_auth` (volume Docker).

## Demo chat (`/promocoes`)

1. Abrir `https://desafiozapi.py.tec.br/promocoes`
2. Informar WhatsApp com DDI e confirmar o número
3. Receber **link de confirmação** no WhatsApp (`send-text` via MCP)
4. Tocar no link → `/confirmar/{token}` → entra no grupo
5. O chat faz **polling** (`GET /api/chat/consent/{session_id}`) até detectar aceite

Sessão do browser: UUID em `localStorage` (`delega_chat_session`) — cookie não é obrigatório.
Estado do link: SQLite (`chat_consent_sessions`), sem Redis.
Telefones exibidos no chat são mascarados (`5544***9999`); o backend usa o número real só para MCP.
