# História do Projeto — Controle Financeiro

Registro cronológico das versões, fases e decisões relevantes.

---

## v1.0 — Release Completa (2025-12-27)

### Congelamento intencional
O sistema foi congelado em 2025-12-27 para validação no mundo real. O freeze expirou em 2025-02-27. Em 2026-03-30 o desenvolvimento foi retomado com o MVP 0 de limpeza.

**Funcionalidades entregues na v1.0:**
- Dashboard com gráficos, alertas e agenda financeira
- Despesas: recorrentes, pontuais, cartão, consórcio, parcelamento
- Cartões de crédito: fatura consolidada, categorias por cartão (ItemAgregado)
- Receitas: orçamento e realizadas (dual previsto/realizado)
- Financiamentos: SAC/PRICE/Simples, amortização extraordinária, seguro habitacional
- Patrimônio: caixinhas, transferências
- Veículos: registro, projeção de custos, mobilidade por app
- Lançamentos: entrada unificada (cartão, direto, crédito)
- Configurações: hub central com todos os módulos

**Regras técnicas verificadas:**
- Backend Soberano ✅
- Cálculo Dinâmico ✅
- Regra Soberana de Fatura ✅
- Mês como Eixo Soberano ✅
- Cartão como Comportamento ✅
- Previsto vs Executado (ambos legítimos) ✅

---

## Fase 6.1 — Agenda Financeira + Insights Temporais (2025-12)

Adicionada linha do tempo financeira no Dashboard, reorganizando dados já existentes do endpoint `/api/dashboard/alertas` em visualização cronológica. Zero impacto no core financeiro.

---

## Fase 6.2 — Importação Assistida de Fatura CSV (2025-12-28)

**Implementado:**
- Upload de CSV com detecção automática de delimitador
- Normalização de descrições e extração de parcelamento (NN/TT, N DE T)
- Reconhecimento de despesas fixas existentes
- Geração de todas as parcelas (passadas, atual, futuras)
- Idempotência via `compra_id + numero_parcela` (UUID v4)
- Interface em 5 etapas com mapeamento manual de colunas

**Arquivos criados:** `backend/services/importacao_cartao_service.py`, `backend/routes/importacao_cartao.py`, `frontend/templates/importar_cartao.html`, `frontend/static/js/importar_cartao.js`

**Campos adicionados em `LancamentoAgregado`:** `descricao_original`, `descricao_original_normalizada`, `descricao_exibida`, `is_importado`, `origem_importacao`

---

## MVP 0 — Limpeza e Consolidação (2026-03-30)

Retomada do desenvolvimento após +1 ano de freeze.

**Executado:**
- Commit de ~490 linhas de mudanças acumuladas (Contas Bancárias, Receitas, Despesas, frontend)
- Scripts de teste movidos para `tests/` (8 arquivos)
- Scripts de debug/correção movidos para `scripts/debug/` (11 arquivos)
- Arquivos temporários removidos
- Banco vazio (`financial_control.db`) removido
- Documentação consolidada: de 18 para 7 arquivos `.md`

---

## Decisão Arquitetural — Web, Mobile, Segurança e PostgreSQL (2026-04-30)

Após o diagnóstico do MVP UX-1 e seu adendo, foram registradas novas diretrizes para a evolução do sistema:

- tratar o Controle Financeiro como Aplicação web, com experiência principal desktop;
- manter a reestruturação visual baseada em menu lateral, barra superior de contexto e faixa de ações por módulo;
- priorizar a tela Despesas como primeiro foco mobile, por representar a fatura mensal consolidada da vida financeira;
- tratar autenticação e proteção global como bloqueantes para qualquer acesso externo;
- reconhecer a ausência atual de autenticação ativa, mesmo com Flask-Login e Flask-WTF já instalados;
- adotar PostgreSQL local como banco oficial de desenvolvimento;
- reservar PostgreSQL DigitalOcean para produção/web futura;
- reconhecer que os dados locais atuais não são dados reais e podem ser resetados, excluídos ou recriados durante o desenvolvimento;
- limitar qualquer operação destrutiva ao ambiente local/dev, nunca a produção, DigitalOcean, banco remoto ou qualquer `DATABASE_URL` externa;
- adotar Playwright E2E como padrão de Validação progressiva dos próximos MVPs;
- manter Segurança como bloqueante para qualquer acesso externo;
- tratar Despesas como prioridade mobile futura;
- manter SQLite apenas como legado, fallback, compatibilidade temporária ou teste, até diagnóstico próprio.

