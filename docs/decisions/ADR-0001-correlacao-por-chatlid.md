# ADR-0001 — Correlação de conversa usa `chatLid`, não `phone`

- Status: Aceita
- Data: 2026-08-11
- Contexto do projeto: DELEGA (Desafio MCP Z-API 2026), Fase 0 (validação técnica)

## Contexto

A seção 14 do `PROJECT_CONTEXT.md` exige que o DELEGA correlacione respostas
externas (ex.: a oficina respondendo no WhatsApp) com a Task correta,
persistindo o estado explicitamente em vez de depender do histórico do LLM.
Isso pressupõe uma chave estável para identificar "quem está respondendo".

A hipótese inicial (implícita na proposta do produto) era usar `phone`
(número de telefone) como essa chave — é o identificador natural e é o
parâmetro exigido pelo `send-text` do MCP para iniciar uma conversa.

Durante a validação real do webhook `on-message-received`
(`docs/zapi-webhook-events.md`), dois eventos reais foram capturados:

1. Mensagem própria sincronizada entre dispositivos (`fromMe: true`):
   `phone` veio como `"<id>@lid"` — não um número de telefone.
2. Mensagem de um terceiro real (`fromMe: false`): `phone` veio como MSISDN
   normal (`"554499670415"`).

Isso levantou a dúvida se `phone` é uma chave confiável. A documentação
oficial da Z-API (`developer.z-api.io/tips/lid.md`) confirma que **não é**:

> LID é um identificador de privacidade que o WhatsApp usa para representar
> contatos sem expor o número de telefone. `phone` pode conter o número real
> ou o LID, dependendo da configuração de privacidade de quem enviou —
> imprevisível e fora do controle do DELEGA. `chatLid` é o identificador mais
> estável. LID não pode ser convertido de volta para número de telefone.

Ou seja: **qualquer** participante externo (oficina, prestador, etc.) pode
aparecer com `phone` mascarado como LID, não só em cenários excepcionais —
depende só da configuração de privacidade dele no WhatsApp, algo que o
DELEGA não controla nem pode prever antecipadamente.

## Decisão

A correlação de conversa (Task ↔ participante externo) usa **`chatLid`**
como chave primária, não `phone`.

- `chatLid` é gravado na Task no momento em que a conversa com o participante
  externo é iniciada ou quando a primeira resposta chega via webhook.
- `phone`, quando disponível como número real, é armazenado como dado
  auxiliar (ex.: exibição para o usuário, log), nunca como chave de busca.
- Para responder um participante cujo `phone` está mascarado como LID, o
  MCP `send-text` aceita o LID diretamente no parâmetro `phone`
  (`"phone": "<id>@lid"`, confirmado na doc oficial) — não é necessário
  resolver o LID para um número real antes de agir.

## Consequências

**Positivas**
- Correlação funciona mesmo quando o participante externo tem privacidade
  ativada no WhatsApp — não há dependência de um formato que o DELEGA não
  controla.
- Segue a recomendação oficial da própria Z-API.

**Negativas / trade-offs**
- `chatLid` não é legível/reconhecível para humanos (diferente de um número
  de telefone) — se o produto precisar exibir "quem é esse contato" para o
  usuário, precisa usar `senderName`/`chatName` do payload do webhook para
  isso, não `chatLid`.
- LID não é conversível de volta para número de telefone (limitação da
  própria Z-API) — se o produto algum dia precisar do número real de um
  contato só conhecido por LID, essa informação simplesmente não está
  disponível via Z-API.

## Referências

- `docs/zapi-webhook-events.md` — achado crítico #2, payloads reais observados
- https://developer.z-api.io/tips/lid.md (documentação oficial)
- `PROJECT_CONTEXT.md`, seção 14 (Correlação de Conversas)
