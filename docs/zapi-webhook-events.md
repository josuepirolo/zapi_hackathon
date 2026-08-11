# Eventos do Webhook Z-API (`on-message-received`)

> Documento vivo. Só descreve o que foi **realmente observado** chegando no
> receiver (`webhook_receiver/`), nunca o que a documentação pública apenas
> sugere. Ver seção "Como isso foi obtido" para reprodução.

- Endpoint configurado na instância: `update-webhook-received` (via API REST
  `PUT /instances/{id}/token/{token}/update-webhook-received`, header
  `Client-Token`) → aponta para
  `https://desafiozapi.py.tec.br/webhooks/zapi/on-message-received`.
- Infra: VM do usuário, Docker (`docker-compose.yml` na raiz), nginx
  (`nginx-prod.conf`) fazendo proxy de `desafiozapi.py.tec.br` (porta 80) pro
  container na porta 8010. TLS terminado no Cloudflare (proxied), origin em
  HTTP puro — **confirma que HTTPS na origin não é exigido**, só o endpoint
  público (via Cloudflare) precisa ser HTTPS.
- Primeiro evento real capturado: 2026-08-11T04:33:20Z (self-sync, `fromMe: true`).
- Segundo evento real capturado: 2026-08-11T04:35:10Z (**terceiro externo real**,
  `fromMe: false`) — fecha a validação do cenário que o DELEGA precisa.

## Como isso foi obtido

`webhook_receiver/app.py` grava cada evento cru em `data/events.jsonl` e loga
via `logging`. Inspecionado via `docker logs delega-webhook-receiver` e
`GET /webhooks/zapi/events` na VM.

## Achado crítico #1: primeiro evento foi self-sync, não terceiro — segundo evento fechou a validação

O primeiro teste (usuário mandando mensagem "de fora") na prática capturou uma
mensagem que o **próprio usuário enviou pelo seu WhatsApp** (`fromMe: true`)
para um contato chamado "Lekazis Marketing" — não uma resposta de terceiro. O
evento chegou porque o WhatsApp multi-device sincroniza as próprias mensagens
enviadas para todos os dispositivos vinculados, incluindo a sessão da API.

Um segundo teste, com uma pessoa genuinamente externa (não o dono da conta)
mandando mensagem direto pro número da instância, confirmou o cenário real:
`fromMe: false`, remetente e conteúdo corretos. **RESOLVIDO** — o loop
completo (terceiro → WhatsApp → Z-API → webhook → DELEGA) está validado.

## Achado crítico #2: `phone` só vem como `@lid` no cenário self-sync

No primeiro evento (self-sync, `fromMe: true`):

```json
"phone": "51875353223224@lid",
"chatLid": "51875353223224@lid"
```

No segundo evento (terceiro real, `fromMe: false`):

```json
"phone": "554499670415",
"chatLid": "115440265252930@lid"
```

**Confirmado:** para mensagem real de terceiro — o caso que importa pro
DELEGA — `phone` vem como MSISDN normal (DDI+DDD+número), igual ao formato
exigido pelo `send-text` do MCP. O formato `@lid` em `phone` parece
específico do cenário de auto-sincronização (`fromMe: true`), onde `phone` e
`chatLid` coincidem. `chatLid` como campo separado (`@lid`) aparece em ambos
os casos e não deve ser usado para correlação — `phone` é o campo certo.

## Achado crítico #3: header `z-api-token` na requisição do webhook

A própria Z-API envia, na chamada POST ao nosso endpoint, um header:

```
z-api-token: <token da instância>
```

Não documentado nas páginas oficiais consultadas até agora. Potencialmente
útil como mecanismo simples de verificação de que o evento veio da Z-API e é
da instância certa (comparar contra o `TOKEN_INSTANCE` esperado) — a
confirmar se é estável/documentado antes de depender disso para segurança.

## Payload real observado (sanitizado)

Nomes, foto e IDs de contato substituídos por placeholders. Estrutura e tipos
de campo preservados exatamente como recebidos.

