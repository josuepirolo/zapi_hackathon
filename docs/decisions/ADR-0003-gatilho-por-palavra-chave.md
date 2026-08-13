# ADR-0003 — Consentimento só inicia com palavra-chave, nunca em qualquer mensagem

- Status: Aceita
- Data: 2026-08-13
- Contexto do projeto: DELEGA (Desafio MCP Z-API 2026)

## Contexto

Na primeira execução real do vertical slice (ver ADR-0002), o webhook
tratava **qualquer mensagem de qualquer número desconhecido** como "quer
participar da campanha" e disparava o convite automaticamente
(`app/webhook.py`, `_handle_new_contact`). No teste end-to-end real contra
o WhatsApp da instância, isso resultou em **mensagens não solicitadas
enviadas para contatos sem relação com o hackathon** assim que uma
mensagem real chegou por qualquer motivo — a instância roda no WhatsApp
pessoal do usuário (não um número dedicado ao hackathon), que já tem
conversas/contatos anteriores sem relação com o projeto. O usuário
precisou derrubar os containers para conter o envio em massa.

Isso viola diretamente a regra 14 do `CONTEXT_UPDATED.md` ("Não enviar
mensagens não solicitadas... O ambiente deve ser reproduzível e seguro
para demonstração").

## Decisão

Uma mensagem de um contato **novo** (sem `Contact` existente) só inicia o
fluxo de consentimento se contiver a `trigger_keyword` de alguma campanha
(comparação case-insensitive, substring). Sem esse match, a mensagem é
**completamente ignorada**: nenhum `Contact` é criado, nenhuma resposta é
enviada.

`Campaign.trigger_keyword` passa a ser obrigatório em `POST /campaigns`.

Se a mensagem bater com a palavra-chave de mais de uma campanha, usa a
mais recente (log de aviso) — cenário raro, aceitável para o hackathon.

## Consequências

- Contatos que já viraram `Contact` (inclusive os criados durante o
  incidente, antes deste fix) continuam no fluxo normalmente — o gate por
  palavra-chave só se aplica à entrada de contatos **novos**.
- Reduz drasticamente o raio de alcance de qualquer mensagem inbound não
  relacionada à campanha, mesmo que o número da instância receba tráfego
  de outros contextos.
- Não elimina 100% o risco (uma mensagem legítima de terceiro não
  relacionado que por acaso contenha a palavra-chave ainda dispararia o
  fluxo) — aceitável para o escopo do hackathon; produção real precisaria
  de confirmação adicional antes de qualquer envio em massa/campanha.

## Referências

- `app/webhook.py` (`_match_campaign_by_keyword`, `_handle_new_contact`)
- `docs/decisions/ADR-0002-pivot-grupo-whatsapp-consentimento.md`
- `CONTEXT_UPDATED.md`, seção 14 (regra de segurança/demo controlada)
