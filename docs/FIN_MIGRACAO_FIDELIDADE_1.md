# FIN-MIGRACAO-FIDELIDADE-1 — Diagnóstico de fidelidade (Flask original × novo aplicativo)

**Natureza:** só diagnóstico. Nada foi alterado no Flask, no `gastos.db`, no Supabase, na prévia publicada nem no GitHub.

**Fontes:**
- código de `backend/`, `frontend/templates`, `frontend/static` e `web/`;
- **21 capturas de tela do Flask real**, rodando localmente sobre um SQLite novo e vazio em pasta temporária. O script abortaria se a URI apontasse o `gastos.db`, que ficou com o mesmo tamanho e a mesma data de modificação. As capturas ficaram fora do repositório e não contêm dados pessoais.

A prévia publicada (protegida pelo Cloudflare Access) foi analisada pelo código-fonte publicado (`web/src`, versão `c56e1fb`).

**Referência:** daqui em diante, o Flask original é a referência de conclusão: visual, navegação e operação.

---

## A. Inventário funcional do Flask

**Volume:**
- 16 páginas (`frontend/templates`, todas herdam `base.html`, exceto login e indexadores);
- cerca de 280 rotas de API em 22 grupos (`backend/routes`);
- cerca de 27 mil linhas de JS e 25 mil de CSS (`frontend/static`);
- cerca de 21,6 mil linhas de serviços (`backend/services`).

