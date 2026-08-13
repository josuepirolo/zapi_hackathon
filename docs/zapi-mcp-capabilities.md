# Capabilities do Server MCP Z-API

> Documento vivo. Só descreve o que foi **realmente observado** conectando ao
> servidor (`tools/list` e `tools/call` reais), nunca o que a documentação
> pública apenas sugere. Ver seção "Como isso foi obtido" para reprodução.

- Endpoint: `https://mcp.z-api.io/mcp`
- Protocolo: MCP sobre Streamable HTTP, autenticação OAuth 2.1 (authorization_code
  + PKCE, Dynamic Client Registration, refresh_token) — descoberto via
  `https://mcp.z-api.io/.well-known/oauth-authorization-server`.
- `serverInfo` retornado no `initialize`: `name=irrah-mcp-server`, `version=1.0.0`.
- Última validação ao vivo: 2026-08-10.
- Total de tools expostas: **9**.

## Como isso foi obtido

Script: `scripts/mcp_oauth_experiment.py` (SDK oficial `mcp`, não é código de
produto do DELEGA — é o experimento de validação da Fase 0).

```
python scripts/mcp_oauth_experiment.py list-tools
python scripts/mcp_oauth_experiment.py call-tool send-text --arg phone=<numero> --arg message=<texto>
```

Na primeira execução abre o navegador para autorização OAuth manual (login
Z-API + escolha da instância). Tokens ficam em `.mcp_auth/` (fora do git) e
são reutilizados/renovados via `refresh_token` nas execuções seguintes — **não
é necessário repetir o passo manual a cada chamada**, o que resolve a maior
incerteza técnica identificada na Fase 0 (viabilidade de um client OAuth
customizado fora do padrão "connector" de apps de chat).

## Achado crítico: sem tools de recebimento/leitura

Nenhuma das 9 tools lê mensagens, lista chats ou consulta histórico. O MCP
cobre **só a metade "ACT"** do loop do DELEGA (agente → WhatsApp). A metade
"WAIT / EVENT" (WhatsApp → agente, ex.: resposta da oficina) depende do
mecanismo clássico de Webhook da Z-API (`on-message-received`), fora do MCP.
Isso confirma a arquitetura da seção 10 do PROJECT_CONTEXT.md e reforça a
regra da seção 14: correlação de conversa tem que ser feita inteiramente pela
persistência do DELEGA, nunca pelo MCP.

---

## Mensageria

### `send-text`
**Status:** ✅ testada ao vivo (mensagem real entregue).

- **Finalidade:** enviar mensagem de texto para um número ou grupo.
- **Parâmetros:**
  | Campo | Tipo | Obrigatório | Descrição |
  |---|---|---|---|
  | `phone` | string | sim | Número (ou ID de grupo) no formato `DDI DDD NUMERO`, ex. `5511999999999`, sem máscara/formatação. |
  | `message` | string | sim | Texto da mensagem. |
  | `delayMessage` | number | não | Delay antes de enviar, 1–15s (default 1–3s). |
  | `delayTyping` | number | não | Tempo em "digitando...", 1–15s (default 0). |
  | `editMessageId` | string | não | ID de uma mensagem já enviada, para editá-la. |
- **Retorno (observado):**
  ```json
  {"zaapId": "019FEEB9C8CF79EB87F3AE2EF8039C52", "messageId": "487D1E245D37E9A11B04", "id": "487D1E245D37E9A11B04"}
  ```
- **Limitações:** nenhuma observada ainda; mensagem sai do número WhatsApp
  vinculado à instância Z-API do usuário.
- **Uso no DELEGA:** ação primária do agente para contatar o participante
  externo (ex.: oficina) e para confirmar/atualizar o usuário. `messageId`
  retornado deve ser persistido na Task para permitir correlação futura
  (ex.: replies via `messageId` em `on-message-received`, ainda não validado).

### `send-image`
**Status:** 📄 documentada via `tools/list`, não testada com chamada real.

- **Finalidade:** enviar imagem (link ou Base64) com legenda opcional.
- **Parâmetros:**
  | Campo | Tipo | Obrigatório | Descrição |
  |---|---|---|---|
  | `phone` | string | sim | Igual a `send-text`. |
  | `image` | string | sim | Link da imagem ou Base64. |
  | `caption` | string | não | Legenda. |
  | `messageId` | string | não | Responde a uma mensagem específica do chat. |
  | `delayMessage` | number | não | Igual a `send-text`. |
  | `viewOnce` | boolean | não | Mensagem "ver uma vez" (default false). |
- **Retorno:** não validado ainda (esperado similar a `send-text`, a confirmar).
- **Uso no DELEGA:** fora do escopo do cenário de demo (troca de óleo); não
  prioritário para o MVP.

### `send-video`
**Status:** 📄 documentada via `tools/list`, não testada com chamada real.

- **Finalidade:** enviar vídeo (link ou Base64) com legenda opcional.
- **Parâmetros:** iguais a `send-image`, mais `async` (boolean — se true,
  responde imediatamente e processa o arquivo em background).
- **Retorno:** não validado ainda.
- **Uso no DELEGA:** fora do escopo do MVP.

---

## Gestão de grupo

Nenhuma destas foi chamada ao vivo — só capturadas via `tools/list`. Fora do
escopo funcional do cenário de demo (troca de óleo é 1:1), mas documentadas
porque fazem parte da superfície real do servidor.

