# Diretrizes Web, Mobile, Segurança e PostgreSQL

## 1. Contexto

Após o diagnóstico do MVP UX-1 e seu adendo, foram definidas novas decisões estruturais para a evolução do Controle Financeiro:

- o sistema deve ser tratado como aplicação web;
- a experiência principal permanece orientada ao desktop;
- o primeiro foco mobile deve ser a tela Despesas;
- qualquer exposição externa exige autenticação antes;
- PostgreSQL passa a ser o banco de referência para a evolução do projeto, com PostgreSQL local em desenvolvimento e PostgreSQL DigitalOcean em produção.

Este documento registra diretrizes arquiteturais. Ele não implementa login, não configura PostgreSQL, não altera banco de dados e não modifica regras financeiras.

## Desenvolvimento Local, Dados Descartáveis e Testes E2E

O Controle Financeiro ainda está em fase de Desenvolvimento. Os dados existentes no banco local não são considerados dados reais e não há obrigação de preservar Histórico local antigo durante a evolução técnica.

Durante a fase atual de desenvolvimento, os dados locais não são considerados dados reais. Portanto, o banco local pode ser resetado, recriado ou limpo quando necessário para simplificar a evolução técnica. Essa autorização vale exclusivamente para ambiente local/dev e nunca se aplica a produção, DigitalOcean ou qualquer banco remoto.

Essa diretriz não autoriza exposição web aberta. Mesmo com dados descartáveis, qualquer acesso externo real continua bloqueado até existir autenticação, proteção de APIs, `DEBUG=False`, `SECRET_KEY` segura, HTTPS e revisão de CORS.

### Banco oficial de desenvolvimento

A direção do projeto passa a ser:

**Ambiente local/dev**

- PostgreSQL local;
- `DATABASE_URL` apontando para `localhost`;
- dados de desenvolvimento descartáveis;
- possibilidade controlada de Criação, Recriação de schema e seeds;
- `DEBUG=True` somente em desenvolvimento.

**Ambiente produção/web futuro**

- PostgreSQL DigitalOcean;
- `DATABASE_URL` remoto;
- dados reais;
- `DEBUG=False`;
- `SECRET_KEY` segura;
- autenticação obrigatória;
- HTTPS obrigatório.

**SQLite**

- deixa de ser o fluxo principal de desenvolvimento;
- pode permanecer temporariamente como legado, fallback ou teste;
- não deve ser removido sem script próprio;
- não deve ser usado como referência final da evolução web.

### Operações destrutivas

Mesmo em fase de desenvolvimento, nenhuma operação destrutiva deve ser implícita. Todo script que puder apagar ou recriar dados deve declarar esse risco, limitar a execução ao ambiente local/dev e proibir execução contra banco remoto ou produção.

Operações como drop de tabelas, reset de banco, exclusão de dados, recriação de schema ou limpeza completa só podem ocorrer quando todas as condições abaixo forem verdadeiras:

1. O script declarar explicitamente que a operação é destrutiva.
2. O script limitar a operação ao ambiente local/dev.
3. O script proibir execução contra DigitalOcean, produção ou `DATABASE_URL` remoto.
4. O script exigir conferência visual da `DATABASE_URL` antes da execução.
5. O script orientar backup local se houver qualquer dúvida.
6. O Usuário autorizar expressamente a execução.

Essa autorização nunca se aplica a banco de produção, banco remoto, PostgreSQL DigitalOcean, qualquer `DATABASE_URL` externa ou qualquer ambiente com dados reais.

### Alembic como fonte oficial de evolução de schema (DB-3C — 2026-05-01)

O baseline Alembic oficial foi gerado via banco temporário local vazio (`controle_financeiro_baseline`) e validado com `flask db upgrade`. O banco dev real (`controle_financeiro_dev`) foi marcado com `flask db stamp head` — revision `dd1a552aec6a`.

