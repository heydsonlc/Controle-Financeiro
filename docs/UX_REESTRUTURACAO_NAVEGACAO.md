# Reestruturação da Navegação e Organização dos Módulos

## 1. Contexto

A tela de Configurações passou a concentrar itens que não são apenas preferências ou parâmetros do sistema. Com o amadurecimento do Controle Financeiro, áreas como Categorias, Receitas, Patrimônio, Contas Bancárias, Veículos, Cartões de Crédito e Financiamentos deixaram de ser simples ajustes e passaram a representar módulos de gestão ou cadastros recorrentes.

Essa concentração dificulta a evolução visual e funcional do sistema, aumenta a sobrecarga da tela de Configurações e torna menos claro para o usuário onde cadastrar, consultar e operar cada tipo de informação.

## 2. Problema

Módulos como contas, cartões, veículos, receitas, patrimônio e financiamentos precisam ser tratados como áreas próprias do sistema, não como simples configurações.

Quando cadastros e fluxos operacionais ficam escondidos dentro de Configurações, o aplicativo passa a parecer menos organizado e menos próximo de um sistema administrativo maduro. A navegação também se torna menos previsível, especialmente para itens usados com frequência.

## 3. Diretriz de Solução

A evolução da interface deve adotar uma estrutura visual com:

- menu lateral principal;
- barra superior de contexto;
- faixa de ações por módulo;
- ícones monocromáticos e padronizados;
- Configurações enxuta, reservada a preferências e parâmetros globais.

Essa diretriz é visual e organizacional. Ela não altera regras financeiras, cálculos, importadores, serviços, banco de dados ou contratos de negócio existentes.

## 4. Nova Organização Conceitual

A navegação principal deve separar claramente operação diária, gestão financeira, cadastros auxiliares e configurações do sistema.

### Dashboard

- Dashboard

### Operação

- Lançamentos
- Movimentações
- Planejamento / Orçamentos

### Gestão Financeira

- Contas Bancárias
- Cartões de Crédito
- Receitas
- Despesas Recorrentes
- Financiamentos
- Patrimônio

### Cadastros

- Categorias
- Veículos
- Pessoas / Favorecidos, se existir ou for planejado

### Sistema

- Configurações
- Logs do Sistema, se aplicável

Essa estrutura poderá ser refinada durante os MVPs de reestruturação, mas a premissa deve ser mantida: módulos operacionais e cadastros recorrentes não devem permanecer escondidos em Configurações.

## 5. Configurações

Configurações deve concentrar apenas itens realmente sistêmicos, como:

- preferências de aparência;
- comportamento do sistema;
- backup;
- importação/exportação geral;
- parâmetros globais;
- segurança/usuário, se aplicável;
- integrações futuras, se aplicável.

Itens que representam cadastros, consultas recorrentes ou gestão financeira devem migrar para módulos próprios no menu lateral, ainda que internamente reaproveitem telas, componentes ou endpoints existentes durante a transição.

## 6. Faixa de Ações

Cada tela ou módulo deve possuir uma faixa de ações própria, posicionada abaixo da barra superior ou no início da área de conteúdo.

Essa faixa deve substituir botões grandes espalhados pela interface e agrupar comandos específicos do módulo atual. As ações devem ser representadas preferencialmente por ícones monocromáticos com tooltip.

Ações gerais esperadas:

- novo registro;
- consultar;
- filtrar;
- atualizar;
- exportar;
- importar;
- ajustes específicos da tela.

Exemplos por módulo:

- Contas Bancárias: nova conta, consultar conta, atualizar, exportar.
- Veículos: novo veículo, consultar veículo, custos de uso, manutenções, financiamento.
- Cartões de Crédito: novo cartão, consultar cartão, faturas, limites, ajustes.

Texto visível deve ser usado apenas quando necessário para clareza. A ação principal pode receber texto quando isso melhorar a leitura, mas o padrão preferencial para comandos recorrentes deve ser ícone com tooltip.

## 7. Padrão Visual dos Ícones

Todos os ícones da nova navegação lateral, barra superior e faixa de ações devem seguir padrão monocromático.

Regras obrigatórias:

- não usar emojis como ícones;
- não usar ícones coloridos;
- não misturar famílias visuais diferentes;
- preferir ícones em estilo outline/traço;
- Botões devem manter ícones, tooltips, tamanho e alinhamento consistentes;
- usar uma única biblioteca visual sempre que possível, como Lucide, Heroicons, Bootstrap Icons ou outra biblioteca já existente no projeto;
- a cor dos ícones deve seguir o tema visual do sistema;
- a variação de cor deve ocorrer apenas por estado: normal, hover, ativo/selecionado, desabilitado e alerta/erro quando houver significado funcional;
- espessura, tamanho e alinhamento dos ícones devem ser padronizados;
- botões de ação devem usar ícone com tooltip;
- texto visível deve ser usado apenas quando necessário para clareza.

