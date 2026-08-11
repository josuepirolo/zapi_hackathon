# DELEGA
## Desafio MCP Z-API 2026 — Project Context

> Documento mestre de contexto, visão, arquitetura e restrições do projeto.

---

# 1. CONTEXTO

Este projeto está sendo desenvolvido especificamente para o:

**Desafio MCP Z-API 2026**

Período oficial:
- Início: 10/08/2026
- Encerramento: 16/08/2026

O projeto deve obrigatoriamente combinar:

- WhatsApp
- Inteligência Artificial
- Server MCP oficial da Z-API

O projeto foi iniciado após a confirmação oficial da inscrição no hackathon.

Todo desenvolvimento específico deste projeto deve ser realizado neste
repositório novo, preservando histórico de commits e evolução técnica.

Não reutilizar uma aplicação pronta anterior como implementação do projeto.

Ideias, conceitos, padrões arquiteturais, bibliotecas e componentes genéricos
podem ser utilizados conforme permitido pelo regulamento.

---

## 1.1 Referências Oficiais

### Página oficial do desafio
https://z-api.io/hackathon-desafio-server-mcp-do-zapi

### Regulamento oficial completo
https://z-api.io/regulamento-desafio-server-mcp-do-z-api/

### Server MCP Z-API
https://mcp.z-api.io/mcp

### Documentação oficial Z-API
https://developer.z-api.io/

---

## 1.2 Instância do Hackathon

A inscrição foi oficialmente confirmada em 10/08/2026.

Conforme item 6.2 do regulamento:

- 1 instância Z-API por inscrição válida;
- sem pagamento;
- sem cartão de crédito;
- sem fornecimento de dados bancários;
- sem adesão a plano pago;
- duração de até 10 dias corridos;
- prazo contado a partir da ativação;
- ativação conforme orientações da organização.

No momento da criação deste documento, as instruções específicas de
ativação da instância ainda não haviam sido recebidas.

---

## 1.3 Server MCP Z-API

Endpoint conhecido:

https://mcp.z-api.io/mcp

IMPORTANTE:

Não assumir quais tools ou capabilities estão disponíveis no Server MCP.

A implementação deverá primeiro realizar descoberta e validação real
das ferramentas disponibilizadas pelo servidor.

---

# 2. OBJETIVO COMPETITIVO

O objetivo não é simplesmente construir um chatbot conectado ao WhatsApp.

Queremos demonstrar uma aplicação em que o Server MCP Z-API seja parte
ESSENCIAL da capacidade do agente de executar tarefas.

Critérios conhecidos de avaliação:

- Uso do Server MCP Z-API: 30%
- Aplicabilidade: 25%
- Execução: 20%
- Criatividade: 15%
- Demonstração: 10%

Portanto, as prioridades são:

1. MCP Z-API profundamente integrado ao fluxo;
2. resolver um problema real;
3. funcionamento confiável;
4. experiência simples;
5. criatividade;
6. excelente demonstração.

O MCP NÃO deve ser utilizado apenas de forma decorativa.

Se retirarmos o MCP Z-API da solução, uma capacidade fundamental do produto
deve deixar de funcionar.

---

# 3. VISÃO DO PRODUTO

Nome provisório:

# DELEGA

Conceito:

**Um agente de delegação através do WhatsApp.**

A ideia fundamental é transformar o WhatsApp de uma simples interface
conversacional em um canal através do qual um agente de IA consegue receber
objetivos e agir para resolvê-los.

O usuário não deve precisar microgerenciar o agente.

Princípio central:

> Se o usuário precisa executar trabalho operacional que poderia ser realizado
> pelo agente, o agente está errado.

Outra forma de expressar a proposta:

> Não converse com uma IA para descobrir como fazer.
> Diga o que precisa e deixe o agente trabalhar.

Possível tagline:

> DELEGA — Menos conversa. Mais coisas resolvidas.

---

# 4. PROBLEMA

Hoje grande parte da coordenação cotidiana acontece pelo WhatsApp.

Exemplos:

- marcar horários;
- consultar disponibilidade;
- negociar datas;
- falar com prestadores;
- confirmar serviços;
- coordenar reuniões;
- solicitar informações;
- acompanhar solicitações;
- combinar compromissos.

Mesmo quando uma IA ajuda o usuário a decidir o que fazer, frequentemente
a execução ainda depende do próprio usuário.

Exemplo tradicional:

Usuário:
"Preciso trocar o óleo do carro."

IA:
"Você pode procurar oficinas próximas, entrar em contato e perguntar..."

O usuário continua executando o trabalho.

O DELEGA pretende mudar isso.

Usuário:

"Preciso trocar o óleo do carro essa semana.
Veja com a oficina algum horário depois das 16h."

A partir daí, o agente trabalha.

---

# 5. TESE DO PRODUTO

A grande ideia deste projeto é:

## WhatsApp como protocolo humano para agentes.

Milhões de pessoas e empresas já podem ser alcançadas pelo WhatsApp.

Um prestador de serviço não precisa possuir:

- API;
- MCP;
- integração específica;
- sistema moderno;
- automação própria.

Se ele consegue conversar pelo WhatsApp, potencialmente um agente pode
interagir com ele utilizando linguagem natural.

Isso permite que IA opere na "última milha humana".

Exemplos:

- oficina;
- restaurante;
- barbearia;
- clínica;
- pet shop;
- fornecedor;
- imobiliária;
- prestador autônomo;
- hotel;
- escola;
- pequenas empresas.

O WhatsApp passa a funcionar como ponte entre:

**Agentes digitais e pessoas reais.**

---

# 6. EXPERIÊNCIA DESEJADA

Exemplo principal do MVP:

Usuário envia:

"Preciso trocar o óleo do carro essa semana.
Veja com a oficina um horário depois das 16h."

O agente:

1. entende o objetivo;
2. identifica as restrições;
3. cria uma tarefa;
4. determina a próxima ação;
5. utiliza o Server MCP Z-API para entrar em contato com a oficina;
6. aguarda uma resposta;
7. correlaciona a resposta com a tarefa;
8. interpreta a disponibilidade;
9. solicita aprovação do usuário somente se necessário;
10. após aprovação, utiliza novamente o MCP para confirmar;
11. finaliza a tarefa;
12. informa o resultado.

Experiência esperada:

Usuário:

"Preciso trocar o óleo essa semana. Depois das 16h."

DELEGA:

"👍 Deixa comigo."

Depois:

"Encontrei quinta às 17h. Posso confirmar?"

Usuário:

"Pode."

DELEGA:

"✅ Resolvido.
Troca de óleo confirmada para quinta-feira às 17h."

---

# 7. DIFERENÇA PARA UM CHATBOT

Este projeto NÃO deve funcionar como:

USER
  ↓
LLM
  ↓
RESPONSE

O modelo desejado é:

USER
  ↓
GOAL
  ↓
AGENT
  ↓
PLAN
  ↓
TOOLS
  ↓
EXTERNAL WORLD
  ↓
WAIT
  ↓
EVENT
  ↓
AGENT
  ↓
NEXT ACTION
  ↓
RESULT

Portanto:

## O sistema é orientado a objetivos, não apenas a conversas.

---

# 8. CONCEITO DE TASK

A entidade central do domínio será:

`Task`

Uma Task representa algo que o usuário delegou ao agente.

Exemplo conceitual:

{
  "goal": "Agendar troca de óleo",
  "status": "WAITING_EXTERNAL",
  "constraints": {
    "period": "esta semana",
    "after": "16:00"
  },
  "participants": [
    "Oficina"
  ],
  "next_action": "WAIT_EXTERNAL_RESPONSE"
}

IMPORTANTE:

Este JSON é apenas conceitual.

O modelo definitivo deve ser projetado durante a arquitetura.

---

# 9. STATE MACHINE

Estados iniciais conceituais:

CREATED
PLANNING
EXECUTING
WAITING_EXTERNAL
WAITING_USER
NEEDS_APPROVAL
COMPLETED
FAILED
CANCELLED