- `db.create_all()` ainda existe em `backend/app.py` e continua funcional para novos ambientes;
- Alembic passa a ser a referência oficial para **evolução futura** de schema;
- migrations antigas (`migrations/versions_archived/pre_baseline_20260501_085449/`) foram arquivadas fora do scan ativo do Alembic;
- para toda alteração de schema futura: `flask db migrate -m "descricao"` + `flask db upgrade`.

### Arquivamento de migrations custom/SQLite (DB-3D — 2026-05-01)

Scripts históricos fora da chain oficial foram arquivados em `migrations/legacy_sqlite/`.

- `backend/migrations/` foi movido para `migrations/legacy_sqlite/backend_migrations/`;
- scripts custom soltos em `migrations/*.py` foram movidos para `migrations/legacy_sqlite/custom_scripts/`;
- `backend/add_taxa_adm_column.py` foi arquivado junto aos scripts legados;
- `scripts/debug/*.py` foram preservados no local e documentados como debug manual/legado, não como fluxo oficial de schema.

Esses arquivos não devem ser executados no fluxo atual. Podem conter `sqlite3`, `PRAGMA`, `sqlite_master`, caminhos `data/gastos.db`/`financeiro.db`, `ALTER TABLE` manual ou comandos destrutivos. A fonte oficial para evolução futura permanece em `migrations/versions/`, iniciando por `dd1a552aec6a`.

### Playwright E2E como padrão de validação

Playwright E2E será adotado como padrão obrigatório de Validação progressiva dos próximos MVPs. O objetivo é testar fluxos reais em navegador antes de avançar em interface, Segurança, mobile e banco.

Os testes E2E devem validar:

- abertura das páginas principais;
- Navegação sem quebra;
- ausência de erros críticos no console;
- fluxo real em navegador;
- proteção contra regressões visuais e funcionais;
- login, Despesas mobile e baixa de pagamento em fases futuras.

O primeiro MVP sugerido é o **TEST-1 - Base Playwright E2E**, com instalação/configuração apenas quando esse MVP for executado. O escopo inicial deverá incluir estrutura de testes, comando de execução, testes básicos de Navegação, carregamento das principais rotas HTML e base para testes futuros de Autenticação, Despesas e mobile.

Rotas mínimas a validar inicialmente:

- `/`
- `/configuracoes`
- `/despesas`
- `/cartoes`
- `/receitas`
- `/lancamentos`
- `/financiamentos`
- `/contas-bancarias`
- `/patrimonio`
- `/categorias`
- `/veiculos`
- `/preferencias`
- `/importar-cartao`

Fluxos futuros a validar com Playwright:

- Navegação lateral após UX-1A;
- login/logout após SEG-1;
- proteção de rota sem login;
- tela Despesas em viewport mobile;
- abertura do modal de pagamento;
- baixa de despesa;
- filtros de Competência;
- ausência de erros no console.

## 2. Aplicação Web

O Controle Financeiro deve evoluir como aplicação web.

A experiência desktop/web será a experiência administrativa completa, contemplando:

- Dashboard;
- Lançamentos;
- Despesas;
- Receitas;
- Cartões;
- Contas Bancárias;
- Financiamentos;
- Patrimônio;
- Veículos;
- Categorias;
- Configurações;
- demais módulos futuros.

A navegação desktop deve seguir a diretriz registrada em [UX_REESTRUTURACAO_NAVEGACAO.md](UX_REESTRUTURACAO_NAVEGACAO.md):

- menu lateral principal;
- barra superior de contexto;
- faixa de ações por módulo;
- ícones monocromáticos;
- Configurações enxuta.

## 3. Mobile Prioritário: Tela Despesas

No celular, o objetivo inicial não é adaptar todo o sistema. O primeiro uso mobile real deve ser a tela Despesas, por representar a fatura mensal consolidada da vida financeira do usuário.

A experiência mobile inicial deve permitir:

- abrir a tela Despesas;
- consultar obrigações financeiras;
- visualizar valores, vencimentos, status e Competência;
- marcar despesa como paga;
- usar a tela com conforto no toque pelo Usuário.

A solução preferencial futura deve:

- manter a mesma rota `/despesas`;
- aplicar CSS responsivo mais forte abaixo de `768px`;
- usar cards/listas em vez de tabelas largas;
- manter apenas filtros essenciais no mobile;
- priorizar a competência atual;
- manter a Navegação simples no celular;
- tornar o botão de pagamento/baixa grande e fácil de tocar;
- ocultar ou reduzir ações administrativas no celular;
- evitar cadastro completo de despesa no mobile se a experiência ficar ruim;
- manter o backend como fonte única da verdade.

A criação de uma rota `/m/despesas` não é prioridade neste momento. Ela só deve ser considerada se a mesma rota `/despesas` se tornar difícil de manter com qualidade para desktop e mobile.

## 4. Segurança Antes de Exposição Externa

A aplicação não pode ser exposta na internet enquanto não houver autenticação.

O diagnóstico identificou os seguintes riscos:

- Flask-Login instalado, mas ainda não usado;
- Flask-WTF instalado, mas CSRF ainda não ativo;
- ausência de tela de login/logout;
- ausência de proteção `@login_required`;
- ausência de usuário autenticado;
- endpoints de API sensíveis sem proteção;
- CORS permissivo;
- risco crítico se a aplicação for exposta externamente sem autenticação.

Antes de qualquer deploy ou acesso externo, deve existir um MVP de segurança com, no mínimo:

- login/senha;
- sessão Flask;
- proteção de todas as rotas HTML;
- proteção de todos os endpoints de API sensíveis;
- exceção apenas para login, logout, arquivos estáticos e health check, se aplicável;
- `SECRET_KEY` segura em produção;
- `DEBUG=False` em produção;
- HTTPS obrigatório no ambiente externo;
- revisão de CORS;
- análise de CSRF para ações de escrita.

Não basta proteger apenas `/despesas`. A autenticação deve ser global, porque a tela Despesas consome APIs e o restante das APIs financeiras continuaria exposto sem uma proteção abrangente.

### Regra Operacional: Local/Dev vs Internet

Enquanto a aplicação estiver restrita a ambiente local/dev:

- pode permanecer sem login;
- testes manuais podem ser feitos livremente;
- dados locais são descartáveis;
- PostgreSQL local é o banco oficial de desenvolvimento.

Antes de qualquer acesso pela internet:

- implementar login;
- proteger APIs;
- revisar CORS;
- configurar `DEBUG=False`;
- usar HTTPS.

## 5. Banco de Dados: PostgreSQL Local e DigitalOcean

A nova diretriz de banco para a evolução do projeto é:

### Desenvolvimento

- PostgreSQL local;
- `DATABASE_URL` apontando para o banco local;
- `DEBUG=True`;
- dados locais de desenvolvimento;
- nunca apontar para produção durante desenvolvimento.

### Produção/Web

- PostgreSQL DigitalOcean;
- `DATABASE_URL` apontando para o banco da DigitalOcean;
- `DEBUG=False`;
- `SECRET_KEY` segura;
- autenticação obrigatória;
- HTTPS obrigatório;
- variáveis de ambiente controladas.

Antes de implementar a migração para PostgreSQL local, deve existir um diagnóstico próprio.

### MVP DB-1 - Diagnóstico PostgreSQL Local e DigitalOcean

O diagnóstico deve mapear:

- como `DATABASE_URL` é lido hoje;
- como `config.py` separa desenvolvimento, teste e produção;
- estado atual de migrations Alembic;
- existência de migrations custom paralelas;
- fonte da verdade do schema;
- compatibilidade entre SQLite e PostgreSQL;
- SQL cru dependente de SQLite;
- scripts de inicialização;
- scripts de seed/dados de exemplo;
- testes automatizados;
- riscos de apontar para banco errado;
- estratégia para criar banco local;
- estratégia para usar DigitalOcean apenas em produção.