| Módulo (menu) | Rota | Template | JS | CSS | O que o usuário faz | Dependências (API/serviço) | Novo app |
|---|---|---|---|---|---|---|---|
| Dashboard | `/` | `index.html` | `dashboard.js`, `categoria_cartao_icones.js` | `dashboard.css` | 8 cartões de resumo (saldo consolidado, fluxo 30 dias, faturas em aberto, recorrências ativas, despesas previstas, contas a vencer, alertas, mobilidade), cartões e limites, consumo por categoria do cartão, gráfico de fluxo de caixa, próximos vencimentos; filtro de período | `/api/dashboard/*` (8 rotas), `dashboard_service` | **Ausente** (a tela inicial do novo app é "Contas do mês") |
| Lançamentos | `/lancamentos` | `lancamentos.html` | `lancamentos.js`, `utils.js` | `lancamentos.css` | Compras do cartão por fatura, parceladas, edição, exclusão, filtros, importação | `/api/cartoes/*` (itens, lançamentos), `cartao_service` | **Parcial**: compras e faturas estão na aba Cartões |
| Despesas | `/despesas` | `despesas.html` | `despesas.js` (3.220 linhas), `utils.js` | `despesas.css` | Lista agrupada por origem e tipo; 6 cartões de resumo; filtros (forma, status, vencimento, competência, busca); nova/editar/excluir; pagar e estornar; consórcio no mesmo formulário; despesa "a partir de documento" | `/api/despesas`, `/api/consorcios`, `/api/despesas-previstas` | **Parcial**: a lista em Contas do mês tem criar, editar, excluir, pagar e estornar. Faltam os filtros, os resumos, o agrupamento, o consórcio e o "a partir de documento" |
| Recorrências | `/recorrencias` | `recorrencias.html` | `recorrencias.js` | `recorrencias.css` | Cadastro de recorrências (despesa, cartão, consórcio), pendências de recorrência rejeitada | `/api/recorrencias`, `/api/consorcios` | **Parcial**: editar e inativar recorrência pelo detalhe da despesa, mais "Gerar contas" e avisos; sem tela própria |
| Receitas | `/receitas` | `receitas.html` | `receitas.js` | `receitas.css` | Fontes, previsões (orçamento), recebimentos, pontual, estorno, resumo mensal, confiabilidade, detalhe por fonte | `/api/receitas/*` (18), `receita_service` | **Parcial**: previsões, receber (parcial) e estornar. Faltam o pontual, o resumo e a confiabilidade |
| Cartões | `/cartoes` | `cartoes.html` | `cartoes.js` | `cartoes.css` | Cadastro de cartões, vínculo de categorias do cartão, limites mensais por categoria | `/api/cartoes`, `/api/categorias-cartao` | **Parcial**: cadastro com fechamento, faturas, compras, pagar e estornar fatura. Faltam os vínculos e limites (só leitura) |
| Contas Bancárias | `/contas-bancarias` | `contas_bancarias.html` | `contas_bancarias.js` | `contas_bancarias.css` | Criar, editar, ativar e inativar conta; extrato; ajuste de saldo; transferência; conferir saldo | `/api/contas/*` (12), `conta_bancaria_service` | **Parcial**: só a leitura (lista em Categorias) e a seção "Movimentos do mês". Faltam cadastro, ajuste e transferência |
| Financiamentos | `/financiamentos`, `/financiamentos/seguro` | `financiamentos.html`, `financiamento_seguro.html` | `financiamentos.js` (2.196), `financiamento_seguro.js` | `financiamentos.css` | Contratos SAC/PRICE (TR), parcelas, pagamento e estorno de parcela, amortização extra, ajuste de saldo devedor, seguro DFI/MIP, documentos, conferências de caixa, demonstrativo, simulação de quitação | `/api/financiamentos/*` (25), `financiamento_service` (3.033), conferência, documento, seguro, `/api/indexadores` | **Ausente** |
| Consórcios | (sem tela própria) | dentro de `despesas.html` e `recorrencias.html` | `despesas.js`, `recorrencias.js` | — | Consórcio como despesa ("É um Consórcio"), parcelas geradas, editar e excluir parcela, contemplação vira receita | `/api/consorcios` (6), `consorcio_receita_service` | **Ausente** (aviso "fica no módulo de consórcios") |
| Patrimônio | `/patrimonio` | `patrimonio.html` | `patrimonio.js` | `patrimonio.css` | Bens (com documentos e imagens, exportar Excel e PDF), contas patrimoniais, transferências | `/api/patrimonio/*` (21) | **Ausente** |
| Documentos Fiscais | `/imposto-renda` | `imposto_renda.html` | `imposto_renda.js` (2.069) | `imposto_renda.css` | Comprovantes (upload e OCR), categorias de IR, documentos da empresa, exportar ZIP, relatórios | `/api/ir/*` (37), `ir_*`, OCR | **Ausente** |
| Categorias | `/categorias` | `categorias.html` | `categorias.js`, `categoria_cartao_icones.js` | `categorias.css` | Categorias de despesa (criar, editar, excluir, logo, palavras-chave); categorias do cartão e vínculos | `/api/categorias`, `/api/categorias-cartao` | **Parcial**: só a leitura; a tela atual mostra contas bancárias e as categorias do 1º módulo |
| Mobilidade | `/veiculos` | `veiculos.html` | `veiculos.js` (3.719) | `veiculos.css` | Veículos, projeções de custos, regras de km, manutenções, financiamento do veículo, cenário ativo, app de transporte, assinaturas | `/api/veiculos` (25), `/api/mobilidade-app`, `/api/despesas-previstas` | **Ausente** (as despesas geradas aparecem em Contas) |
| Importar Cartão | `/importar-cartao` | `importar_cartao.html` | `importar_cartao.js` (3.698) | `importar_cartao.css` | Importar fatura (arquivo) para lançamentos | `importacao_cartao*` | **Ausente** |
| Configurações e Preferências | `/configuracoes` | `configuracoes.html` | `configuracoes.js` | `configuracoes.css` | Preferências; **perfis financeiros** (criar, editar, inativar, padrão); backup e restauração; ferramentas de OCR | `/api/preferencias`, `/api/perfis-financeiros`, `/api/backup`, `/api/ocr` | **Ausente** |
| Ajuda e Manual | `/ajuda` | `ajuda.html` | `ajuda.js` | `ajuda.css` | Manual estático | — | **Ausente** |
| Indexadores | `/indexadores` | `indexadores.html` (fora do menu) | `indexadores.js` | `global.css` | Tabela TR e outros (insumo dos financiamentos) | `/api/indexadores` | **Ausente** |
| Login | `/login` | `login.html` | — | `style.css`, `theme-light.css` | E-mail e senha (usuário único, SEG-1) | sessão Flask | **Equivalente funcional** (Supabase Auth), visual diferente |

