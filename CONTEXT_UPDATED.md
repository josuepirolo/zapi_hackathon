ATUALIZAÇÃO DE ESCOPO — HACKATHON MCP Z-API

Leia esta instrução integralmente antes de continuar.

Estamos fazendo uma mudança deliberada no escopo funcional do projeto para
maximizar simplicidade, aplicabilidade, capacidade de demonstração e uso
efetivo do Server MCP Z-API dentro do prazo do hackathon.

IMPORTANTE:

NÃO descarte o trabalho técnico já realizado.

Continuam válidos e devem ser preservados:

- conexão real com https://mcp.z-api.io/mcp;
- OAuth 2.1 funcionando;
- persistência/reutilização do token;
- client MCP;
- FastAPI já criado;
- tools/list validado diretamente contra o servidor;
- documentação das capabilities;
- send-text testado com mensagem real;
- qualquer infraestrutura genérica já criada e útil ao novo fluxo.

O que está mudando é o CASO DE USO do produto.

==================================================
1. NOVO OBJETIVO
==================================================

Não vamos mais priorizar, neste hackathon, o conceito amplo de agente pessoal
DELEGA e seu Task Engine genérico.

O novo objetivo é construir uma solução pequena e demonstrável para:

GERENCIAMENTO INTELIGENTE DE GRUPOS DE WHATSAPP COM CONSENTIMENTO,
UTILIZANDO IA + SERVER MCP Z-API.

O foco é provar uma aplicação prática do MCP.

Não estamos construindo uma plataforma genérica, CRM, marketplace,
construtor de agentes ou produto SaaS completo.

PRINCÍPIO:

SIMPLES + FUNCIONAL + APLICÁVEL + MCP NO CENTRO.

==================================================
2. CAPABILITIES MCP JÁ CONFIRMADAS
==================================================

O tools/list REAL do Server MCP Z-API confirmou 9 tools:

Mensageria:

- send-text
- send-image
- send-video

Grupos:

- group-create
- group-metadata
- group-add-participant
- group-remove-participant
- group-add-admin
- group-remove-admin

IMPORTANTE:

A existência e os schemas das 9 tools foram observados diretamente no
servidor MCP autenticado.

send-text já foi efetivamente executada com sucesso através de tools/call,
com mensagem real entregue pelo WhatsApp.

Não existe send-audio entre as tools atualmente observadas.

Não inventar capabilities adicionais.

==================================================
3. FLUXO PRINCIPAL DO MVP
==================================================

O sistema terá um ambiente administrativo mínimo.

ETAPA A — ADMINISTRAÇÃO

Administrador acessa uma página web simples.

Ele cria/configura uma campanha/comunidade, por exemplo:

Nome:
Promoções Hackathon

Descrição:
Grupo de promoções e novidades.

Mensagem de convite:
"Olá! Quer participar do nosso grupo de promoções?"

Mensagem de boas-vindas:
"Pronto! Você agora faz parte do nosso grupo de promoções."

O administrador cria o grupo.

Quando possível e adequado, utilizar:

group-create

Depois podemos utilizar:

group-metadata

para consultar/confirmar os dados do grupo.

O group ID necessário deve ser persistido.

==================================================
4. ENTRADA DO INTERESSADO
==================================================

O interessado NÃO será prospectado automaticamente.

Não buscar pessoas na internet.
Não fazer scraping.
Não enviar mensagens não solicitadas.
Não utilizar números aleatórios.

O próprio interessado inicia uma conversa enviando mensagem para o WhatsApp
conectado à instância Z-API.

Exemplo:

INTERESSADO:

"Olá"

ou

"Quero promoções"

A mensagem inbound chega através do mecanismo suportado pela Z-API
(webhook/evento), pois o MCP atualmente não possui tool de recebimento.

A aplicação identifica o interessado pelo telefone.

Se ainda não houver consentimento registrado, responde:

"Olá! 👋
Quer participar do nosso grupo de promoções e receber novidades por lá?"

A resposta deve permitir:

SIM
NÃO

Não assumir botão interativo via MCP, pois essa capability não foi observada.

Para o MVP, texto simples "SIM" / "NÃO" é suficiente, salvo se outra
capability real já validada permitir algo melhor.

==================================================
5. CONSENTIMENTO
==================================================

Se responder NÃO:

- registrar DECLINED;
- não adicionar ao grupo;
- responder educadamente;
- encerrar o fluxo.

Se responder SIM:

- registrar consentimento;
- salvar timestamp;
- salvar telefone;
- salvar contato mínimo;
- associar contato à campanha/grupo;
- executar group-add-participant através do Server MCP Z-API.

Depois da inclusão bem-sucedida:

utilizar send-text via MCP para enviar mensagem PARTICULAR ao participante:

"Pronto! ✅
Você já faz parte do grupo Promoções Hackathon."