A padronização deve manter o visual limpo, profissional e consistente, evitando aparência improvisada, excesso de cores ou mistura de estilos.

## 8. MVPs de Reestruturação

### MVP UX-1 - Base da nova navegação

Objetivo: criar a estrutura base de layout com menu lateral, barra superior de contexto e área principal de conteúdo.

Escopo:

- criar shell visual reutilizável;
- definir grupos do menu lateral;
- definir estado ativo do menu;
- preservar rotas/telas existentes;
- não alterar regras de negócio.

### Registro de implementação - UX-1A

O UX-1A inicia a criação do shell visual desktop/web com `base.html`, `layout.css`, sidebar, topbar e estado ativo de menu.

Páginas migradas nesta etapa:

- Dashboard (`/`);
- Configurações (`/configuracoes`).

As demais telas permanecem no layout atual e devem ser migradas em etapa futura, especialmente no UX-1C. A tela Seguro Habitacional (`/financiamentos/seguro`) continua como pendência de UX-1B e não deve ser incluída no menu principal enquanto não for normalizada.

### Registro de implementação - UX-1C

O UX-1C migrou as demais telas do escopo para o shell visual reutilizável (`base.html`), preservando CSS/JS de módulo, IDs, classes internas e comportamento funcional.

Páginas migradas nesta etapa:

- Despesas (`/despesas`);
- Cartões (`/cartoes`);
- Receitas (`/receitas`);
- Lançamentos (`/lancamentos`);
- Financiamentos (`/financiamentos`);
- Contas Bancárias (`/contas-bancarias`);
- Patrimônio (`/patrimonio`);
- Categorias (`/categorias`);
- Veículos (`/veiculos`);
- Preferências (`/preferencias`);
- Importar Cartão (`/importar-cartao`).

A tela Despesas foi preservada visual e estruturalmente, sem redesenho, sem alteração de detalhamentos, modais, filtros ou ícones pequenos de pagamento. Seguro Habitacional (`/financiamentos/seguro`) e Indexadores (`/indexadores`) seguem fora do shell principal e permanecem como pendências diagnósticas.

### MVP UX-2 - Desmembramento de Configurações

Objetivo: remover de Configurações os itens que são módulos ou cadastros operacionais.

Escopo:

- Categorias;
- Receitas;
- Patrimônio;
- Contas Bancárias;
- Cartões de Crédito;
- Veículos;
- Financiamentos;
- Despesas Recorrentes.

Cada item deve passar a ser acessado por menu próprio, ainda que internamente reaproveite a tela ou componente existente.

### Registro de implementação - UX-2

O UX-2 removeu de Configurações os atalhos de módulos operacionais e cadastros já acessíveis pela sidebar.

Configurações deixa de funcionar como hub geral de módulos e passa a ficar reservada a preferências, parâmetros globais e futuras configurações sistêmicas. Os módulos removidos continuam acessíveis pela navegação lateral.

### MVP UX-3 - Faixa de ações por módulo

Objetivo: padronizar a faixa de ações de cada tela.

Escopo:

- novo;
- consultar;
- filtrar;
- atualizar;
- exportar/importar quando aplicável;
- ajustes específicos.

As ações devem usar ícones monocromáticos com tooltip.

### Registro de implementação - UX-3A

O UX-3A criou a infraestrutura reutilizável da faixa de ações por módulo, sem aplicar a faixa em telas funcionais.

O shell `base.html` passou a expor o bloco opcional `action_bar`, posicionado abaixo da topbar e antes do conteúdo principal. O `layout.css` recebeu classes globais para `module-actionbar`, grupos de ações e botões com ícones monocromáticos.

Nenhuma tela sensível foi alterada, nenhum botão existente foi movido e a aplicação real da faixa em telas simples fica reservada para o UX-3B.

### Registro de implementação - UX-3B-1

O UX-3B-1 aplicou a faixa de ações na tela Categorias (`/categorias`) como primeira validação real do padrão criado no UX-3A.

A ação principal "Nova Categoria" foi movida para a `action_bar`, reaproveitando o mesmo fluxo de abertura do modal. As ações contextuais de editar e excluir categoria permaneceram na listagem, sem alteração de JavaScript, API, banco ou regras financeiras.

Despesas, Cartões, Financiamentos e demais telas sensíveis seguem fora desta etapa.

### Registro de implementação - UX-3B-2