Essas decisões não alteram regras financeiras, contratos de API, banco de dados, código-fonte ou comportamento dos módulos existentes.

---

## MVP UX-1C — Migração das demais telas para shell visual (2026-04-30)

As telas HTML standalone restantes foram migradas para herdar `base.html`, usando o shell visual desktop/web criado no UX-1A.

Foram migradas as telas Despesas, Cartões, Receitas, Lançamentos, Financiamentos, Contas Bancárias, Patrimônio, Categorias, Veículos, Preferências e Importar Cartão. A migração preservou CSS/JS de módulo, IDs, classes internas, modais, filtros e comportamento funcional.

Despesas foi mantida sem redesenho. Seguro Habitacional (`/financiamentos/seguro`) e Indexadores (`/indexadores`) continuam como pendências diagnósticas fora deste MVP.

---

## MVP UX-2 — Configurações enxuta (2026-04-30)

A tela Configurações deixou de ser hub de módulos operacionais. Os atalhos para Categorias, Despesas Recorrentes, Cartões, Veículos, Financiamentos, Contas Bancárias, Receitas e Patrimônio foram removidos da tela, mantendo os módulos acessíveis pela sidebar.

Configurações ficou reservada a Preferências do Sistema e futuras configurações sistêmicas, sem alteração de rotas, APIs, banco de dados ou regras financeiras.

## MVP UX-3A — Infraestrutura da faixa de ações (2026-04-30)

O shell visual recebeu o bloco opcional `action_bar` e o CSS global passou a conter classes reutilizáveis para futura faixa de ações por módulo.

Esta etapa não aplicou a faixa em telas funcionais, não moveu botões existentes e manteve Despesas, Cartões, Financiamentos e demais módulos sem reorganização visual. A aplicação por tela fica para UX-3B.

## MVP UX-3B-1 — Faixa de ações em Categorias (2026-04-30)

A tela Categorias passou a usar a `action_bar` como primeira aplicação real do padrão. O botão "Nova Categoria" foi movido para a faixa superior e continua abrindo o mesmo modal.

As ações contextuais de editar e excluir permaneceram na listagem. Nenhuma regra financeira, API, banco de dados, JavaScript funcional ou tela sensível foi alterada.

## MVP UX-3B-2 — Faixa de ações em Contas Bancárias (2026-04-30)

A tela Contas Bancárias passou a usar a `action_bar` para a ação primária "Nova Conta", mantendo o mesmo modal e o mesmo fluxo existente.

Filtros, extrato, ajuste manual, editar, inativar e reativar foram preservados nos seus contextos originais. Não houve alteração de regra de saldo, APIs, JavaScript funcional, banco de dados ou regras financeiras.

## MVP UX-3B-3 — Faixa de ações em Receitas (2026-04-30)

A tela Receitas passou a usar a `action_bar` para a ação primária "Nova Fonte", mantendo o mesmo modal de fonte de receita e o mesmo fluxo existente.

Filtros, cards, listagens, consolidação, registro, edição e exclusão permaneceram nos seus contextos originais. Não houve alteração de lógica de receitas previstas/realizadas, APIs, dashboard, JavaScript funcional, banco de dados ou regras financeiras.

## MVP UX-3B-4 — Faixa de ações em Patrimônio (2026-04-30)

A tela Patrimônio passou a usar a `action_bar` para as ações globais "Nova Caixinha" e "Nova Transferência", mantendo os mesmos modais e fluxos existentes.

Abas, caixinhas, transferências, saldos, metas, edição, inativação e remoção permaneceram nos seus contextos originais. Não houve alteração de lógica patrimonial, APIs, JavaScript funcional, banco de dados ou regras financeiras.