O consentimento precisa existir ANTES da chamada group-add-participant.

==================================================
6. ESTADOS MÍNIMOS
==================================================

Não criar Task Engine genérico.

Não precisamos mais daquela state machine ampla do DELEGA.

Para este MVP, utilizar somente estados necessários ao fluxo.

Exemplo conceitual:

PENDING
ACCEPTED
DECLINED
ADDED
REMOVED

Avalie criticamente se todos são necessários.

Não criar abstração genérica antes da necessidade real.

==================================================
7. MODELO DE DADOS MÍNIMO
==================================================

Precisamos somente do necessário.

Entidades conceituais:

Campaign / Group

- id
- name
- description
- whatsapp_group_id
- invitation_message
- welcome_message
- status
- created_at

Contact / Membership

- id
- phone
- name, se disponível
- consent_status
- consent_at
- campaign_id
- membership_status
- created_at
- updated_at

Não considere este schema definitivo.

Simplifique se possível.

==================================================
8. PAINEL WEB
==================================================

A web é apenas um PAINEL ADMINISTRATIVO / DEMONSTRAÇÃO.

Não é a interface principal do interessado.

O WhatsApp continua sendo a interface do participante.

O painel deve ser extremamente simples.

Idealmente:

1. GRUPO/CAMPANHA
2. PARTICIPANTES
3. CONTEÚDO

Exemplo:

--------------------------------------

Promoções Hackathon

Status: ATIVO
Grupo WhatsApp: criado
Participantes: 4

[ Dados do grupo ]

--------------------------------------

Interessados

João
ACEITOU
ADICIONADO

Maria
AGUARDANDO

Carlos
RECUSOU

--------------------------------------

Conteúdo

[ Enviar texto ]
[ Enviar imagem ]
[ Enviar vídeo ]

--------------------------------------

Não criar:

- dashboard empresarial complexo;
- analytics sofisticado;
- multi-tenant;
- billing;
- autenticação complexa;
- editor de agentes;
- marketplace;
- CRM;
- busca externa;
- sistema de permissões sofisticado.

É um painel funcional para demonstrar o hackathon.

==================================================
9. ADMINISTRAÇÃO DO GRUPO
==================================================

As capabilities de grupo devem ser utilizadas quando fizerem sentido real.

Possibilidades:

group-create
→ criar o grupo da campanha.

group-metadata
→ consultar informações do grupo.

group-add-participant
→ adicionar pessoa após consentimento.

group-remove-participant
→ remover participante quando solicitado/admin decidir.

group-add-admin
→ promover participante autorizado a administrador.

group-remove-admin
→ remover privilégio administrativo.

IMPORTANTE:

Não precisamos forçar todas as tools na primeira versão.

Entretanto, queremos explorar o máximo possível das capabilities do MCP
quando houver justificativa funcional.

Não fazer "bingo de tools".

==================================================
10. CONTEÚDO VIA MCP
==================================================

O painel poderá permitir ao administrador enviar conteúdo utilizando:

send-text
send-image
send-video

Essas ações devem passar pelo Server MCP Z-API quando compatíveis com as
capabilities observadas.

Exemplo:

Administrador seleciona:

"Enviar promoção"

Texto:
"Oferta especial desta semana."

Imagem:
card-promocao.jpg

O sistema utiliza send-image.

Outro exemplo:

Vídeo:
video-promocao.mp4

O sistema utiliza send-video.

Antes de implementar upload complexo de arquivos, verificar exatamente os
schemas já observados dessas tools.

Se link público for suficiente para a demonstração, preferir a solução
mais simples.

==================================================
11. PAPEL DA IA
==================================================

IMPORTANTE:

Não queremos transformar isso apenas em CRUD + automação fixa.

A IA deve ter um papel pequeno, claro e demonstrável.

Exemplos:

- interpretar intenção da mensagem inbound;
- reconhecer interesse em participar;
- interpretar SIM/NÃO mesmo com linguagem natural;
- gerar/responder mensagens contextualizadas;
- decidir qual ação MCP apropriada dentro das regras permitidas.

Exemplos:

"Quero entrar"
"Pode me colocar"
"Sim, quero"
"Tenho interesse"

→ ACCEPT

"Não quero"
"Agora não"
"Prefiro não participar"

→ DECLINE

Entretanto:

A IA NÃO pode adicionar participante sem consentimento interpretado de forma
suficientemente clara.

Em caso de ambiguidade:

perguntar novamente.

==================================================
12. PAPEL DO MCP
==================================================

O Server MCP Z-API deve permanecer ESSENCIAL.

Fluxo esperado:

INTERESSADO
    ↓
WHATSAPP
    ↓
WEBHOOK
    ↓
FASTAPI
    ↓
IA
    ↓
CONSENTIMENTO
    ↓
MCP Z-API
    ↓
group-add-participant
    ↓
MCP Z-API
    ↓