## DB-2A - Preparacao segura para PostgreSQL local

O ambiente `development` passa a aceitar `DATABASE_URL` local para PostgreSQL, desde que a URL aponte claramente para `localhost`, `127.0.0.1` ou `::1`. URLs remotas, DigitalOcean, `ondigitalocean` ou `do-user` devem ser bloqueadas em desenvolvimento antes da aplicacao iniciar.

Se `DATABASE_URL` nao estiver definida, o SQLite local permanece como fallback temporario/legado. O ambiente `testing` continua isolado com SQLite em memoria, e `production` continua exigindo `DATABASE_URL` e `SECRET_KEY` seguras.

Este MVP nao cria banco PostgreSQL, nao roda migrations, nao recria schema e nao altera dados. A compatibilidade de runtime entre SQLite e PostgreSQL, incluindo pontos como `strftime`, fica para o DB-2B.

## DB-2B - Compatibilidade runtime minima com PostgreSQL

O fluxo ativo de cartao iniciou a remocao de dependencias SQLite-specific no runtime. O uso de `func.strftime` em filtros mensais de `backend/services/cartao_service.py` foi substituido por filtro por intervalo mensal calculado em Python, no formato `inicio_mes <= mes_fatura < inicio_mes_seguinte`, compativel com SQLite e PostgreSQL.

Este MVP nao cria banco PostgreSQL local, nao roda migrations e nao altera dados. Scripts, migrations antigas e demais pontos SQLite-specific permanecem pendentes para analise posterior.

## DB-2C - PostgreSQL local validado

O ambiente local de desenvolvimento foi validado com PostgreSQL em `localhost:5432`, banco `controle_financeiro_dev` e usuario local `controle_financeiro`. A `DATABASE_URL` local fica em `.env.local`, que permanece fora do Git.

O schema limpo foi criado pelo mecanismo atual de startup em desenvolvimento (`backend/app.py` com `db.create_all()`), sem migration, sem seed e sem insercao manual de dados. Durante a validacao, o runtime criou apenas 1 registro tecnico em `preferencia`. O SQLite permanece como fallback temporario quando `DATABASE_URL` nao estiver definida.

DigitalOcean, producao e bancos remotos nao foram acessados. A consolidacao da fonte oficial de schema, Alembic e seeds fica para etapa futura.

## DB-2D - Validacao funcional minima no PostgreSQL local

O PostgreSQL local foi validado funcionalmente com a aplicacao em `development`, usando `controle_financeiro_dev` em `localhost:5432`. O health check respondeu `status=ok`, `database=connected` e `environment=development`.

Foram criados dados locais descartaveis pelo fluxo normal de API, todos com prefixo `TESTE_DB2D_`:

- `TESTE_DB2D_Categoria_20260430_210000`;
- `TESTE_DB2D_Conta_20260430_210000`;
- `TESTE_DB2D_Receita_20260430_210000`.

As listagens de categorias, contas bancarias e receitas confirmaram os registros criados. As rotas de Despesas, Cartoes, Dashboard, Receitas, Contas Bancarias, Configuracoes e demais paginas principais foram validadas sem erro critico. Cartao e despesa complexa nao foram criados neste MVP para evitar geracao de faturas, recorrencias ou contas fora do escopo.

O Playwright manteve `13 passed, 2 skipped`. DigitalOcean, producao e bancos remotos nao foram acessados. Nenhum `DROP`, reset, migration ou alteracao de schema foi executado.

## 6. SQLite

SQLite deve deixar de ser a base principal de desenvolvimento da evolução web do projeto.

Ele pode permanecer temporariamente como:

- legado;
- compatibilidade;
- ambiente de teste;
- base temporária até decisão posterior.

