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
2. Clicar **Falar com a assistente**
3. Pedir para entrar no grupo → informar WhatsApp com DDI
4. Confirmar → a IA chama `group-add-participant` ou `group-create` + `send-text`
5. Chips **MCP · tool-name** aparecem abaixo da resposta