### `group-create`
**Status:** ✅ testada ao vivo (2026-08-13, app de produto `app/admin_api.py`).

- **Finalidade:** criar grupo com participantes.
- **Parâmetros:** `groupName` (string, obrigatório), `phones` (array de
  string, obrigatório, mesmo formato de `send-text`), `autoInvite` (boolean,
  obrigatório — envia link de convite em privado).
- **Achado crítico: `phones: []` é rejeitado.** Chamada real com array vazio
  retornou `{"success":false,"message":"participants not found"}` — o MCP
  exige pelo menos um participante para criar o grupo, não é possível criar
  vazio e adicionar depois via `group-add-participant`.
- **Achado crítico: o próprio número da instância também é rejeitado.**
  Passar só o número conectado à instância como `phones` retornou o mesmo
  erro `"participants not found"` — não dá pra se adicionar como
  participante de si mesmo (você já é o dono/criador do grupo). Por isso
  `app/webhook.py` não chama `group-create` em `POST /campaigns`; o grupo
  só é criado no primeiro aceite real de um terceiro (RN-007), usando esse
  contato como participante inicial.
- **Achado crítico: formato real do retorno de `tools/call`.** O payload de
  negócio (`success`, mensagens de erro, IDs) não vem em chaves soltas do
  resultado — vem como uma **string JSON dentro de `content[0]['text']`**:
  ```json
  {"content": [{"type": "text", "text": "{\"success\": false, \"message\": \"participants not found\"}"}], "is_error": false}
  ```
  `is_error: false` no envelope só significa que a chamada MCP em si não
  quebrou — **não** que a operação teve sucesso; é preciso parsear
  `content[0]['text']` como JSON e checar `success` dentro dele. Provável
  que as demais tools (`send-text`, `group-add-participant` etc.) sigam o
  mesmo envelope — `app/mcp_client.py` (`parse_tool_payload`,
  `tool_call_succeeded`) trata isso de forma genérica.
- **Limitação documentada:** não é possível criar grupo já com imagem; precisa
  de chamada separada (tool de update de foto não está entre as 9 atuais).

### `group-metadata`
**Status:** ⚠️ testada ao vivo, mas com `groupId` no formato errado — retornou
erro, não sucesso. Ver nota abaixo.

- **Finalidade:** consultar metadados do grupo (nome, participantes, admins).
- **Parâmetros:** `groupId` (string, obrigatório).
- **Retorno observado (com ID inválido):**
  ```json
  {"is_error": true, "content": [{"type": "text", "text": "Request failed with status code 400"}]}
  ```
- **Achado real:** o código de convite do grupo (o token que aparece em
  `chat.whatsapp.com/<codigo>`, formato tipo `CN7JnIdwMmsGNeGGqs2XTG`) **não é
  aceito** como `groupId` — retorna 400. O MCP não tem nenhuma tool para
  listar grupos/chats ou resolver nome → ID, então o formato correto de
  `groupId` (provavelmente o JID interno do grupo, ex.
  `120363xxxxxxxxxx-xxxxxxxxxx`, sem o sufixo `@g.us`) ainda não foi
  confirmado ao vivo — precisa ser obtido fora do MCP (painel Z-API ou API
  REST clássica) para fechar essa validação.
- **Uso potencial no DELEGA:** poderia servir para verificar estado de um
  grupo de coordenação, se o produto evoluir para esse caso — não usado no MVP.

### `group-add-participant` / `group-remove-participant`
- **Finalidade:** adicionar/remover membros de um grupo.
- **Parâmetros:** `groupId` (string, obrigatório), `phones` (array, obrigatório);
  `group-add-participant` também aceita `autoInvite` (boolean, obrigatório).

### `group-add-admin` / `group-remove-admin`
- **Finalidade:** promover/rebaixar administradores do grupo.
- **Parâmetros:** `groupId` (string, obrigatório), `phones` (array, obrigatório).

---

## Limitações e riscos ainda abertos

- **Sem tool de listagem de grupos/chats.** Confirmado ao vivo: não existe
  `list-groups`/`search-chats` entre as 9 tools, então não há como resolver
  nome de grupo → `groupId` só com o MCP. Precisa vir de fora (painel Z-API
  ou API REST clássica) antes de qualquer chamada que dependa de `groupId`.
- Formato exato de `groupId` aceito por `group-metadata` (e pelas outras
  tools de grupo) ainda não confirmado com sucesso — só confirmado que o
  código de convite (`chat.whatsapp.com/<codigo>`) não funciona (erro 400).
- Schemas de retorno de `send-image`, `send-video`, `group-add-participant`,
  `group-remove-participant`, `group-add-admin`, `group-remove-admin` ainda
  não foram observados na prática — não assumir formato até testar. O
  envelope genérico (`content[0]['text']` como JSON string) já é conhecido
  desde `group-create`; falta confirmar os campos de negócio específicos de
  cada tool.
- Schema completo do payload do webhook `on-message-received` ainda não foi
  capturado (próximo passo do experimento da Fase 0).
- Doc oficial da Z-API menciona "mais tools planejadas" — revalidar esta lista
  perto da data de entrega do hackathon rodando `list-tools` novamente.
- Rate limits e comportamento em caso de token revogado ainda não testados.
