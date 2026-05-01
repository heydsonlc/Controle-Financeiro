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

---

## Backlog — Próximas fases

Ver [plano de MVPs](./../C:/Users/heydson.cardoso/.claude/plans/sleepy-floating-candy.md) para o cronograma completo (MVP 1 ao 6).

Itens pendentes de maior relevância:
- Fechar módulo Contas Bancárias (MVP 1)
- Remover SENHA_MESTRE hardcoded, ativar scheduler (MVP 2)
- Completar Dashboard com saldo de contas e projeção (MVP 3)
- Autenticação simples via `.env` (MVP 4)
- Exportação CSV e backup do banco (MVP 5)