O UX-3B-2 aplicou a faixa de ações na tela Contas Bancárias (`/contas-bancarias`), usando o mesmo padrão validado em Categorias.

A ação primária "Nova Conta" foi movida para a `action_bar`, reaproveitando o fluxo existente de abertura do modal. Filtros, extrato, ajuste manual, editar, inativar e reativar permaneceram nos locais originais, próximos aos seus contextos.

Não houve alteração de JavaScript funcional, CSS de módulo, regra de saldo, API, banco ou regras financeiras.

### Registro de implementação - UX-3B-3

O UX-3B-3 aplicou a faixa de ações na tela Receitas (`/receitas`), mantendo o padrão validado em Categorias e Contas Bancárias.

A ação primária "Nova Fonte" foi movida para a `action_bar`, reaproveitando o mesmo fluxo de abertura do modal de fonte de receita. Filtros, cards, listagens, consolidação, registro, edição e exclusão permaneceram nos locais originais.

Não houve alteração de JavaScript funcional, CSS de módulo, lógica de receitas previstas/realizadas, API, banco, dashboard ou regras financeiras.

### Registro de implementação - UX-3B-4

O UX-3B-4 aplicou a faixa de ações na tela Patrimônio (`/patrimonio`), mantendo o padrão validado em Categorias, Contas Bancárias e Receitas.

As ações globais "Nova Caixinha" e "Nova Transferência" foram movidas para a `action_bar`, reaproveitando os mesmos fluxos de abertura dos modais existentes. Abas, caixinhas, transferências, saldos, metas, edição, inativação e remoção permaneceram nos locais originais.

Não houve alteração de JavaScript funcional, CSS de módulo, lógica patrimonial, API, banco ou regras financeiras.

### Registro de implementação - UX-3B-5

O UX-3B-5 avaliou telas médias para expansão da faixa de ações.

A tela Lançamentos (`/lancamentos`) recebeu a `action_bar` com a ação global "Novo Lançamento", reaproveitando o mesmo fluxo de abertura do modal existente. Filtros, receitas pendentes, confirmação de recebimento, histórico, edição, exclusão e modais permaneceram nos locais originais.

Preferências (`/preferencias`) foi preservada sem `action_bar` neste lote porque as ações de salvar dependem da aba ativa e há ações de backup/reset/importação com contexto específico. Importar Cartão (`/importar-cartao`) também foi preservada sem `action_bar` por funcionar como wizard por etapas, onde os botões devem permanecer dentro de cada passo.

Não houve alteração de JavaScript funcional, CSS de módulo, lógica financeira, API, banco ou regras financeiras.

### Registro de implementação - UX-3C-1

O UX-3C-1 aplicou a faixa de ações na tela Cartões (`/cartoes`) como primeira tela mais complexa do ciclo UX-3C.

A ação global "Novo Cartão" foi movida para a `action_bar`, reaproveitando o mesmo fluxo de abertura do modal de cartão. Cards/listagem, edição de cartão, revelação de CVV, categorias internas, limites/orçamentos, faturas, lançamentos e demais ações contextuais permaneceram nos locais originais.

Não houve alteração de JavaScript funcional, CSS de módulo, lógica de cartão/fatura, API, banco ou regras financeiras.

### Registro de implementação - UX-3C-2

O UX-3C-2 aplicou a faixa de ações na tela Financiamentos (`/financiamentos`) como continuidade do ciclo UX-3C.

A ação global "Novo Financiamento" foi movida para a `action_bar`, reaproveitando o mesmo fluxo de abertura do modal de financiamento. Lista/cards, parcelas, pagamentos, amortizações, demonstrativo anual, evolução de saldo, seguro habitacional, regeneração de parcelas e demais ações contextuais permaneceram nos locais originais.

Não houve alteração de JavaScript funcional, CSS de módulo, lógica de financiamento, API, banco ou regras financeiras.

### Registro de implementação - UX-3C-3

O UX-3C-3 aplicou a faixa de ações na tela Veículos (`/veiculos`), mantendo o padrão já validado nas telas anteriores.

As ações globais "Novo Veículo" e "Transporte por App" foram movidas para a `action_bar`, reaproveitando os mesmos fluxos de abertura dos modais existentes. Lista/cards, comparativos, custos, manutenção, financiamento de veículo, simulações e demais ações contextuais permaneceram nos locais originais.

Não houve alteração de JavaScript funcional, CSS de módulo, lógica de veículos, API, banco ou regras financeiras.

### Registro de revisão - UX-3-REVIEW FINAL

O UX-3-REVIEW FINAL revisou as telas com `action_bar` já aplicada: Categorias, Contas Bancárias, Receitas, Patrimônio, Lançamentos, Cartões, Financiamentos e Veículos.

