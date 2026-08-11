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
- Primeiro evento real capturado: 2026-08-11T04:33:20Z.

## Como isso foi obtido

`webhook_receiver/app.py` grava cada evento cru em `data/events.jsonl` e loga
via `logging`. Inspecionado via `docker logs delega-webhook-receiver` e
`GET /webhooks/zapi/events` na VM.

## Achado crítico #1: primeiro evento não foi de um terceiro externo

O teste manual (usuário mandando mensagem "de fora") na prática capturou uma
mensagem que o **próprio usuário enviou pelo seu WhatsApp** (`fromMe: true`)
para um contato/grupo chamado "Lekazis Marketing" — não uma resposta de um
terceiro para o número da instância. O evento chegou porque o WhatsApp
multi-device sincroniza as próprias mensagens enviadas para todos os
dispositivos vinculados, incluindo a sessão da API.

**Consequência:** ainda não validamos o caso real do DELEGA (participante
externo, ex. oficina, respondendo à instância). Precisa de um teste
adicional: um número que **não seja** o dono da instância mandando mensagem
diretamente para o número conectado à instância, com `fromMe: false`.

## Achado crítico #2: `phone` nem sempre é um MSISDN simples

Diferente de todos os exemplos da doc pública (`phone: "5544999999999"`), o
evento observado trouxe:

```json
"phone": "51875353223224@lid",
"chatLid": "51875353223224@lid"
```

Formato `@lid` (Linked ID interno do WhatsApp), não um telefone. Isso é
relevante para a correlação de conversa (seção 14 do PROJECT_CONTEXT.md): a
lógica de correlação **não pode assumir que `phone` é sempre um número
discável** — precisa tratar `@lid` como identificador válido também, ou
normalizar antes de comparar com o que foi usado no `send-text` do MCP (que
exige DDI+DDD+número). Ainda não confirmado se `@lid` aparece em mensagens de
terceiros ou é específico desse cenário (self-sync).

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

Headers HTTP relevantes recebidos junto (redigido: token trocado por
placeholder no log real, mas visível cru no log do container — ver risco
abaixo):

```
z-api-token: <instance-token>
server: Z-API
origin: https://api.z-api.io
user-agent: Mozilla/5.0 (iPad; ...) — UA fixo do client HTTP da Z-API, não é o
  dispositivo do usuário
```

## Campos — classificação

| Campo | Status | Observação |
|---|---|---|
| `messageId` | OBSERVADO | Presente, string única. Candidato natural a chave de idempotência. |
| `instanceId` | OBSERVADO | Bate com o `INSTANCE_ID` real da instância. |
| `phone` | OBSERVADO (formato inesperado) | Veio como `@lid`, não MSISDN — ver achado #2. Formato MSISDN puro ainda **NÃO VALIDADO** (só documentado nos exemplos públicos). |
| `fromMe` | OBSERVADO | `true` neste evento — o caso `false` (mensagem de terceiro) ainda **NÃO VALIDADO**. |
| `isGroup` | OBSERVADO | `false`, consistente com o teste (chat 1:1). |
| `momment` | OBSERVADO | Epoch ms. |
| `text.message` | OBSERVADO | Conteúdo textual simples confere com a doc pública. |
| `type` | OBSERVADO | Sempre `"ReceivedCallback"`, como documentado. |
| Campos de reply/mensagem citada (`referencedMessage` etc.) | NÃO VALIDADO | Não presentes neste evento (mensagem não era resposta a nada). Documentado publicamente para reactions/polls/status-reply, não testado ao vivo ainda. |
| Header `z-api-token` | OBSERVADO, NÃO DOCUMENTADO | Ver achado #3. |

## Riscos / pendências abertas

- **Falta o teste com terceiro real** (`fromMe: false`) — é o cenário que
  efetivamente importa para o DELEGA. Próxima ação recomendada.
- Log da aplicação (`webhook_receiver/app.py`) grava o header `z-api-token`
  em texto puro no log do container (`docker logs`) — a lista
  `SENSITIVE_HEADERS` só redige `authorization`/`client-token`/`cookie`,
  não esse header específico. Ajustar antes de considerar o receiver
  hardened (não é urgente para o experimento, mas não deve ir pra produto
  sem correção).
- Formato `@lid` em `phone` precisa ser investigado mais: acontece só em
  contextos de self-sync, ou também em mensagens de terceiros? Isso muda a
  estratégia de correlação de conversa.