send-text
    ↓
WHATSAPP

Administração:

WEB
 ↓
FASTAPI
 ↓
MCP
 ↓
GROUP MANAGEMENT

Conteúdo:

WEB
 ↓
FASTAPI
 ↓
MCP
 ↓
TEXT / IMAGE / VIDEO

Se removermos o MCP, as principais ações de administração e comunicação do
produto deixam de funcionar.

==================================================
13. DEMONSTRAÇÃO DO HACKATHON
==================================================

A demo precisa ser visual, curta e determinística.

Cenário:

1. administrador cria "Promoções Hackathon";
2. grupo é criado através do MCP;
3. painel mostra grupo ativo;
4. outro celular envia mensagem para o WhatsApp conectado à Z-API;
5. aplicação recebe mensagem;
6. IA identifica interessado;
7. pergunta se deseja participar;
8. usuário responde SIM;
9. consentimento é registrado;
10. MCP executa group-add-participant;
11. usuário aparece dentro do grupo;
12. MCP envia confirmação no privado;
13. painel atualiza participante para ADICIONADO;
14. administrador envia uma imagem promocional;
15. MCP executa send-image;
16. imagem aparece no WhatsApp;
17. opcionalmente demonstrar send-video;
18. opcionalmente promover/remover admin ou remover participante.

Isso deve caber confortavelmente em poucos minutos.

==================================================
14. SEGURANÇA E DEMO CONTROLADA
==================================================

Todos os números usados na demonstração devem ser controlados/autorizados.

Não entrar em contato com empresas ou pessoas aleatórias.

Não descobrir números externamente.

Não adicionar ninguém sem consentimento.

O ambiente deve ser reproduzível e seguro para demonstração.

==================================================
15. PRIORIDADES
==================================================

MUST HAVE:

- grupo criado/configurado;
- webhook inbound funcionando;
- identificação do interessado;
- pergunta de consentimento;
- interpretação SIM/NÃO;
- persistência mínima;
- group-add-participant via MCP;
- send-text via MCP;
- painel mostrando participantes/status;
- fluxo end-to-end funcionando.

SHOULD HAVE:

- group-metadata;
- group-remove-participant;
- envio de imagem;
- atualização do painel em tempo próximo do real.

NICE TO HAVE:

- send-video;
- group-add-admin;
- group-remove-admin;
- animações;
- métricas;
- qualquer refinamento adicional.

==================================================
16. REGRA DE PRAZO
==================================================

Estamos em um hackathon com prazo extremamente curto.

Prioridade absoluta:

FUNCIONAR END-TO-END.

Não aumentar escopo sem necessidade.

Não criar infraestrutura para problemas futuros.

Não construir framework genérico.

Não transformar o projeto em produto completo.

Se uma solução simples resolve o MVP, use a solução simples.

==================================================
17. DOCUMENTAÇÃO EXISTENTE
==================================================

Atualize o PROJECT_CONTEXT.md para refletir oficialmente esta mudança de
escopo.

IMPORTANTE:

Não apague o histórico técnico já validado sobre MCP.

Preserve e atualize:

docs/zapi-mcp-capabilities.md

Registre a mudança como uma decisão arquitetural/de produto.

Se considerar útil, crie:

docs/decisions/001-hackathon-scope-pivot.md

explicando resumidamente:

- escopo anterior;
- motivo do pivot;
- novo escopo;
- por que ele explora melhor o Server MCP Z-API;
- quais componentes técnicos anteriores permanecem válidos.

==================================================
18. SUA PRÓXIMA TAREFA
==================================================

Antes de sair implementando tudo:

1. leia novamente PROJECT_CONTEXT.md;
2. inspecione o código REAL que já existe no repositório;
3. identifique exatamente o que pode ser reutilizado;
4. atualize a documentação para o novo escopo;
5. proponha a arquitetura MÍNIMA necessária;
6. proponha o modelo de dados MÍNIMO;
7. proponha os endpoints MÍNIMOS;
8. proponha o fluxo inbound/outbound;
9. liste o que deve ser removido/ignorado do plano antigo;
10. apresente um plano de implementação vertical.

NÃO reimplemente o que já funciona.

NÃO altere o client MCP funcional sem necessidade.

NÃO quebre OAuth/token persistence já validado.

NÃO comece pelo frontend.

Depois da análise, priorize o primeiro vertical slice:

ADMIN CRIA GRUPO
        ↓
INTERESSADO MANDA MENSAGEM
        ↓
CONSENTIMENTO
        ↓
MCP ADICIONA AO GRUPO
        ↓
MCP CONFIRMA NO PRIVADO

Esse é o primeiro Definition of Done.

Depois dele funcionar, evoluímos para imagem, vídeo e demais operações de
grupo.

Ao final da análise, PARE e apresente o plano antes de implementar mudanças
estruturais significativas.