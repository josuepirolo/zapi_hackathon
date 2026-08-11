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

## Achado crítico #2: `phone` pode vir como LID — não é específico de self-sync

Hipótese inicial (revisada): achei que o `@lid` em `phone` fosse exclusivo do
cenário self-sync. **Estava incompleto.** A doc oficial
(`developer.z-api.io/tips/lid.md`, DOCUMENTADO) explica: LID (Linked ID) é o
identificador de privacidade que o próprio WhatsApp usa para representar
contatos **sem expor o número de telefone**, e pode aparecer no lugar do
número pra **qualquer contato** que tenha essa configuração de privacidade
ativa — não é algo que o DELEGA controla ou pode prever por tipo de evento.

Segundo a doc oficial:
- `phone` pode conter o número real OU o LID, dependendo da configuração de
  privacidade de quem enviou — não dá pra assumir um formato fixo.
- `chatLid` é o identificador **mais estável** recomendado pela própria
  Z-API para identificar o contato — ele existe mesmo quando `phone` também
  está disponível.
- LID **não pode ser convertido de volta pra número de telefone** — a Z-API
  não oferece esse mapeamento (é assim por design de privacidade).
- Pra responder um contato que só tem LID, o MCP `send-text` aceita o LID
  diretamente no parâmetro `phone` (ex.: `"phone": "999999999999999@lid"`).

Nos dois eventos que capturamos:

```json
// Evento 1 (self-sync, fromMe: true)
"phone": "51875353223224@lid", "chatLid": "51875353223224@lid"

// Evento 2 (terceiro real, fromMe: false)
"phone": "554499670415", "chatLid": "115440265252930@lid"
```

Os dois casos são consistentes com a doc: `chatLid` sempre presente e em
formato `@lid`; `phone` variando entre número real e LID.

**Decisão de arquitetura para o DELEGA:** a correlação de conversa (seção 14
do PROJECT_CONTEXT.md) deve usar **`chatLid` como chave primária**, não
`phone` — exatamente como a Z-API recomenda ("armazene o LID no seu banco
para manter consistência"). `phone`, quando vier como número real, pode ser
guardado como dado auxiliar (ex. exibição pro usuário), mas não como chave de
correlação, já que pode não estar disponível ou pode mudar de forma
imprevisível para o mesmo contato.

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
| `phone` | OBSERVADO + DOCUMENTADO | Pode conter MSISDN ou LID, dependendo da privacidade do remetente (confirmado em `tips/lid.md`) — **não usar como chave de correlação**. Ver achado #2. |
| `chatLid` | OBSERVADO + DOCUMENTADO | Sempre presente, formato `@lid` estável nos dois eventos. Recomendado pela própria Z-API como identificador de correlação. Ver achado #2. |
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
