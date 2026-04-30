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

### MVP UX-4 - Padronização visual dos ícones e estados

Objetivo: uniformizar ícones, cores, tamanhos, estados ativos e hover.

Escopo:

- remover emojis;
- remover ícones coloridos;
- padronizar biblioteca;
- criar classes CSS/tokens visuais;
- garantir consistência entre menu lateral, barra superior e ações.

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