## MVP UX-3B-5 — Faixa de ações em telas médias (2026-04-30)

A tela Lançamentos passou a usar a `action_bar` para a ação global "Novo Lançamento", mantendo o mesmo modal e fluxo existente.

Filtros, receitas pendentes, confirmação de recebimento, histórico, edição, exclusão e modais permaneceram nos seus contextos originais. Preferências e Importar Cartão foram avaliadas e preservadas sem `action_bar` neste lote, por dependerem respectivamente de abas e de fluxo wizard por etapas.

## MVP UX-3C-1 — Faixa de ações em Cartões (2026-04-30)

A tela Cartões passou a usar a `action_bar` para a ação global "Novo Cartão", mantendo o mesmo modal de cadastro e o mesmo fluxo existente.

Cards/listagem, edição de cartão, revelação de CVV, categorias internas, limites/orçamentos, faturas, lançamentos e ações contextuais permaneceram nos seus contextos originais. Não houve alteração de lógica de cartão/fatura, APIs, JavaScript funcional, banco de dados ou regras financeiras.

## MVP UX-3C-2 — Faixa de ações em Financiamentos (2026-04-30)

A tela Financiamentos passou a usar a `action_bar` para a ação global "Novo Financiamento", mantendo o mesmo modal de cadastro e o mesmo fluxo existente.

Lista/cards, parcelas, pagamentos, amortizações, demonstrativo anual, evolução de saldo, seguro habitacional, regeneração de parcelas, edição, exclusão, inativação e ações contextuais permaneceram nos seus contextos originais. Não houve alteração de lógica de financiamento, APIs, JavaScript funcional, banco de dados ou regras financeiras.

## MVP UX-3C-3 — Faixa de ações em Veículos (2026-04-30)

A tela Veículos passou a usar a `action_bar` para as ações globais "Novo Veículo" e "Transporte por App", mantendo os mesmos modais de cadastro e fluxos existentes.

Cards/listagem, comparativos, custos, manutenção, financiamento por veículo, simulações, edição, exclusão e ações contextuais permaneceram nos seus contextos originais. Não houve alteração de lógica de veículos, APIs, JavaScript funcional, banco de dados ou regras financeiras.

## MVP UX-3-REVIEW FINAL — Revisão geral das action bars (2026-05-01)

As telas Categorias, Contas Bancárias, Receitas, Patrimônio, Lançamentos, Cartões, Financiamentos e Veículos foram revisadas quanto à consistência da `action_bar`.

A revisão confirmou o padrão visual e corrigiu apenas a duplicidade visual residual dos botões antigos em Veículos. Nenhuma nova tela recebeu faixa de ações, Despesas permaneceu preservada e não houve alteração de regras financeiras, APIs, JavaScript funcional, banco de dados ou fluxos de clique.

## MVP UX-4B — Ícones dinâmicos em JavaScript (2026-05-01)

O UX-4B padronizou ícones funcionais gerados dinamicamente por JavaScript em Contas Bancárias, Receitas, Lançamentos e Cartões.

Emojis e símbolos usados em botões foram substituídos por SVGs inline monocromáticos com `currentColor`, preservando handlers, IDs, classes, modais, APIs e regras financeiras. Despesas, Financiamentos, Patrimônio e Dashboard ficaram fora desta etapa.

## MVP UX-4C-1 — Ícones em Financiamentos e Dashboard (2026-05-01)

O UX-4C-1 padronizou ícones visuais dinâmicos em Financiamentos e Dashboard, cobrindo seguro, indicadores, alertas, datas, loading e notificações.

As substituições usaram SVGs inline monocromáticos com `currentColor` ou texto limpo quando o conteúdo já era suficiente. Não houve alteração de cálculo financeiro, dashboard backend, APIs, templates, modais, Chart.js, banco de dados ou regras financeiras.

## MVP UX-4C-2 — Patrimônio JS com API relativa e ícones dinâmicos (2026-05-01)