A revisão confirmou consistência estrutural de títulos, subtítulos, botões, SVGs monocromáticos, alinhamento e responsividade básica. Foi removida a duplicidade visual residual dos botões antigos em Veículos, mantendo os mesmos handlers e fluxos de modal. Nenhuma nova tela recebeu `action_bar` nesta revisão.

Não houve alteração de JavaScript funcional, CSS de módulo, rotas, APIs, banco, regras financeiras ou telas fora do escopo. Despesas, Preferências, Importar Cartão, Configurações, Seguro Habitacional e Indexadores permaneceram sem alteração.

### MVP UX-4 - Padronização visual dos ícones e estados

Objetivo: uniformizar ícones, cores, tamanhos, estados ativos e hover.

Escopo:

- remover emojis;
- remover ícones coloridos;
- padronizar biblioteca;
- criar classes CSS/tokens visuais;
- garantir consistência entre menu lateral, barra superior e ações.

### Registro de implementação - UX-4B

O UX-4B iniciou a padronização dos ícones gerados dinamicamente por JavaScript em telas de baixo e médio risco.

Foram cobertos os arquivos `contas_bancarias.js`, `receitas.js`, `lancamentos.js` e `cartoes.js`, substituindo emojis e símbolos funcionais de botões por SVGs inline monocromáticos com `currentColor`.

Despesas, Financiamentos, Patrimônio, Dashboard e Seguro Habitacional permanecem fora desta etapa e devem ser tratados apenas em MVPs específicos.

### Registro de implementação - UX-4C-1

O UX-4C-1 padronizou ícones dinâmicos remanescentes em `financiamentos.js` e `dashboard.js`, cobrindo casos com semântica visual de seguro, indicadores, alertas, datas, loading e notificações.

Os emojis e símbolos foram substituídos por SVGs inline monocromáticos com `currentColor` ou removidos quando o texto já preservava a mensagem. Não houve alteração de cálculo financeiro, APIs, templates, gráficos, modais ou fluxos de financiamento.

Despesas, Patrimônio JS e Financiamento Seguro permaneceram fora desta etapa.

### MVP UX-5 - Refinamento de consultas

Objetivo: criar ou consolidar padrões de consulta dentro dos módulos.

Escopo:

- campo de busca;
- filtros;
- tabelas/listagens;
- estados vazios;
- botão de limpar filtro;
- preservação da usabilidade em telas com muitos registros.

## 9. Regras de Preservação

A reestruturação visual deve preservar integralmente:

- regras financeiras existentes;
- cálculos de previsto e executado;
- comportamento de faturas, contas, receitas, despesas, financiamentos e patrimônio;
- dados já cadastrados;
- importadores;
- serviços;
- contratos de API;
- banco de dados;
- filosofia de consciência financeira sem julgamento.

Durante a migração, rotas e telas existentes devem ser preservadas sempre que possível. A reorganização deve priorizar navegação, apresentação e clareza de acesso, sem alterar o significado dos dados.

## 10. Pendências Futuras

A estrutura definitiva do menu poderá ser refinada conforme os módulos amadureçam e conforme o uso real revele novos padrões de consulta e operação.

Pontos em aberto para validação futura:

- confirmação dos nomes finais dos grupos do menu lateral;
- definição da biblioteca oficial de ícones;
- definição dos tokens visuais de tamanho, cor, hover e estado ativo;
- decisão sobre Pessoas / Favorecidos;
- decisão sobre Logs do Sistema;
- alinhamento visual gradual com o padrão adotado no projeto Orçamento Bertha.

## Diretrizes Complementares

A reestruturação visual deve considerar também as diretrizes registradas em [WEB_MOBILE_SEGURANCA_POSTGRESQL.md](WEB_MOBILE_SEGURANCA_POSTGRESQL.md), especialmente:

- Aplicação web com experiência principal desktop;
- Playwright E2E como Validação padrão antes dos próximos MVPs de UX;
- shell visual desktop/web deve considerar responsividade futura desde a base;
- mobile focado inicialmente na tela Despesas;
- Despesas mobile depende de Segurança, Autenticação e proteção global antes de qualquer exposição externa;
- Autenticação e Segurança como pré-requisitos para qualquer exposição externa;
- PostgreSQL local em desenvolvimento e PostgreSQL DigitalOcean em produção.

A execução dos MVPs de UX deve respeitar a ordem recomendada no documento complementar: primeiro documentação, depois base Playwright E2E, em seguida UX-1A. Essa ordem protege a evolução visual contra regressões de Navegação e carregamento das rotas principais.