**Componentes globais** (`base.html`):
- JS: `auth.js`, `icons.js`, `instituicoes.js`, `formas_pagamento.js`, `contexto_financeiro.js` (troca de perfil), `modals.js`;
- CSS: `style.css`, `layout.css`, `instituicoes.css`, `formas_pagamento.css`, `theme-light.css`.

## B. Mapa visual e de navegação

**Moldura** (`base.html` + `layout.css`), igual em todas as páginas:
- **Barra lateral fixa** à esquerda: marca "Controle Financeiro" e seções com títulos em caixa alta. O item ativo fica em fundo escuro, com ícone SVG em linha e texto.
- **Barra superior:**
  - botão ☰;
  - título da página (`page_title`);
  - à direita: Ajuda, **seletor de perfil**, Alertas, Sair.
- **Barra de ação** da página (`action_bar`): breadcrumb, período ou filtros, "Atualizar", atalhos e o botão principal (por exemplo, "+ Nova despesa").
- **Conteúdo:** cartões de resumo com ícone em círculo colorido, listas e tabelas, painel lateral de resumos e modais (`modals.js`).

**Menu (hierarquia original):**
```
Dashboard
  └ Dashboard
Operação
  ├ Lançamentos
  ├ Despesas
  └ Recorrências
Gestão Financeira
  ├ Receitas
  ├ Cartões
  ├ Contas Bancárias
  ├ Financiamentos
  ├ Patrimônio
  └ Documentos Fiscais
Cadastros
  ├ Categorias
  └ Mobilidade
Ferramentas
  └ Importar Cartão
Sistema
  ├ Configurações e Preferências
  └ Ajuda e Manual
```

**Telas menores:**
- **Até 1024 px:** a barra lateral encolhe para 236 px.
- **Até 768 px:**
  - a barra lateral é **ocultada** (`display: none`);
  - o seletor de perfil vira só o avatar;
  - os cartões passam a 2 colunas;
  - **Defeito preexistente:** o botão ☰ **não tem ação** (nenhum JS o liga). No celular, o Flask não oferece menu de navegação. As capturas confirmam.

**Fluxos típicos:**
- Os formulários abrem em painel ou modal sobre a página. Salvar recarrega a lista e os resumos com mensagem.
- Excluir pede confirmação em modal (despesa recorrente ou consórcio pergunta "só esta" ou "esta e as próximas").
- Atalhos cruzados do Dashboard: Lançamentos, Revisar recorrências, Gerenciar mobilidade.

**Defeitos visuais preexistentes observados** (só registrados):
- Cartões: a coluna direita fica cortada a 1366 px.
- Financiamentos: a barra "Novo financiamento / Cancelar / Salvar financiamento" aparece sem formulário aberto.
- Despesas: os rótulos dos filtros ficam sobrepostos a 1366 px.

**Novo aplicativo (prévia):**
- **Cabeçalho simples:** marca, `select` "Perfil", e-mail, "Sair".
- **Abas** Contas | Receitas | Cartões, mais as setas de mês.
- **Sem barra lateral**, sem dashboard e sem as seções "Operação, Gestão, Cadastros…".
- **Pontos em comum:** usa os mesmos `style.css` e `theme-light.css` do Flask (copiados no build), mas não o `layout.css` (moldura) nem os CSS das páginas.

## C. Perfis Pessoal e Trabalho (Empresa)

**Conceitos distintos:**
- **Perfil financeiro** (`public.perfil_financeiro`: Pessoal = `PESSOAL`, padrão; Empresa = `EMPRESA`, que é o "Trabalho"; outros = `OUTRO`) separa os dados.
- **Usuário autenticado:** no Flask, `Usuario`, único e sem papéis; no novo app, o Supabase Auth.
- **Papel de autorização:** só no novo app (`financeiro.perfil_acesso`: TITULAR ou LEITOR, `pode_gerir`), que decide quem vê e quem altera cada perfil.