O UX-4C-2 removeu a dependência hardcoded de `http://localhost:5000/api/patrimonio` em `patrimonio.js`, substituindo por `/api/patrimonio`.

Também padronizou ícones dinâmicos em caixinhas e transferências com SVGs inline monocromáticos e `currentColor`, sem alterar cálculos de saldo, transferências, metas, modais, APIs, banco de dados ou regras financeiras.

## MVP UX-4-REVIEW FINAL — Revisão geral de ícones (2026-05-01)

O UX-4-REVIEW FINAL revisou o estado final dos ícones e emojis após UX-4A, UX-4B, UX-4C-1 e UX-4C-2.

Foram corrigidos resíduos pontuais em telas comuns e preservadas as exceções planejadas: Despesas, Financiamento Seguro, console/logs/comentários e alerts/confirms internos. Nenhuma regra financeira, backend, API, banco de dados ou fluxo sensível foi alterado.

## MVP UX-5A-INFRA — Action bar full width e estrutura de filtros (2026-05-01)

O UX-5A-INFRA ajustou o shell visual para tratar a `action_bar` como regiao estrutural abaixo da topbar, com melhor aproveitamento da largura util da area principal.

Foram adicionadas classes globais para suporte futuro a filtros a esquerda e acoes a direita, alem de classes opt-in para conteudo mais largo por tela. Nenhum filtro foi movido, nenhum template de modulo foi alterado e Despesas permaneceu preservada.

## MVP DB-3C — Baseline Alembic oficial (2026-05-01)

O DB-3C estabeleceu o Alembic como fonte oficial de evolução de schema do projeto.

O baseline foi gerado contra um banco PostgreSQL local temporário vazio (`controle_financeiro_baseline`) para contornar o cenário em que o autogenerate retornava "No changes in schema detected" no banco dev real (já criado por `db.create_all()`). As migrations anteriores foram arquivadas em `migrations/versions_archived/pre_baseline_20260501_085449/`.

O banco dev real (`controle_financeiro_dev`) foi marcado com `flask db stamp head` — revision `dd1a552aec6a`, sem alteração de dados ou schema. `flask db current` confirma `dd1a552aec6a (head)`. A partir deste ponto, toda evolução de schema deve usar `flask db migrate` + `flask db upgrade`.

## MVP DB-3D — Arquivamento de migrations SQLite legadas (2026-05-01)

O DB-3D organizou scripts históricos fora da estratégia oficial de schema.

Foram arquivados em `migrations/legacy_sqlite/` os scripts custom de `backend/migrations/`, os scripts soltos de `migrations/*.py` que não pertenciam à chain Alembic oficial e o script standalone `backend/add_taxa_adm_column.py`.

Os scripts de `scripts/debug/` foram preservados no local e documentados como diagnósticos manuais/legados, não como caminho oficial de migration. Nenhum banco foi alterado, nenhuma migration foi executada e a fonte oficial permanece `migrations/versions/dd1a552aec6a_baseline_inicial_schema_completo.py` e migrations futuras.

## MVP DEV-SEED-1 — Massa de Demonstração para Homologação Visual (2026-05-01)

O DEV-SEED-1 criou o script `scripts/seed_demo_dev.py` para popular o banco local com dados fictícios identificados pelo prefixo `DEV_DEMO_`.

O seed cria: 8 categorias, 1 conta bancária (R$5.000), 1 fonte de receita com orçamento e receita realizada (R$8.000), 1 cartão com 3 categorias internas e 5 lançamentos (incluindo compra parcelada 3x), 4 itens de despesa (Internet R$120, Diarista R$220, Consulta Médica R$300 e Conta de Luz R$280 — sendo esta última paga).

O script é idempotente, só roda em `DATABASE_URL` local e não apaga dados fora do prefixo `DEV_DEMO_`.

---

## MVP UX-5C - Area util ampliada e Dashboard 2.0 (2026-05-01)

O UX-5C reformulou a organizacao visual do Dashboard para aproveitar melhor a largura util do shell, mantendo os mesmos contratos de dados e os IDs usados por `dashboard.js`.

