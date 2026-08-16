# DELEGA — Hackathon MCP Z-API

FastAPI + SQLite + OpenAI + **Server MCP oficial** (`https://mcp.z-api.io/mcp`).

## Rotas públicas

| Rota | Descrição |
|------|-----------|
| `/` | Painel admin (campanhas, checklist MCP) |
| `/participar` | Landing WhatsApp (palavra-chave `#desafiozapi`) |
| `/promocoes` | Landing **Tech News** + chat flutuante (IA → 9 tools MCP) |
| `POST /api/chat` | Backend do chat (`message`, `history[]` → `reply`, `tools_used[]`) |
| `/health` | Health check |
| `/tools-usage` | Checklist das 9 tools já usadas nesta execução |

## Deploy (VM)

```bash
git pull
docker compose up -d --build
```

Variáveis no `.env`: `WEBHOOK_SHARED_SECRET`, `OPENAPI_KEY`, opcional `OPENAI_MODEL`, `PUBLIC_BASE_URL`, `ZAPI_INSTANCE_PHONE` (MSISDN do WhatsApp da instância — bloqueado no chat `/promocoes` porque `group-create` não aceita o próprio número).

Anti-bot (chat `/promocoes`): `NEXT_PUBLIC_TURNSTILE_SITE_KEY`, `TURNSTILE_SECRET_KEY` (Cloudflare Turnstile).
Rate limit in-memory por IP: `CHAT_RATE_LIMIT_PER_MINUTE` (default 8), `CHAT_POLL_RATE_LIMIT_PER_MINUTE` (90), `CHAT_ACCEPT_RATE_LIMIT_PER_MINUTE` (15).

Tokens MCP OAuth em `/mnt/api-zapi-desafio-hackathon/mcp_auth` (volume Docker).

## Demo chat (`/promocoes`)

1. Abrir `https://desafiozapi.py.tec.br/promocoes`
2. Ler aviso LGPD; informar **primeiro nome** e WhatsApp com DDI
3. Receber **link de confirmação** no WhatsApp (`send-text` via MCP)
4. Tocar no link → `/confirmar/{token}` → progresso no chat (criando grupo / adicionando / conteúdo)
5. Polling `GET /api/chat/consent/{session_id}` (2s, só enquanto aguarda link/grupo/news) — retoma ao reabrir o chat; estados: `pending`, `creating_group`, `adding_participant`, `preparing_content`, `accepted`
6. Ao concluir: **grupo pessoal** `Tech News IA & MCP #NNN` (admin da instancia + 1 participante) via `group-create` + `group-add-participant`; `send-text` de boas-vindas no DM; primeira news no grupo via `send-image` (imagem cacheada em `data/news_assets/`).

Sessão do browser: UUID em `localStorage` (`delega_chat_session`) — cookie não é obrigatório.
Estado do link: SQLite (`chat_consent_sessions`), sem Redis.
Telefones exibidos no chat são mascarados (`5544***9999`); o backend usa o número real só para MCP.
Quem **já tem grupo pessoal** (`#NNN`) reconhecido pelo telefone (com/sem 9º dígito) conclui direto no chat, sem novo link.