| Aspecto | Flask original | Novo aplicativo | Diferença |
|---|---|---|---|
| Onde aparece | Barra superior: avatar (PE/EM), nome, tipo; menu com os perfis, ✓ no ativo e "Configurar perfis" | `select` "Perfil" no cabeçalho de cada página | VISUAL / PERFIL |
| Como alterna | `POST /api/perfis-financeiros/ativo` grava na **sessão do servidor** e a página **recarrega** | Grava em `sessionStorage` por usuário e **recarrega os dados** sem recarregar a página | Comportamento equivalente; mecanismo diferente |
| Persistência na navegação | Sessão do servidor: vale em todas as páginas e abas até sair | `sessionStorage`: vale nas páginas da mesma aba; outra aba volta ao padrão | PERFIL (pequena) |
| Sem escolha | Perfil `padrao` (Pessoal) | O salvo, senão o `padrao`, senão o primeiro | Equivalente |
| Registros sem perfil (legado) | Pertencem ao Pessoal (`condicao_perfil`) | Mesma regra (`financeiro.pertence_ao_perfil`) | Igual |
| Quem vê quais perfis | O usuário logado vê todos | Só os vinculados em `perfil_acesso` (`meus_perfis`) | Novo (segurança), sem perda |
| Separação por perfil | Todas as consultas filtram pelo perfil da sessão (despesas, receitas, cartões, contas, financiamentos…) | Todas as funções recebem o perfil e o banco revalida o acesso | Igual nos módulos migrados |
| Configurar perfis | Configurações: criar, editar (nome, tipo, avatar, cor), inativar, reativar, definir padrão | Não existe (só o administrador, direto no banco) | FUNCIONAL |

**Suporte do Supabase:**
- **Já existe e basta** para preservar a alternância **sem tabela nova**: as mesmas tabelas, `perfil_acesso`, `meus_perfis`, a regra NULL → Pessoal e a autorização por perfil.
- **Falta:** só funções para a gestão de perfis da tela Configurações (criar, editar, inativar, padrão). Elas também precisam criar o vínculo do criador em `perfil_acesso`.
- **Para fidelidade total:** o seletor da barra superior (`contexto_financeiro.js`) pode ser reaproveitado trocando as duas chamadas (`GET` perfis → `meus_perfis`; `POST` ativo → gravar a escolha no navegador). Para manter a mesma escolha em todas as abas, usar `localStorage` em vez de `sessionStorage`.

## D. Matriz de fidelidade

Classificação das diferenças: VISUAL, NAVEGAÇÃO, FUNCIONAL, DADOS, PERFIL, TÉCNICA.