O Dashboard passou a combinar cards superiores, graficos, fluxo de caixa, leitura do mes, indicadores e alertas em uma distribuicao mais ampla. Lancamentos, Receitas e Despesas receberam apenas largura opt-in no wrapper principal. Despesas nao foi redesenhada e preservou listagem, cards, icones pequenos, modais e regras funcionais.

---

## MVP ICONES-1A — Icones por categoria e meio de pagamento (2026-05-01)

O ICONES-1A criou infraestrutura de icones semanticos para o sistema. Adicionou campo `icone` em `Categoria` (migration `28ba243136e8`), criou catalogo interno de SVGs monocromaticos em `icons.js`, e renderiza icones de categoria em Lancamentos, Despesas, Recorrencias e Categorias. Meios de pagamento (cartao, pix, dinheiro, boleto, debito) recebem icone via mapa estatico no frontend. Receitas exibem icone derivado do tipo da fonte. Nenhuma regra financeira, calculo, pagamento, fatura ou dashboard foi alterado.

---

## MVP UX-6B - Action bar compacta em linha unica (2026-05-01)

O UX-6B compactou o padrao visual das action bars ja aplicadas. Filtros passaram a usar label inline antes do campo, os controles ficaram mais baixos e as acoes globais passaram a ser exibidas como botoes icon-only com `title` e `aria-label`.

A mudanca foi limitada a `layout.css` e templates de action bar. Nenhum JavaScript funcional, backend, banco, regra financeira, cards, listagens, modais ou conteudo abaixo da action bar foi alterado. Em Despesas, a intervencao ficou restrita a action bar.

## MVP UX-6C - Areas de informacao em grade full width (2026-05-01)

O UX-6C padronizou as principais areas de informacao com paineis full width, cabecalhos de secao com icone discreto e suporte global a grades/listas compactas.

Lancamentos permaneceu como referencia visual. Despesas recebeu apenas envelope de secao e largura fluida, preservando cards, dica, pagamentos, modais e listagem funcional. Receitas e Categorias tiveram apenas o HTML renderizado dinamicamente reorganizado para grade compacta, mantendo os mesmos handlers, APIs e regras.

Em complemento, Configuracoes, Preferencias e Importar Cartao tambem passaram a usar action bar e conteudo fluido no padrao do shell. Preferencias manteve as abas existentes na faixa superior e Importar Cartao preservou o assistente de importacao.

---

## MVP RECUP-2 - Restauracao de acessos em Despesas (2026-05-01)

O RECUP-2 restaurou atalhos visuais para funcionalidades que ja existiam, mas ficaram pouco descobriveis apos a reestruturacao de navegacao. A action bar de Despesas passou a expor Nova Despesa, Nova Recorrencia e Consorcio como acoes icon-only, e a navegacao lateral passou a exibir atalhos diretos para Recorrencias e Consorcios.

O modal de Despesas foi reaproveitado sem mudanca de regra: Nova Recorrencia apenas pre-marca a despesa como recorrente, e Consorcio apenas abre os campos de consorcio ja existentes. A dica obsoleta de Despesas foi atualizada, e Configuracoes recebeu um atalho discreto para Recorrencias e Obrigacoes.

---

## MVP RECUP-4 - Tela propria de Recorrencias (2026-05-01)

O RECUP-4 criou a rota `/recorrencias`, com tela propria para cadastros-matriz de recorrencias e consorcios. A sidebar passou a direcionar Recorrencias para a nova tela, e Consorcios deixou de ser item separado por ser tratado como tipo especial de recorrencia.

Foi criado endpoint minimo `/api/recorrencias` para listar, criar, atualizar e inativar regras recorrentes baseadas em `ItemDespesa`. Consorcios continuam usando `/api/consorcios`, sem alterar regra de parcelas, contemplacao, receitas, pagamentos ou a tela Despesas.

---

## MVP UX-6E - Botoes de acao padronizados em grades (2026-05-01)