Fluxo possível:

CREATED
   ↓
PLANNING
   ↓
EXECUTING
   ↓
WAITING_EXTERNAL
   ↓
NEEDS_APPROVAL
   ↓
EXECUTING
   ↓
COMPLETED

Não implementar cegamente esta state machine.

Primeiro avaliar quais estados realmente são necessários para o MVP.

Evitar overengineering.

---

# 10. ARQUITETURA CONCEITUAL

Arquitetura inicial desejada:

WhatsApp
    │
    ▼
Z-API
    │
    ▼
Application
    │
    ├── Agent Orchestrator
    │
    ├── Task Engine
    │
    ├── Conversation Correlation
    │
    ├── Approval Rules
    │
    └── Persistence
    │
    ▼
MCP Client
    │
    ▼
Server MCP Z-API
    │
    ▼
WhatsApp / External Participants

A arquitetura definitiva dependerá das capacidades reais disponibilizadas
pelo Server MCP Z-API.

---

# 11. REGRA CRÍTICA SOBRE O MCP

NÃO assumir quais tools o MCP Z-API possui.

Antes de projetar integrações específicas:

1. configurar conexão com:
   https://mcp.z-api.io/mcp

2. autenticar conforme documentação oficial;

3. executar descoberta das capabilities/tools disponíveis;

4. documentar todas as tools relevantes;

5. testar individualmente as tools necessárias;

6. somente então definir a implementação definitiva.

Criar documentação, por exemplo:

docs/zapi-mcp-capabilities.md

Essa documentação deverá registrar:

- nome da tool;
- finalidade;
- parâmetros;
- retorno;
- limitações;
- como será utilizada pelo DELEGA.

Nunca inventar uma capability do MCP.

---

# 12. SERVER MCP COMO CAPACIDADE DO AGENTE

A arquitetura deve privilegiar:

AGENT
   │
   ▼
MCP CLIENT
   │
   ▼
Z-API MCP SERVER
   │
   ▼
WHATSAPP
   │
   ▼
HUMAN / BUSINESS

Queremos poder explicar para a banca:

> O Server MCP Z-API funciona como uma camada de atuação do agente sobre
> o WhatsApp.

O MCP deve participar de ações reais do fluxo demonstrado.

---

# 13. HUMAN-IN-THE-LOOP

Autonomia NÃO significa executar qualquer coisa sem autorização.

O sistema deve diferenciar:

## LOW RISK

Pode executar automaticamente.

Exemplo:

"Pergunte quais horários estão disponíveis."

## DECISION REQUIRED

Usuário precisa escolher.

Exemplo:

"Existem dois horários possíveis: 16h e 18h."

## COMMITMENT

Pode exigir confirmação antes da execução.

Exemplo:

"Posso confirmar o serviço para quinta às 17h?"

Esse comportamento deve ser simples e previsível no MVP.

---

# 14. CORRELAÇÃO DE CONVERSAS

Problema técnico importante:

Quando uma pessoa externa responder pelo WhatsApp, o sistema precisa determinar:

- quem respondeu;
- a qual usuário pertence;
- a qual Task pertence;
- qual etapa estava aguardando;
- qual contexto deve ser entregue ao agente.

Nunca depender apenas do histórico bruto do LLM.

Persistir estado explicitamente.

---

# 15. IDEMPOTÊNCIA

Mensagens e eventos podem ser recebidos mais de uma vez.

Toda integração relevante deve considerar:

- event/message ID;
- deduplicação;
- idempotência;
- retry seguro.

O agente nunca deve, por exemplo, confirmar duas vezes uma tarefa por causa de
um webhook duplicado.

---

# 16. SEGURANÇA

Nunca armazenar secrets no Git.

Utilizar:

.env

e fornecer:

.env.example

Credenciais que devem permanecer fora do repositório:

- Z-API credentials;
- MCP credentials/tokens;
- OpenAI/LLM keys;
- database credentials;
- qualquer outro segredo.