SQLite não deve ser removido sem diagnóstico próprio, não deve ser apagado automaticamente e não deve ser usado como referência final da evolução web.

## 7. Sequência Recomendada de MVPs

### 1. DOCS - Atualização das diretrizes web/mobile/segurança/PostgreSQL/testes

Escopo:

- registrar as decisões atuais;
- consolidar status de desenvolvimento, PostgreSQL local, Segurança e testes;
- status: imediato.

### 2. TEST-1 - Base Playwright E2E

Escopo:

- criar infraestrutura mínima de testes E2E;
- validar páginas principais;
- detectar erros críticos no console;
- preparar proteção contra regressão;
- preparar base para Autenticação, Despesas mobile e baixa de pagamento.

### 3. UX-1A - Shell visual desktop/web

Escopo:

- `base.html`;
- `layout.css`;
- sidebar;
- topbar;
- Dashboard;
- Configurações;
- sem mexer em Despesas;
- sem mexer em banco;
- sem mexer em autenticação.

### 4. DB-1 - PostgreSQL local como banco oficial de desenvolvimento

Escopo:

- diagnóstico/implementação controlada;
- criar ambiente local PostgreSQL;
- ajustar ambiente local;
- validar schema limpo;
- dados locais podem ser recriados;
- não apontar para DigitalOcean em desenvolvimento.

### 5. SEG-1 - Autenticação mínima e proteção global

Escopo:

- login/sessão;
- proteção de rotas HTML;
- proteção de APIs;
- preparo mínimo para acesso web seguro.

### 6. UX-MOBILE-1 - Despesas mobile

Escopo:

- mesma rota `/despesas`;
- layout em cards;
- botão de pagamento adequado ao toque;
- filtros simplificados;
- sidebar oculta/drawer no mobile;
- preservação integral das regras financeiras.

### 7. UX-1B - Normalização da tela Seguro Habitacional

Escopo:

- corrigir `financiamento_seguro.html`;
- remover Bootstrap/Font Awesome órfãos;
- integrar ao padrão visual.

### 8. UX-1C - Migração das demais telas para base.html

Escopo:

- migrar módulos restantes para o shell visual;
- preservar contratos de API e regras financeiras.

### 9. UX-2 - Desmembramento de Configurações

Escopo:

- retirar módulos operacionais de Configurações;
- deixar Configurações apenas para preferências/parâmetros globais.

### 10. UX-3 - Faixa de ações por módulo

Padronizar ações por módulo.

### 11. UX-4 - Padronização completa de ícones

Padronizar biblioteca, estados visuais, tamanhos e cores.

### 12. UX-5 - Consultas e filtros avançados

Consolidar busca, filtros, listagens, estados vazios e limpeza de filtros.

### 13. DEPLOY-1 - Publicação web controlada

Somente quando houver decisão de publicar. Depende de Autenticação, PostgreSQL, configuração segura e nenhuma exposição externa sem proteção.

## 8. Regras Preservadas

Estas diretrizes não alteram os contratos financeiros já consolidados.

Permanecem invioláveis:

- Despesas = fatura mensal consolidada;
- Backend soberano;
- frontend não recalcula valores;
- Conta é a base da tela Despesas;
- categoria é metadado;
- pagamento e baixa seguem regra do backend;
- Cartão gera fatura consolidada;
- Financiamento gera parcelas/contas conforme regra existente;
- API deve respeitar contrato documentado;
- `extrairArray()` deve continuar sendo usado onde aplicável;
- linguagem do sistema deve continuar descritiva, sem julgamento financeiro.

## 9. Fora de Escopo

Este documento não implementa:

- autenticação;
- tela de login/logout;
- proteção de rotas;
- configuração de PostgreSQL;
- alteração de `.env`;
- alteração de `config.py`;
- migrations;
- alterações em templates;
- alterações em CSS;
- alterações em JavaScript;
- alterações em backend;
- alteração de contratos de API;
- alteração de regras financeiras.