O UX-6E consolidou um padrao visual unico para acoes por linha em grades, listas compactas e cards de registros. As telas principais passaram a usar botoes pequenos, sempre visiveis, com icones monocromaticos, borda sutil, `title` e `aria-label`, preservando os handlers existentes.

Tambem foi ajustado o alinhamento das grades: cabecalhos centralizados, conteudo das colunas secundarias centralizado e conteudo da primeira coluna alinhado a esquerda. Nenhuma API, backend, banco, model, migration ou regra financeira foi alterada.

---

## MVP SEC-0 - Travar exposicao acidental local (2026-05-01)

O SEC-0 reduziu o risco de exposicao acidental durante desenvolvimento local. O servidor passou a usar `FLASK_HOST`, `FLASK_PORT` e `FLASK_DEBUG`, com padrao seguro em `127.0.0.1:5000` e debug desativado quando a variavel nao e definida.

O CORS deixou de ser aberto por wildcard e passou a aceitar apenas origens locais por padrao (`localhost:5000` e `127.0.0.1:5000`), com `CORS_ORIGINS` para configuracao explicita. O MVP nao implementou login, CSRF, producao, HTTPS ou exposicao externa.

---

## MVP TEST-BASE-1 - Estabilizar infraestrutura de testes (2026-05-01)

O TEST-BASE-1 estabilizou a execucao dos testes sem alterar aplicacao, backend funcional, frontend funcional, banco ou regras financeiras. Os scripts npm passaram a separar smoke, smoke headed, funcionais completos, funcionais `[safe]`, funcionais `[create]` e suite combinada.

Os testes funcionais agora rodam com `--workers=1`, reduzindo risco de OOM/worker crash. Fluxos que criam dados usam guard de ambiente e ficam skipped quando o servidor reutilizado esta em `development`; criacao continua permitida somente quando `/health` retorna `environment=testing`.

Foi criado `pytest.ini` para descoberta segura de testes Python `test_*.py`. Os scripts legados `teste_*.py` ficaram fora da coleta automatica porque executam codigo em tempo de import e podem mutar banco local; sua conversao para pytest seguro fica para MVP proprio.

---

## Auditoria Técnica — Análise Sênior (2026-05-01)

Uma auditoria técnica de 360° foi realizada sobre o estado atual do projeto.

**Pontos fortes confirmados:**
- Arquitetura de backend sólida com separação clara de responsabilidades
- Regras financeiras (SAC/PRICE/SIMPLES, fatura, previsto/executado) corretamente implementadas
- Shell visual desktop completo e padronizado
- Playwright E2E como barreira de regressão funcional
- Alembic consolidado como fonte oficial de evolução de schema

**Débitos técnicos identificados:**
- `lazy='dynamic'` depreciado: ~12 relacionamentos em `models.py`
- `datetime.utcnow` depreciado: ~20 ocorrências
- N+1 queries em `to_dict()` com lazy load
- `Query.get()` legacy API SQLAlchemy 2.0
- Zero autenticação nas 18 rotas de API; `CORS(app)` irrestrito
- `numero_cartao` e `codigo_seguranca` em texto puro no banco

**Ordem de trabalho definida (ver `README_TECNICO.md` para tabela completa):**
SEC-0 ✅ → TEST-BASE-1 ✅ → ICONES-1B → DB-CLEAN-1 → CARD-SEC-1 → FIN-RULES-1 → TEST-FIN-1 → DATA-HYGIENE-1 → PERF-1 → FRONT-ARCH-1 → SEG-1 → DEPLOY-1

---

## Backlog — Próximas fases

Para o roadmap técnico completo com prioridades atualizadas, ver `README_TECNICO.md` — seção "Roadmap Técnico — Pós-Auditoria".

Prioridades imediatas:
- TEST-FIN-1: ampliar cobertura E2E em Despesas, Cartões e Financiamentos
- DB-CLEAN-1: corrigir débitos SQLAlchemy 2.0
- CARD-SEC-1: remover dados sensíveis de cartão em texto puro
- SEG-1: autenticação global (bloqueante para qualquer deploy)
