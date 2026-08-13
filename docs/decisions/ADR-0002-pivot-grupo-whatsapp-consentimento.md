# ADR-0002 — Pivot de escopo: DELEGA genérico → gestão de grupo de WhatsApp com consentimento

- Status: Aceita
- Data: 2026-08-11
- Contexto do projeto: DELEGA (Desafio MCP Z-API 2026)

## Contexto

O escopo original (`PROJECT_CONTEXT.md`) definia o DELEGA como um agente de
delegação genérico: o usuário delega qualquer objetivo, um Task Engine
decide a próxima ação, e o agente executa via MCP até resolver. Cenário de
demo: agendar troca de óleo negociando horário com uma oficina.

Com a Fase 0 completa (MCP validado ao vivo, webhook validado ao vivo,
infraestrutura de produção no ar), o usuário decidiu — via
`CONTEXT_UPDATED.md` — estreitar o escopo para maximizar simplicidade,
demonstrabilidade e uso concentrado do MCP dentro do prazo do hackathon.

## Decisão

Escopo anterior (agente genérico, Task Engine amplo, state machine de 8
estados, cenário de oficina) é substituído por:

**Gestão inteligente de grupos de WhatsApp com consentimento.**

Fluxo: administrador cria uma campanha/grupo pelo painel → interessado inicia
conversa espontânea no WhatsApp da instância → aplicação pergunta se ele
quer participar → IA interpreta a resposta (SIM/NÃO, inclusive em linguagem
natural) → em caso positivo, `group-add-participant` via MCP adiciona ao
grupo e `send-text` via MCP confirma no privado.

## Por que isso explora melhor o Server MCP Z-API

- Usa 3 das 9 tools de forma essencial ao fluxo principal
  (`group-add-participant`, `send-text`) e mais 2 de forma auxiliar
  (`group-create`, `group-metadata`), versus o cenário anterior que usava
  essencialmente só `send-text`.
- Fluxo é determinístico e fácil de demonstrar em poucos minutos — menos
  superfície de falha ao vivo que negociar disponibilidade de horário com um
  terceiro real.
- Remove a necessidade de um Task Engine genérico (que nunca chegou a ser
  implementado) — o novo fluxo é fixo o bastante para não precisar de uma
  máquina de estados ampla nem de um orquestrador de agente livre.

## O que permanece válido da Fase 0 (não descartado)

- Client MCP com OAuth 2.1 (DCR + PKCE + refresh_token) — `scripts/mcp_oauth_experiment.py`
  vira a base do client MCP de produto.
- Webhook receiver com segredo no path — `webhook_receiver/app.py` vira a
  base do handler de webhook de produto (mesma proteção, lógica real
  adicionada).
- Infraestrutura: Docker, nginx (`nginx-prod.conf`), Cloudflare, domínio
  `desafiozapi.py.tec.br` — reaproveitados sem alteração.
- `docs/zapi-mcp-capabilities.md` e `docs/zapi-webhook-events.md` — continuam
  sendo a fonte de verdade sobre schemas e comportamento real observado.
- **ADR-0001 (correlação por `chatLid`, não `phone`)** — mais relevante
  ainda: o novo modelo de dados usa `chatLid` como chave de identificação do
  contato, não `phone` como o `CONTEXT_UPDATED.md` sugeria inicialmente
  ("identifica o interessado pelo telefone") — corrigido na modelagem
  seguindo a evidência real já validada.
- Regras de segurança, idempotência e princípios de engenharia (seções 15,
  16, 18 do `PROJECT_CONTEXT.md` original) continuam valendo.

## O que é descontinuado

- Task Engine genérico e state machine de 8 estados
  (`CREATED/PLANNING/EXECUTING/WAITING_EXTERNAL/NEEDS_APPROVAL/COMPLETED/FAILED/CANCELLED`)
  → substituído por 5 estados de contato
  (`PENDING/ACCEPTED/DECLINED/ADDED/REMOVED`).
- Conceito de `Task` genérica como entidade central de domínio → substituído
  por `Campaign` e `Contact`, específicos do novo fluxo.
- Cenário de demo "troca de óleo/oficina" → substituído por "grupo de
  promoções".
- Dashboard genérico (Atenção/Em andamento/Resolvidas) → substituído por
  painel campanha/participantes/conteúdo.

## Referências

- `CONTEXT_UPDATED.md` (raiz do projeto — instrução original do pivot)
- `PROJECT_CONTEXT.md` (documento anterior, seções de visão/demo superseded)
- `docs/decisions/ADR-0001-correlacao-por-chatlid.md`