```json
{
  "isStatusReply": false,
  "chatLid": "<lid>@lid",
  "connectedPhone": "<numero-da-instancia>",
  "waitingMessage": false,
  "isEdit": false,
  "isGroup": false,
  "isNewsletter": false,
  "instanceId": "<instance-id>",
  "messageId": "AC15186B9CE0DC6F8A73C4217D7EDBC9",
  "phone": "<lid>@lid",
  "fromMe": true,
  "momment": 1786422848000,
  "status": "RECEIVED",
  "chatName": "<nome-do-chat>",
  "senderPhoto": "<url>",
  "senderName": "<nome-do-remetente>",
  "photo": "<url>",
  "broadcast": false,
  "participantPhone": null,
  "participantLid": null,
  "forwarded": false,
  "type": "ReceivedCallback",
  "fromApi": false,
  "text": {
    "message": "Tetse"
  }
}
```

### Segundo payload real observado (sanitizado) — terceiro externo, `fromMe: false`

```json
{
  "isStatusReply": false,
  "chatLid": "<lid>@lid",
  "connectedPhone": "<numero-da-instancia>",
  "waitingMessage": false,
  "isEdit": false,
  "isGroup": false,
  "isNewsletter": false,
  "instanceId": "<instance-id>",
  "messageId": "ACD4DFDFDCD8C4964CA48A71429F2914",
  "phone": "<msisdn-do-terceiro>",
  "fromMe": false,
  "momment": 1786422957000,
  "status": "RECEIVED",
  "chatName": "<nome-do-contato>",
  "senderPhoto": "<url>",
  "senderName": "<nome-do-remetente>",
  "photo": "<url>",
  "broadcast": false,
  "participantPhone": null,
  "participantLid": null,
  "forwarded": false,
  "type": "ReceivedCallback",
  "fromApi": false,
  "text": {
    "message": "Tetse"
  }
}
```

Headers HTTP relevantes recebidos junto (redigido: token trocado por
placeholder no log real, mas visível cru no log do container — ver risco
abaixo):

```
z-api-token: <instance-token>
server: Z-API
origin: https://api.z-api.io
user-agent: Mozilla/5.0 (...) — UA varia por evento (visto iPad Safari e
  Android Chrome), parece ser um valor arbitrário do client HTTP da Z-API,
  não o dispositivo real do remetente — não usar para nada funcional.
```

## Campos — classificação

| Campo | Status | Observação |
|---|---|---|
| `messageId` | OBSERVADO | Presente, string única, em ambos os eventos. Candidato natural a chave de idempotência. |
| `instanceId` | OBSERVADO | Bate com o `INSTANCE_ID` real da instância. |
| `phone` | OBSERVADO | MSISDN normal (DDI+DDD+número) em mensagem de terceiro real (`fromMe: false`) — o caso que importa pro DELEGA. Vira `@lid` só no cenário self-sync (`fromMe: true`). Ver achado #2. |
| `fromMe` | OBSERVADO | Ambos os valores confirmados ao vivo: `true` (self-sync) e `false` (terceiro real). |
| `isGroup` | OBSERVADO | `false` nos dois eventos (testes 1:1). Grupo ainda não testado. |
| `momment` | OBSERVADO | Epoch ms, nos dois eventos. |
| `text.message` | OBSERVADO | Conteúdo textual simples confere com a doc pública. |
| `type` | OBSERVADO | Sempre `"ReceivedCallback"`, como documentado. |
| Campos de reply/mensagem citada (`referencedMessage` etc.) | NÃO VALIDADO | Não presentes em nenhum dos dois eventos (nenhuma mensagem era resposta a algo). Documentado publicamente para reactions/polls/status-reply, não testado ao vivo ainda. |
| Header `z-api-token` | OBSERVADO, NÃO DOCUMENTADO | Ver achado #3. Presente e consistente nos dois eventos. |

## Riscos / pendências abertas

- Log da aplicação (`webhook_receiver/app.py`) grava o header `z-api-token`
  em texto puro no log do container (`docker logs`) — **corrigido**:
  `SENSITIVE_HEADERS` agora inclui `z-api-token` (commit `47cdeaa`). Falta
  redeploy na VM (`docker compose up -d --build`) pra valer no ambiente real.
- `isGroup: true` e campos de reply/citação ainda não testados ao vivo —
  fora do caminho crítico do cenário de demo (troca de óleo é 1:1, sem reply).
