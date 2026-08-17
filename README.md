# Tech News IA & MCP — Desafio MCP Z-API 2026

FastAPI + SQLite + OpenAI (function-calling) + **Server MCP oficial da Z-API** (`https://mcp.z-api.io/mcp`). A cada turno do chat, a IA descobre as tools ao vivo via `tools/list` (não é um schema hardcoded) e decide quais chamar.

## Páginas (browser)

| Rota | Descrição |
|------|-----------|
| `/promocoes` | Chat público **Tech News** — fluxo principal da demo (IA + MCP) |
| `/confirmar/{token}` | Confirmação de entrada no grupo (link enviado via `send-text`) |
| `/sair/{token}` | Confirmação de saída do grupo (link enviado via `send-text`) |
| `/` | Redireciona para `/promocoes` |
| `/participar` | Landing legada — fluxo por palavra-chave `#desafiozapi` no WhatsApp |

## API

| Rota | Descrição |
|------|-----------|
| `GET /health` | Health check |
| `GET /tools-usage` | Checklist das 9 tools MCP já usadas nesta execução |
| `GET\|HEAD /assets/news/{id}.jpg` | Imagem pública da notícia (URL usada pelo `send-image`) |
| `GET /api/chat/config` | Config pública do chat (Turnstile habilitado/site key) |
| `POST /api/chat` | Turno do chat (`message`, `history[]` → `reply`, `tools_used[]`) |
| `GET /api/chat/human/{session_id}` | Status da verificação anti-bot (Turnstile) |
| `POST /api/chat/verify-human` | Confirma token do Cloudflare Turnstile |
| `GET /api/chat/consent/{session_id}` | Polling do link de entrada/saída (ver estados abaixo) |
| `POST /api/chat/consent/accept/{token}` | Aceite do link de entrada — chamado por `/confirmar/{token}` |
| `POST /api/chat/leave/accept/{token}` | Aceite do link de saída — chamado por `/sair/{token}` |
| `POST /api/news-assets/{id}` | Upload manual da imagem da notícia (header `X-Webhook-Secret`) |
| `GET /api/news-assets/{id}/info` | Verifica se a imagem existe e qual URL pública usar |
| `POST /webhooks/zapi/{secret}/on-message-received` | Webhook do fluxo legado (`/participar`) |

**Painel admin (`app/admin_api.py`, rotas `/campaigns/...`) está desligado** — sem autenticação, ficaria exposto durante os dias de avaliação pública do desafio. Código intacto, só não é registrado em `app/main.py` (`app.include_router(admin_router)` comentado/removido); religar é reverter esse ponto.

## Deploy (VM)

```bash
git pull
docker compose up -d --build
```

Variáveis no `.env`: `WEBHOOK_SHARED_SECRET`, `OPENAPI_KEY`, opcional `OPENAI_MODEL`, `PUBLIC_BASE_URL`, `ZAPI_INSTANCE_PHONE` (MSISDN do WhatsApp da instância — sem default no código; se não definido, a checagem "número já é o dono do grupo" fica desativada).

Anti-bot (somente chat `/promocoes`): `NEXT_PUBLIC_TURNSTILE_SITE_KEY`, `TURNSTILE_SECRET_KEY` (Cloudflare Turnstile). Páginas `/confirmar/{token}` e `/sair/{token}` não exigem Turnstile.
Rate limit in-memory por IP: `CHAT_RATE_LIMIT_PER_MINUTE` (default 8), `CHAT_POLL_RATE_LIMIT_PER_MINUTE` (90), `CHAT_ACCEPT_RATE_LIMIT_PER_MINUTE` (15).

Tokens MCP OAuth em `/mnt/api-zapi-desafio-hackathon/mcp_auth` (volume Docker).

## Demo chat (`/promocoes`)

1. Abrir `https://desafiozapi.py.tec.br/promocoes`
2. Ler aviso LGPD; informar **primeiro nome** e WhatsApp com DDI
3. Receber **link de confirmação** no WhatsApp (`send-text` via MCP)
4. Tocar no link → `/confirmar/{token}` → progresso no chat (criando grupo / adicionando / conteúdo)
5. Polling `GET /api/chat/consent/{session_id}` (2s, só enquanto aguarda link/grupo/news) — retoma ao reabrir o chat.
   Estados de entrada: `pending`, `creating_group`, `adding_participant`, `preparing_content`, `accepted`, `expired`.
   Estados de saída (`/sair/{token}`): `remove_pending`, `removing`, `removed`.
6. Ao concluir: **grupo pessoal** `Tech News IA & MCP #NNN` (admin da instância + 1 participante) via `group-create` + `group-add-participant`; `send-text` de boas-vindas no DM; primeira news no grupo via `send-image` (URL pública, sem base64 — evita 413 no MCP) + `send-text` (legenda).

`send-image` está implementado e é tentado a cada notícia, mas em testes recentes o MCP da Z-API retornou erro 400 de forma consistente para essa tool (payload confere com o schema oficial); `send-text` funciona normalmente na mesma sessão. Enquanto isso, a notícia é entregue em texto — o código já volta a enviar imagem sozinho assim que a Z-API corrigir, sem precisar de novo deploy.

### Imagem da notícia (upload manual)

O MCP aceita **link público** no `send-image` (sem base64). URL enviada: `.../assets/news/zapi-mcp-intro.jpg` (sem `?v=`). Uploads comprimidos (~100KB JPEG).

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
Quem **já tem grupo pessoal** (`#NNN`) reconhecido pelo telefone (com/sem 9º dígito) conclui direto no chat, sem novo link — e nunca revela status de membro/admin antes de confirmar posse do número pelo link.
Após criar ou reencontrar o grupo, o backend envia por DM o **link de convite** (`chat.whatsapp.com/...`) obtido via `group-metadata` — abre o grupo direto no celular, sem vasculhar contatos na demo. Só afirma envio se o MCP confirmar.
**Sair do grupo** no chat: *"quero sair do grupo"* → link de confirmação no WhatsApp (`/sair/{token}`) → polling → `group-remove-participant` (igual ao fluxo de entrada).
