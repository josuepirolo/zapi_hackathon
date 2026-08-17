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
| `GET /assets/news/{id}.jpg` | Imagem pública da notícia (URL para `send-image` no MCP) |
| `POST /api/news-assets/{id}` | Upload manual da PNG (header `X-Webhook-Secret`) |
| `GET /api/news-assets/{id}/info` | Verifica se a imagem existe e qual URL pública usar |

## Deploy (VM)

```bash
git pull
docker compose up -d --build
```

Variáveis no `.env`: `WEBHOOK_SHARED_SECRET`, `OPENAPI_KEY`, opcional `OPENAI_MODEL`, `PUBLIC_BASE_URL`, `ZAPI_INSTANCE_PHONE` (MSISDN do WhatsApp da instância — bloqueado no chat `/promocoes` porque `group-create` não aceita o próprio número).

Anti-bot (somente chat `/promocoes`): `NEXT_PUBLIC_TURNSTILE_SITE_KEY`, `TURNSTILE_SECRET_KEY` (Cloudflare Turnstile). Paginas `/confirmar/{token}` e `/sair/{token}` nao exigem Turnstile.
Rate limit in-memory por IP: `CHAT_RATE_LIMIT_PER_MINUTE` (default 8), `CHAT_POLL_RATE_LIMIT_PER_MINUTE` (90), `CHAT_ACCEPT_RATE_LIMIT_PER_MINUTE` (15).

Tokens MCP OAuth em `/mnt/api-zapi-desafio-hackathon/mcp_auth` (volume Docker).

## Demo chat (`/promocoes`)

1. Abrir `https://desafiozapi.py.tec.br/promocoes`
2. Ler aviso LGPD; informar **primeiro nome** e WhatsApp com DDI
3. Receber **link de confirmação** no WhatsApp (`send-text` via MCP)
4. Tocar no link → `/confirmar/{token}` → progresso no chat (criando grupo / adicionando / conteúdo)
5. Polling `GET /api/chat/consent/{session_id}` (2s, só enquanto aguarda link/grupo/news) — retoma ao reabrir o chat; estados: `pending`, `creating_group`, `adding_participant`, `preparing_content`, `accepted`
6. Ao concluir: **grupo pessoal** `Tech News IA & MCP #NNN` (admin da instancia + 1 participante) via `group-create` + `group-add-participant`; `send-text` de boas-vindas no DM; primeira news no grupo via `send-image` (URL pública, sem base64 — evita 413 no MCP) + `send-text` (legenda); imagem em `data/news_assets/{id}.png` (geração OpenAI ou upload manual).

### Imagem da notícia (upload manual)

O MCP rejeita `send-image` com base64 grande (`413 Request Entity Too Large`). O app envia a **URL pública** (`.../assets/news/zapi-mcp-intro.jpg?v=...`). Uploads são **comprimidos** (max 1024px, JPEG ~100KB).

```bash
# Depois do deploy — substitua SECRET pelo WEBHOOK_SHARED_SECRET do .env
curl -X POST "https://desafiozapi.py.tec.br/api/news-assets/zapi-mcp-intro" \
  -H "X-Webhook-Secret: SECRET" \
  -F "file=@sua-imagem.png"

# Conferir
curl "https://desafiozapi.py.tec.br/api/news-assets/zapi-mcp-intro/info"
curl -I "https://desafiozapi.py.tec.br/assets/news/zapi-mcp-intro.jpg"
```

Legado PNG no volume é reconvertido para JPEG no próximo envio da news.

Sessão do browser: UUID em `localStorage` (`delega_chat_session`) — cookie não é obrigatório.
O chat `/promocoes` usa **OpenAI + tools MCP** no fluxo de entrada (nome → interesse → WhatsApp); perguntas fora desse roteiro recebem resposta fixa sem chamar a API (economia de tokens).
Estado do link: SQLite (`chat_consent_sessions`), sem Redis.
Telefones exibidos no chat são mascarados (`5544***9999`); o backend usa o número real só para MCP.
Quem **já tem grupo pessoal** (`#NNN`) reconhecido pelo telefone (com/sem 9º dígito) conclui direto no chat, sem novo link.
Após criar ou reencontrar o grupo, o backend envia por DM o **link de convite** (`chat.whatsapp.com/...`) obtido via `group-metadata` — abre o grupo direto no celular, sem vasculhar contatos na demo. Só afirma envio se o MCP confirmar.
**Sair do grupo** no chat: *"quero sair do grupo"* → link de confirmação no WhatsApp (`/sair/{token}`) → polling → `group-remove-participant` (igual ao fluxo de entrada).