| Funcionalidade | Flask original | Novo aplicativo | Diferença | Classes | Prioridade |
|---|---|---|---|---|---|
| Moldura e menu principal | Barra lateral com 6 seções, barra superior, barra de ação | Cabeçalho simples e 3 abas | Toda a moldura | VISUAL, NAVEGAÇÃO | **Alta** (fase 1) |
| Alternância de perfis | Seletor com avatar na barra superior, recarga, "Configurar perfis" | `select` por página | Visual e gestão de perfis | PERFIL, VISUAL, FUNCIONAL | **Alta** (fase 1) |
| Menu no celular | Inexistente (defeito) | Abas funcionam | Decidir o comportamento | NAVEGAÇÃO | Alta (decisão) |
| Login | Página própria do Flask | Página própria do novo app | Visual | VISUAL | Média |
| Dashboard | Página inicial com 8 indicadores, gráficos, vencimentos | Inexistente (início = Contas do mês) | Módulo inteiro | FUNCIONAL, DADOS, NAVEGAÇÃO, TÉCNICA | Alta |
| Despesas | Página completa (resumos, filtros, agrupamento, painel lateral) | Lista dentro de "Contas do mês", com pagar e estornar | Tela e recursos | VISUAL, NAVEGAÇÃO, DADOS, FUNCIONAL | **Alta** (fase 2) |
| Pagar / estornar despesa | Modal do Flask | Formulário próprio (ajuste justificado, idempotente) | Tela; as regras novas precisam caber no modal original | VISUAL | Alta (fase 2) |
| Recorrências | Página própria | Pelo detalhe da despesa + "Gerar contas" | Tela | NAVEGAÇÃO, VISUAL | Alta (fase 2) |
| Lançamentos (compras) | Página própria | Dentro da aba Cartões | Tela | NAVEGAÇÃO, VISUAL | Alta (fase 2) |
| Cartões (cadastro, limites, vínculos) | Página com lista, detalhe e limites por categoria | Cadastro e faturas na aba Cartões; limites e vínculos só leitura | Gestão de limites e vínculos | FUNCIONAL, VISUAL | Alta (fase 2) |
| Faturas: fechamento, pagar, estornar | Fechamento manual, pagamento no Flask | Fechamento sugerido, pagar e estornar no novo app | Tela | VISUAL | Alta (fase 2) |
| Receitas | Página com fontes, previsões, recebimentos, pontual, resumo, confiabilidade | Previsões, receber e estornar | Pontual, resumo, confiabilidade, tela | FUNCIONAL, DADOS, VISUAL | Alta (fase 2) |
| Contas bancárias | Página com cadastro, extrato, ajuste, transferência, conferir saldo | Só leitura e "Movimentos do mês" | Cadastro, ajuste, transferência, tela | FUNCIONAL, VISUAL, TÉCNICA | **Alta** (essencial para usar sem Flask) |
| Categorias | Cadastro completo e categorias do cartão | Só leitura | Cadastro | FUNCIONAL, VISUAL, TÉCNICA | Alta (fase 2) |
| Financiamentos | Módulo completo (motor de 3 mil linhas) | Inexistente | Módulo inteiro | FUNCIONAL, TÉCNICA | **Essencial** (fase 3) |
| Consórcios | Dentro de Despesas e Recorrências | Inexistente | Módulo inteiro | FUNCIONAL, TÉCNICA | **Essencial** (fase 3) |
| Patrimônio | Página completa | Inexistente | Módulo inteiro | FUNCIONAL, TÉCNICA | Obrigatória (uso confirmado) |
| Documentos Fiscais / IR | Página completa (upload, OCR, ZIP) | Inexistente | Módulo inteiro; o OCR depende de ferramentas no servidor | FUNCIONAL, TÉCNICA | Obrigatória (uso confirmado) |
| Mobilidade (veículos) | Página completa | Inexistente (só as despesas geradas) | Módulo inteiro | FUNCIONAL, TÉCNICA | Obrigatória (uso confirmado) |
| Importar cartão | Página completa | Inexistente | Módulo inteiro | FUNCIONAL, TÉCNICA | **Prioridade elevada** (uso confirmado) |
| Configurações | Preferências, perfis, backup, OCR | Inexistente | Perfis essencial; o backup passa a ser do Supabase; OCR a decidir | FUNCIONAL, PERFIL, TÉCNICA | Perfis: alta; demais: a decidir |
| Ajuda e Manual | Página estática | Inexistente | Página | NAVEGAÇÃO | Baixa (reaproveitamento direto) |
| Débito automático | Baixa automática ao abrir Despesas | Pagamento manual (decisão do FIN-MOVIMENTACOES-1) | Comportamento | FUNCIONAL | A decidir depois |

## E. Mapa de reaproveitamento

**A — direto:**
- **CSS:** `style.css` e `theme-light.css` (já reaproveitados), `layout.css` (moldura), `instituicoes.css`, `formas_pagamento.css` e os CSS por página.
- **Ícones e componentes sem API:** `icons.js` e SVGs, `modals.js`, `instituicoes.js`, `formas_pagamento.js`, `utils.js` (formatação monetária e datas).
- **Ajuda:** `ajuda.html` e `ajuda.js`.

**B — adaptação pequena:**
- **Templates.** Usam só `extends`/`block`, `url_for('static')`, `active_page`, `page_title`, dois laços que geram dias e meses e o erro do login. O HTML resultante pode virar página estática: o `build.mjs` monta cada página com a moldura do `base.html`, troca `url_for` por caminho relativo e marca o item ativo. O HTML que o usuário vê fica **igual**.
- **Seletor de perfil** (`contexto_financeiro.js`): 2 chamadas trocadas.
- **`auth.js`:** passa a usar o Supabase Auth.
- **Login:** visual do Flask, autenticação do Supabase.

