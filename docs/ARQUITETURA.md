# Arquitetura do Sistema — Controle Financeiro

Referência técnica dos módulos, entidades e decisões de design.

---

## Estrutura Geral

```
backend/
├── app.py              # Factory Flask (create_app)
├── config.py           # Configuração por ambiente (dev/prod/test)
├── models.py           # Todos os modelos SQLAlchemy (~31 tabelas)
├── init_database.py    # Inicialização e migrations custom
├── scheduler.py        # Jobs automáticos (geração mensal de contas)
├── routes/             # 17 blueprints — um por módulo
├── services/           # 16 serviços — lógica de negócio
├── migrations/         # Flask-Migrate (Alembic)
└── utils/              # Utilitários

frontend/
├── templates/          # 15 templates Jinja2
└── static/
    ├── js/             # 15+ arquivos JS (1 por página)
    └── css/            # 13 arquivos CSS (1 por página)

data/
└── gastos.db           # SQLite (desenvolvimento)
```

**Tecnologias**: Flask 3.0, SQLAlchemy 2.0, SQLite (dev) / PostgreSQL (prod), Vanilla JS, Chart.js.

---

## Módulo 1: Orçamento (Receitas e Despesas)

### Entidades principais

| Entidade | Papel |
|----------|-------|
| `Categoria` | Agrupador de despesas com cor |
| `ItemDespesa` | Template de gasto — tipo Simples ou Agregador (cartão) |
| `ConfigAgregador` | Configuração de cartão (dia fechamento/vencimento) |
| `Conta` | Fonte única de verdade para todas as despesas a pagar |
| `ItemAgregado` | Categoria dentro de um cartão |
| `OrcamentoAgregado` | Teto mensal por categoria de cartão |
| `LancamentoAgregado` | Gasto real no cartão (executado) |
| `GrupoAgregador` | Consolidação entre múltiplos cartões |
| `ItemReceita` | Fonte de receita (salário, aluguel, etc.) |
| `ReceitaOrcamento` | Previsão mensal de receita |
| `ReceitaRealizada` | Receita efetivamente recebida |

### Regra soberana de fatura
- Fatura paga → usa `total_executado` (soma de `LancamentoAgregado`)
- Fatura pendente → usa `total_previsto` (soma de `OrcamentoAgregado`)

### Fluxo de cartão de crédito
```
ItemDespesa (recorrente, meio_pagamento='cartao')
  → gerar_lancamentos_cartao_recorrente()
  → LancamentoAgregado (is_recorrente=True)
  → CartaoService.get_or_create_fatura()
  → Conta (is_fatura_cartao=True, status: ABERTA/FECHADA/PAGA)
```

---

## Módulo 2: Contas Bancárias

### Princípios fundamentais (invioláveis)

1. **Saldo nunca é editado diretamente** — `saldo_atual` é sempre derivado
2. **Tudo que altera saldo gera `MovimentoFinanceiro`** — sem exceções
3. **Ajuste manual é um lançamento explícito** — aparece no extrato, é editável
4. **Extrato é a verdade** — o extrato explica o saldo, não o contrário

### Entidades

| Entidade | Papel |
|----------|-------|
| `ContaBancaria` | Onde o dinheiro está (`saldo_inicial` + `saldo_atual` derivado) |
| `MovimentoFinanceiro` | Qualquer alteração de saldo |

**Tipos de movimento**: `CREDITO`, `DEBITO`, `AJUSTE`
**Origens**: `MANUAL`, `RECEITA`, `DESPESA`, `TRANSFERENCIA`

### Função central: `recalcular_saldo_conta(conta_id)`
Chamada após criar, editar ou excluir qualquer movimento.
```
saldo_atual = saldo_inicial + sum(créditos) - sum(débitos)
```

### Integrações
- Receita realizada → crédito automático
- Despesa paga → débito automático
- Fatura paga → débito único
- Transferência → 2 movimentos atômicos

---

## Módulo 3: Financiamentos

### Entidades

| Entidade | Papel |
|----------|-------|
| `Financiamento` | Contrato (valor, prazo, taxa, indexador) |
| `FinanciamentoParcela` | Parcelas geradas (SAC, PRICE ou SIMPLES) |
| `FinanciamentoAmortizacaoExtra` | Amortizações extraordinárias |
| `FinanciamentoSeguroVigencia` | Vigências de seguro habitacional |

### Cálculo
Serviço `financiamento_service.py` (~73KB) implementa SAC, PRICE e SIMPLES com suporte a correção por indexadores (TR, IPCA etc.) e amortização extraordinária com recalculo de parcelas.

---

## Módulo 4: Indexadores Econômicos

Tabela `indexador_mensal` com histórico de índices (TR, IPCA, IGP-M, CDI, SELIC).

- 419 registros históricos de TR (1991–2025)
- Interface: `/indexadores`, API: `/api/indexadores`
- Integrado ao cálculo de parcelas de financiamento

---

## Módulo 5: Veículos

### Entidades

| Entidade | Papel |
|----------|-------|
| `Veiculo` | Registro com tipo, combustível, autonomia |
| `VeiculoRegraManutencaoKm` | Regras de manutenção por intervalo de km |
| `VeiculoCicloManutencao` | Ciclo auditável de manutenção |
| `VeiculoFinanciamento` | Financiamento projetivo do veículo |
| `CaminhoMobilidade` | Caminhos para cálculo de custo de transporte por app |

O módulo projeta custo total de propriedade mas **não cria despesas automáticas** — apenas exibe projeção.

---

## Módulo 6: Patrimônio

Caixinhas de alocação de patrimônio (corrente, poupança, investimento, reserva). Transferências entre caixinhas são rastreadas. Separado de `ContaBancaria` — patrimônio é visão de alocação, contas bancárias é visão de saldo operacional.

---

## Importação de Fatura CSV

Feature aditiva implementada na Fase 6.2. Campos em `LancamentoAgregado`:
- `descricao_original` — texto bruto do CSV (imutável)
- `descricao_original_normalizada` — sem informação de parcela
- `descricao_exibida` — editável pelo usuário
- `is_importado` — flag de origem
- `origem_importacao` — "csv", "manual"

Idempotência garantida via `compra_id` (UUID v4) + `numero_parcela`.

---

## Scheduler de Jobs

`backend/scheduler.py` implementa geração automática mensal de contas recorrentes. Atualmente **comentado** em `backend/app.py:264` — ativação pendente no MVP 2.

---

## Banco de Dados

- **Desenvolvimento**: `data/gastos.db` (SQLite)
- **Produção**: PostgreSQL via variável `DATABASE_URL`
- **Migrations**: Flask-Migrate (Alembic) em `migrations/`
- **Compat layer**: `backend/services/sqlite_schema_compat.py` para compatibilidade com schemas SQLite existentes

**Nota**: `backend/migrations/` (migrations custom) e `migrations/` (Alembic oficial) coexistem — unificação pendente no MVP 2.