Logs também não devem expor secrets.

---

# 17. STACK INICIAL

Preferência:

Backend:
- Python 3.12+
- FastAPI

IA:
- OpenAI APIs / Agents quando adequado

Protocolos:
- MCP

Persistência:
- PostgreSQL

Desenvolvimento:
- Docker Compose quando trouxer benefício real

Possível:
- Redis

Porém:

## NÃO adicionar infraestrutura sem necessidade.

Este é um hackathon de poucos dias.

Preferir um monólito modular bem estruturado.

---

# 18. PRINCÍPIOS DE ENGENHARIA

Código deve possuir:

- separação de responsabilidades;
- domínio independente de infraestrutura quando fizer sentido;
- type hints;
- async quando apropriado;
- dependency injection simples;
- interfaces claras;
- tratamento explícito de erros;
- logs estruturados;
- configuração por environment;
- testes das partes críticas.

Evitar:

- abstrações prematuras;
- microservices;
- Kubernetes;
- event buses desnecessários;
- repository pattern aplicado mecanicamente;
- arquitetura excessivamente cerimonial.

Clean Architecture é uma ferramenta, não um objetivo.

---

# 19. POSSÍVEL ORGANIZAÇÃO

Não tratar esta estrutura como obrigatória:

src/
├── domain/
│   ├── tasks/
│   └── conversations/
│
├── application/
│   ├── agents/
│   ├── tasks/
│   └── orchestration/
│
├── infrastructure/
│   ├── database/
│   ├── mcp/
│   ├── zapi/
│   └── llm/
│
├── interfaces/
│   └── http/
│
└── main.py

Antes de criar diretórios, avaliar se cada camada é necessária.

---

# 20. OBSERVABILIDADE

Para o hackathon, precisamos conseguir enxergar claramente:

Task criada
    ↓
Agent decidiu ação
    ↓
MCP tool chamada
    ↓
Mensagem enviada
    ↓
Resposta recebida
    ↓
Task retomada
    ↓
Agent decidiu
    ↓
Task concluída

Logs devem facilitar:

- debugging;
- demonstração;
- documentação;
- análise de falhas.

---

# 21. DASHBOARD

Dashboard é SECUNDÁRIO.

Não começar pelo frontend.

Se houver tempo, criar uma interface simples mostrando:

## Atenção

Tasks que precisam de decisão do usuário.

## Em andamento

Tasks executadas pelo agente.

## Resolvidas

Tasks concluídas.

Exemplo:

DELEGA
────────────────────────

ATENÇÃO

Jantar sexta
Restaurante ofereceu 19h ou 21h


EM ANDAMENTO

Troca de óleo
Aguardando oficina


RESOLVIDAS

Almoço com Carlos
Amanhã • 13:00

A experiência principal continua sendo WhatsApp.

---

# 22. MVP

O MVP NÃO é:

- marketplace;
- super app;
- CRM;
- assistente universal completo;
- plataforma de automação genérica.

O MVP é:

## Delegação assíncrona de uma tarefa envolvendo uma pessoa externa através
## do WhatsApp utilizando IA + Server MCP Z-API.

Definition of Done:

Uma pessoa consegue:

1. delegar uma tarefa;
2. o sistema interpretar;
3. criar estado persistente;
4. o agente decidir uma ação;
5. executar ação pelo MCP Z-API;
6. interagir com uma segunda pessoa;
7. receber e correlacionar sua resposta;
8. continuar a Task;
9. solicitar aprovação quando necessário;
10. executar a ação final;
11. concluir a Task;
12. informar ao usuário que foi resolvida.

Se isso funciona end-to-end, temos MVP.

---

# 23. CENÁRIO PRINCIPAL DA DEMO

Cenário preferencial:

## Agendamento de troca de óleo.

Usuário:

"Preciso trocar o óleo do carro essa semana.
Veja com a oficina algum horário depois das 16h."

DELEGA:

"Deixa comigo."

MCP Z-API → Oficina:

"Olá! Gostaria de verificar disponibilidade para troca de óleo nesta semana,
após as 16h. Quais horários vocês possuem?"

Oficina:

"Tenho quinta às 17h."

Agente interpreta.

DELEGA → Usuário:

"A oficina tem quinta às 17h. Posso confirmar?"

Usuário:

"Pode."

MCP Z-API → Oficina:

"Perfeito. Pode confirmar quinta-feira às 17h."

Oficina confirma.

DELEGA → Usuário:

"✅ Resolvido.
Troca de óleo confirmada para quinta-feira às 17h."

---

# 24. DEMONSTRAÇÃO

O projeto será apresentado em vídeo de no máximo 5 minutos.

A demonstração deve privilegiar funcionamento REAL.

Objetivo:

Mostrar dois celulares/WhatsApps:

- usuário;
- pessoa/empresa externa.

E o agente no meio.

Evitar slides demais.

Sequência desejada:

Problema
   ↓
Delegação
   ↓
Agente
   ↓
MCP Z-API
   ↓
Pessoa real
   ↓
Resposta
   ↓
Agente
   ↓
Aprovação
   ↓
Execução
   ↓
RESOLVIDO

Depois mostrar rapidamente a arquitetura.

---

# 25. O QUE NÃO FAZER AGORA

Não implementar ainda:

- aplicativo mobile próprio;
- marketplace;
- múltiplos agentes especializados;
- sistema complexo de memória;
- pagamentos;
- dezenas de integrações;
- arquitetura distribuída;
- dashboard sofisticado;
- sistema de usuários empresarial completo.

Primeiro provar o loop:

DELEGATE → ACT → WAIT → RESUME → RESOLVE.

---

# 26. ESTRATÉGIA DE DESENVOLVIMENTO

Trabalhar verticalmente.

Evitar construir todas as camadas antes de existir um fluxo funcional.

Ordem preferencial:

### Milestone 0
Repository + documentação + configuração.

### Milestone 1
Conectar ao MCP Z-API.

### Milestone 2
Descobrir e testar tools.

### Milestone 3
Enviar uma ação real pelo MCP.

### Milestone 4
Receber evento/resposta.

### Milestone 5
Persistir Task.

### Milestone 6
Retomar Task a partir de resposta externa.

### Milestone 7
LLM decidir próxima ação.

### Milestone 8
Human-in-the-loop.

### Milestone 9
Fluxo completo.

Somente depois:

- dashboard;
- áudio;
- refinamentos;
- múltiplos casos.

---

# 27. COMMITS

Manter commits pequenos e semanticamente claros.

Exemplos:

chore: initialize hackathon project

docs: define project vision and MVP

feat: add z-api mcp client

feat: discover z-api mcp tools

feat: implement delegated task model

feat: correlate external whatsapp replies

feat: add approval workflow

feat: complete delegation lifecycle

Não fabricar histórico.

O histórico deve representar o desenvolvimento real.

---

# 28. REGRA PARA AGENTES DE DESENVOLVIMENTO

Claude Code, Cursor ou qualquer outro agente trabalhando neste projeto deve:

1. ler este documento antes de mudanças arquiteturais relevantes;
2. não inventar requisitos;
3. não assumir capabilities externas;
4. pesquisar documentação oficial quando necessário;
5. preservar simplicidade;
6. perguntar quando uma decisão alterar significativamente o escopo;
7. explicar trade-offs relevantes;
8. não adicionar dependências desnecessárias;
9. manter o projeto executável;
10. priorizar o MVP end-to-end.

---

# 29. PRINCÍPIO FINAL

Não estamos construindo um chatbot.

Estamos construindo um sistema no qual:

**uma intenção humana se transforma em uma tarefa executável por um agente.**

O WhatsApp fornece a interface humana.

A IA fornece interpretação e decisão.

O Task Engine fornece continuidade.

E o Server MCP Z-API fornece ao agente capacidade de agir através do WhatsApp.

O objetivo final não é gerar uma boa resposta.

É chegar a:

# RESOLVIDO.