**C — adaptação estrutural** (o JS das telas chama a API REST do Flask):
- **O padrão favorável:** quase todos os módulos concentram as chamadas num `fetchJson`/`fetch` por arquivo (`/api/despesas`, `/api/receitas`, `/api/cartoes`, `/api/contas`, …).
- **A recomendação:** uma camada de dados única no navegador que atende, **com o mesmo formato de resposta do Flask**, as rotas que cada tela usa, chamando as funções do Supabase que já existem. Assim o JS original das telas é reaproveitado quase sem mudança.
- **Onde a camada se aplica:**
  - Despesas, Recorrências, Receitas, Lançamentos e Cartões: as funções já existem, falta a camada;
  - Contas Bancárias e Categorias: a escrita precisa de funções novas;
  - Dashboard: 8 consultas, que precisam de funções de leitura.
- **Onde há diferença de regra** (por exemplo, a justificativa de ajuste no pagamento, a confirmação de fatura consolidada e a chave de idempotência), a camada preenche o que for automático e devolve as mensagens do banco nos avisos que a tela original já mostra. Mudanças de tela só onde a regra nova exige uma escolha do usuário.

**D — substituição necessária** (com justificativa):
- **Motores de cálculo em Python** (financiamentos 3 mil linhas, consórcios, dashboard, receitas resumo e confiabilidade, mobilidade). Não rodam no navegador nem no Supabase sem servidor Python. Precisam virar funções no banco, como foi feito com despesas e cartões, conferidas contra o Flask com os mesmos dados de entrada.
- **OCR e importação de PDF** (`ocr_tools`, `cupom_fiscal_parser`, `importacao_cartao*`). Dependem de programas instalados no servidor (poppler, tesseract), sem equivalente direto em Cloudflare Pages ou Supabase. A decisão depende do uso real.
- **Backup e restauração do `gastos.db`.** Perde o sentido com o Supabase, que tem backup próprio. Registrar como substituído, não migrar.
- **Upload de documentos e imagens** (financiamentos, patrimônio, IR). Precisam do Supabase Storage, ainda não configurado.

## F. Plano de implementação

A sequência proposta pelo titular foi mantida, com dois ajustes técnicos justificados.

**Fase 1 — Moldura, navegação e perfis.**
- Converter `base.html` e o login para o build estático.
- Barra lateral, barra superior, barra de ação e seletor de perfil originais.
- Página de Ajuda.
- **Ajuste 1:** criar já aqui a **camada de dados** (com o seletor de perfil como primeiro uso), porque todas as fases seguintes dependem dela.
- **Decisão necessária:** menu no celular (ver G).
- **Pronto quando:** as páginas migradas têm a mesma moldura e o mesmo menu do Flask, lado a lado nas capturas.

**Fase 2 — Telas já atendidas pelo Supabase, com a tela original.** Ordem pelo que já existe no banco:
1. Despesas + Recorrências (inclui pagar e estornar no modal original);
2. Receitas;
3. Lançamentos + Cartões (faturas, pagar e estornar);
4. Contas Bancárias;
5. Categorias.

- **Ajuste 2:** Contas Bancárias e Categorias precisam de **funções de escrita novas** (cadastro, ajuste, transferência, categorias). Sem elas não há uso sem Flask, então entram nesta fase e não na 3.
- **Pronto quando:** cada tela é igual à do Flask e faz as mesmas operações, conferidas pelo titular, além dos testes.

**Fase 3 — Módulos que ainda dependem do Flask.**
1. Dashboard (só leitura, usa dados já migrados).
2. Consórcios (6 rotas e geração de parcelas, que hoje passa pelas despesas).
3. Financiamentos e Indexadores (o maior motor). Migração conferida contra o Flask cenário a cenário: SAC, PRICE, TR, DFI/MIP, amortização, ajuste de saldo devedor, pagamento e estorno de parcela.
4. Configurações (perfis, preferências).
5. **Importar Cartão, com prioridade elevada** (uso confirmado pelo titular), e depois Patrimônio, Documentos Fiscais/IR e Mobilidade, todos obrigatórios.

