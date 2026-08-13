# CLAUDE.md — consentimento-grupo

Este diretório contém o módulo `consentimento-grupo`.

Antes de modificar qualquer arquivo aqui, leia:

- `.sdds/specs/consentimento-grupo.spec.md` — spec completa do módulo
- `.sdds/contracts/consentimento-grupo.contract.md` — contratos de entrada/saída

Regras:

- Não faça alterações arquiteturais sem registrar ADR em `.sdds/decisions/`
- Não crie arquivos fora da estrutura definida na spec
- Ao terminar, atualize `.sdds/CURRENT_STATE.md` se houve impacto operacional
- `mcp_client.py` é o único ponto de import do SDK MCP — não chame o MCP
  diretamente de outros módulos
- `ai.py` é o único ponto de import da API OpenAI — não chame a OpenAI
  diretamente de outros módulos
- Sem frontend neste módulo — regras de UI não se aplicam
