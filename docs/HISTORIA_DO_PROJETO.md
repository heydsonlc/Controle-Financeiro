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

## Backlog — Próximas fases

Ver [plano de MVPs](./../C:/Users/heydson.cardoso/.claude/plans/sleepy-floating-candy.md) para o cronograma completo (MVP 1 ao 6).

Itens pendentes de maior relevância:
- Fechar módulo Contas Bancárias (MVP 1)
- Remover SENHA_MESTRE hardcoded, ativar scheduler (MVP 2)
- Completar Dashboard com saldo de contas e projeção (MVP 3)
- Autenticação simples via `.env` (MVP 4)
- Exportação CSV e backup do banco (MVP 5)