Cada motor migrado substitui o do Flask. **Não manter dois motores permanentes.**

**Fase 4 — Validação e substituição.**
- Conferência de fidelidade (visual, navegação e resultados financeiros) pelo titular.
- Plano de migração dos dados pessoais.
- Só então a retirada do Flask.

## G. Resumo executivo

1. **Qual é a dimensão da diferença?**
   - **Grande na interface, pequena no motor.** O novo app tem 3 abas e um cabeçalho simples; o Flask tem 15 páginas no menu com moldura própria.
   - Os serviços financeiros mais usados (despesas, recorrências, receitas, cartões, pagamentos, estornos, movimentos e perfis) já estão no Supabase e validados.
   - Ausentes: dashboard, contas bancárias (escrita), categorias (escrita), financiamentos, consórcios, patrimônio, documentos fiscais, mobilidade, importação e configurações.
2. **É possível recuperar a interface sem refazer os serviços?**
   - **Sim.** Os templates quase não usam Jinja (o HTML pode ser servido estático) e o CSS é reaproveitado direto.
   - O JS das telas fala com a API por um ponto central por arquivo: uma camada de dados no formato do Flask, sobre as funções do Supabase, preserva as telas sem refazer os serviços.
3. **Quais módulos podem ser recuperados mais rapidamente?** Moldura, menu, seletor de perfil e Ajuda; depois Despesas, Recorrências, Receitas, Lançamentos e Cartões (o banco já atende).
4. **Como preservar a alternância Pessoal/Trabalho?**
   - Com as estruturas atuais, sem tabela nova: reaproveitar o seletor original da barra superior, ligado a `meus_perfis`, e guardar a escolha em `localStorage` para valer em todas as abas.
   - Falta só a gestão de perfis em Configurações (funções novas).
5. **O que ainda impede a substituição definitiva do Flask?**
   - Financiamentos e Indexadores, Consórcios, Dashboard;
   - escrita de Contas Bancárias e de Categorias;
   - gestão de perfis;
   - e, conforme o uso real, Patrimônio, Documentos Fiscais/OCR, Mobilidade e Importar cartão;
   - por fim, a migração dos dados pessoais.
6. **Qual é o caminho mais curto para uma versão fiel?** Fase 1 (moldura, perfis e camada de dados), depois Fase 2 tela a tela com o HTML, o CSS e o JS originais. As telas sem serviço no banco aparecem no menu como "em migração" até a fase 3.

**Decisões do titular necessárias:**
- **(a)** Menu no celular. O original não tem (defeito); manter a fidelidade sem menu ou ligar o botão ☰ para abrir a mesma barra lateral (correção mínima, sem mudar o visual)?
- **(b)** Uso real de Patrimônio, Documentos Fiscais/IR (com OCR), Mobilidade e Importar cartão: quais entram antes da retirada do Flask.
- **(c)** Página inicial: o Dashboard do Flask (fidelidade) ou "Contas do mês" até o Dashboard ser migrado.
- **(d)** Itens do menu ainda não migrados: ocultar ou mostrar como "em migração".
- **(e)** As regras novas já validadas (ajuste justificado no pagamento, confirmação de fatura consolidada) entram nos modais originais com a menor mudança possível. Confirmar.

## H. Decisões do titular (registradas)

- **(a)** O botão ☰ abre e fecha a mesma barra lateral no celular. É uma correção mínima do defeito do Flask, sem mudar o visual.
- **(b)** **Todos os módulos do Flask são usados**, especialmente **Importar Cartão**. Nenhum módulo é opcional nem fica fora do plano de substituição. Importar Cartão tem **prioridade elevada** nas próximas fases. Essa decisão não amplia a Fase 1, que continua limitada à interface, à navegação e aos perfis.
- **(c)** O Dashboard fica no menu, marcado "Em migração". Até ele ser migrado, a entrada funcional é Contas. Não haverá Dashboard simplificado.
- **(d)** Os itens ainda não migrados aparecem no menu marcados "Em migração", com uma página informativa e nunca quebrada.
- **(e)** As regras novas entram nos modais originais com a menor mudança possível, sempre documentada.
