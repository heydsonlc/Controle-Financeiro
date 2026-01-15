# 📊 AUDITORIA TÉCNICA — DASHBOARD EXISTENTE

**Data da Auditoria:** 2025-12-27
**Objetivo:** Mapear o dashboard atual, identificar duplicações e determinar o que está faltando ou pode ser removido.

---

## 1. RESUMO EXECUTIVO

### ✅ O QUE JÁ EXISTE

Você possui um **Dashboard completo e funcional** implementado em:
- **Backend:** [backend/routes/dashboard.py](backend/routes/dashboard.py) - 6 endpoints REST (506 linhas)
- **Frontend:** [frontend/templates/index.html](frontend/templates/index.html) - Interface HTML completa (184 linhas)
- **JavaScript:** [frontend/static/js/dashboard.js](frontend/static/js/dashboard.js) - Lógica de renderização (512 linhas)
- **Gráficos:** Chart.js integrado com 3 visualizações

### 🎯 CONCLUSÃO PRINCIPAL

**O dashboard ATUAL já agrega dados de múltiplas fontes e está funcional.**
**Foram identificados 3 bugs que devem ser corrigidos.**
**NÃO é necessário criar novos endpoints de agregação.**

---

## 2. INVENTÁRIO COMPLETO DO DASHBOARD ATUAL

### 📡 Backend - Endpoints Existentes

| **Endpoint** | **Linhas** | **O Que Calcula** | **Usado no Frontend** |
|-------------|-----------|-------------------|----------------------|
| `GET /api/dashboard/resumo-mes` | 37-119 | Receitas, despesas, saldo líquido, saldo bancário | ✅ `carregarResumoMes()` (js:39) |
| `GET /api/dashboard/indicadores` | 126-216 | Média histórica, gastos pendentes, faturas, % poupado | ✅ `carregarIndicadores()` (js:82) |
| `GET /api/dashboard/grafico-categorias` | 223-274 | Despesas agrupadas por categoria (gráfico pizza) | ✅ `carregarGraficoCategorias()` (js:177) |
| `GET /api/dashboard/grafico-evolucao` | 277-319 | Despesas últimos 6 meses (gráfico barras) | ✅ `carregarGraficoEvolucao()` (js:239) |
| `GET /api/dashboard/grafico-saldo` | 322-400 | Evolução saldo bancário (gráfico linha) | ✅ `carregarGraficoSaldo()` (js:313) |
| `GET /api/dashboard/alertas` | 407-505 | Contas a vencer, cartões, financiamentos, receitas | ✅ `carregarAlertas()` (js:394) |

**Total:** 6 endpoints ativos

---

### 🖥️ Frontend - Interface Existente

#### Bloco 1: Resumo Financeiro (index.html:24-52)
- ✅ **RECEITAS DO MÊS** - Card clicável → `/receitas`
- ✅ **DESPESAS DO MÊS** - Card clicável → `/despesas`
- ✅ **SALDO LÍQUIDO** - Coloração dinâmica (verde/vermelho)
- ✅ **SALDO NAS CONTAS** - Card clicável → `/contas-bancarias`

#### Bloco 2: Indicadores Inteligentes (index.html:57-62)
- Chips dinâmicos renderizados via JavaScript
- Tipos: despesas acima da média, gastos pendentes, faturas, % poupado

#### Bloco 3: Gráficos (index.html:67-95)
- ✅ Gráfico de Pizza - Distribuição por Categoria
- ✅ Gráfico de Barras - Evolução de Gastos (6 meses)
- ✅ Gráfico de Linha - Evolução do Saldo Bancário

#### Bloco 4: Alertas e Agenda (index.html:100-136)
- ✅ Contas a Vencer (próximos 7 dias)
- ✅ Faturas de Cartão
- ✅ Financiamentos Ativos
- ✅ Receitas Previstas

---

## 3. ANÁLISE DETALHADA — O QUE CADA ENDPOINT FAZ

### 3.1 `/resumo-mes` (dashboard.py:37-119)

#### Lógica de Cálculo:
```python
# RECEITAS = Confirmadas + Previstas (não confirmadas)
orcamentos_realizados = ReceitaRealizada WHERE mes_referencia=mes_atual
receitas_realizadas = SUM(ReceitaRealizada.valor_recebido)
receitas_previstas = SUM(ReceitaOrcamento.valor_esperado) WHERE orcamento_id NOT IN (realizados)
receitas_mes = receitas_realizadas + receitas_previstas

# DESPESAS = Soma de todas as Contas do mês
despesas_mes = SUM(Conta.valor) WHERE mes_referencia=mes_atual

# SALDO LÍQUIDO
saldo_liquido = receitas_mes - despesas_mes

# SALDO BANCÁRIO
saldo_contas = SUM(ContaBancaria.saldo_atual) WHERE status='ATIVO'
```

#### ⚠️ Observação:
- **NÃO usa** `CartaoService` diretamente
- **Assume** que `Conta.valor` das faturas já foi calculado
- **Risco:** Se faturas não forem recalculadas, valores podem divergir

---

### 3.2 `/indicadores` (dashboard.py:126-216)

#### Cálculos:
1. **Média Histórica:** `AVG(Conta.valor)` dos últimos 3 meses
2. **Gastos Pendentes:** `COUNT(Conta)` com vencimento em 7 dias
3. **Faturas Próximas:** `COUNT(ConfigAgregador)` de cartões ativos ⚠️
4. **% Poupado:** `((receitas - despesas) / receitas) * 100`

#### 🔴 BUG IDENTIFICADO:
- **Linha 160-164:** Conta apenas cartões ativos, **não verifica se há fatura real**
- Pode exibir "3 faturas próximas" mesmo que nenhum cartão tenha sido usado

---

### 3.3 `/grafico-categorias` (dashboard.py:223-274)

#### Query SQL:
```sql
SELECT
    Categoria.nome,
    Categoria.cor,
    SUM(Conta.valor) AS total
FROM Conta
JOIN ItemDespesa ON Conta.item_despesa_id = ItemDespesa.id
JOIN Categoria ON ItemDespesa.categoria_id = Categoria.id
WHERE
    MONTH(mes_referencia) = mes_atual
    AND Categoria.id IS NOT NULL
GROUP BY Categoria.id
ORDER BY total DESC
```

#### ✅ Correto:
- Agrupa por categoria analítica
- Exclui despesas sem categoria

---

### 3.4 `/grafico-evolucao` (dashboard.py:277-319)

#### Lógica:
```python
# Últimos 6 meses
for i in range(5, -1, -1):
    mes = mes_atual - i
    total = SUM(Conta.valor) WHERE mes_referencia = mes
    valores.append(total)
```

#### ✅ Correto:
- Série temporal simples e eficiente

---

### 3.5 `/grafico-saldo` (dashboard.py:322-400)

#### Lógica Atual:
```python
saldo_atual = SUM(ContaBancaria.saldo_atual)

# Para cada um dos últimos 6 meses:
for i in range(5, -1, -1):
    receitas_mes = receitas_realizadas + receitas_previstas
    despesas_mes = SUM(Conta.valor)
    diferencial = receitas_mes - despesas_mes

    # PROJETA saldo passado (NÃO É HISTÓRICO REAL)
    saldo_mes = saldo_atual - (diferencial * (i + 1))
```

#### 🔴 BUG CRÍTICO:
- **NÃO usa histórico real de saldo**
- **Simula** saldo passado a partir do saldo atual
- **Fórmula invertida:** Subtrai diferenciais futuros
- **Resultado:** Gráfico **não reflete realidade histórica**

---

### 3.6 `/alertas` (dashboard.py:407-505)

#### Consultas:
1. **Contas a Vencer:** Pendentes com vencimento em 7 dias (LIMIT 10)
2. **Cartões:** Todos cartões ativos (LIMIT 5) ⚠️
3. **Financiamentos:** Ativos (LIMIT 5)
4. **Receitas:** Orçamento do mês (LIMIT 10)

#### 🔴 BUGS IDENTIFICADOS:

**Bug #1 - Cartões (linhas 429-467):**
- Lista todos cartões ativos, **não verifica faturas reais**

**Bug #2 - Financiamentos (linhas 474-477):**
```python
'valor_parcela': decimal_to_float(fin.valor_parcela_inicial) if hasattr(fin, 'valor_parcela_inicial') ...
'parcela_atual': fin.parcelas_pagas if hasattr(fin, 'parcelas_pagas') else 0
```
- Tenta acessar `valor_parcela_inicial` e `parcelas_pagas`
- **Esses campos NÃO EXISTEM** no modelo `Financiamento`
- Sempre retorna `0` → **Informação incorreta**

---

## 4. COMPARAÇÃO COM OUTROS ENDPOINTS DO SISTEMA

### 4.1 Duplicação: Cálculo de Despesas Mensais

| **Origem** | **Método** | **Observação** |
|-----------|-----------|----------------|
| `GET /api/dashboard/resumo-mes` | `SUM(Conta.valor)` WHERE `mes_referencia` | Dashboard principal |
| `GET /api/despesas?competencia=X` | Função `calcular_totais_mes()` | Tela de despesas |
| `GET /api/cartoes/<id>/resumo` | `CartaoService.obter_resumo_mensal()` | Recalcula via `LancamentoAgregado` |

#### ⚠️ Risco de Divergência:
- **Dashboard** e **Despesas** usam `Conta.valor` diretamente
- **Cartões** recalcula via `LancamentoAgregado`
- Se faturas não forem recalculadas (via `recalcular_fatura()`), valores podem divergir

---

### 4.2 Duplicação: Cálculo de Receitas Mensais

| **Origem** | **Método** |
|-----------|-----------|
| `GET /api/dashboard/resumo-mes` (linhas 56-82) | Lógica condicional inline |
| `GET /api/receitas/resumo-mensal?ano=X` | `ReceitaService.get_resumo_receitas_por_mes()` |

#### ⚠️ Possível Duplicação:
- Mesma lógica implementada em 2 lugares diferentes

---

## 5. PROBLEMAS IDENTIFICADOS

### 🔴 CRÍTICO

#### Problema #1: Gráfico de Saldo Bancário - Dados Simulados
**Arquivo:** `dashboard.py:322-400`

**Descrição:**
- NÃO usa histórico real de saldo
- Projeta saldo passado a partir do saldo atual
- Fórmula: `saldo_mes = saldo_atual - (diferencial * (i + 1))`

**Impacto:**
- Gráfico **NÃO reflete realidade histórica**
- Movimentações atípicas (transferências, receitas extras) não aparecem

**Soluções Possíveis:**
1. **Criar snapshot mensal de saldo** (alto esforço)
2. **Calcular retroativo via `MovimentoFinanceiro`** (médio esforço)
3. **Remover gráfico** e explicar ausência de histórico (baixo esforço)
4. **Manter como "projeção"** e avisar usuário (zero esforço)

---

### 🟠 MÉDIO

#### Problema #2: Alertas de Cartão - Não Verifica Faturas Reais
**Arquivo:** `dashboard.py:429-467`

**Descrição:**
- Lista todos cartões ativos
- **NÃO verifica** se há fatura real para o mês

**Impacto:**
- Pode exibir "Faturas próximas: 3 cartões" mesmo sem uso

**Solução:**
```python
# Em vez de:
cartoes = ConfigAgregador WHERE ItemDespesa.ativo=True

# Usar:
faturas = Conta WHERE is_fatura_cartao=True AND status_pagamento='Pendente'
```

---

#### Problema #3: Alertas de Financiamento - Campos Inexistentes
**Arquivo:** `dashboard.py:474-477`

**Descrição:**
```python
'valor_parcela': decimal_to_float(fin.valor_parcela_inicial) ...
'parcela_atual': fin.parcelas_pagas ...
```
- Campos **NÃO EXISTEM** no modelo `Financiamento`
- Sempre retorna `0`

**Solução:**
```python
# Buscar parcela do mês via FinanciamentoParcela
parcela_mes = FinanciamentoParcela WHERE financiamento_id=fin.id AND mes=mes_atual
'valor_parcela': parcela_mes.valor_previsto_total
'parcela_atual': parcela_mes.numero_parcela
```

---

### 🟡 BAIXO

#### Problema #4: Indicador "Faturas Próximas" - Impreciso
**Arquivo:** `dashboard.py:160-164`

**Descrição:**
- Mesmo problema do #2
- Conta cartões ativos, não faturas reais

**Solução:**
- Mesma do Problema #2

---

## 6. RECOMENDAÇÕES

### ✅ O QUE MANTER

1. ✅ Estrutura geral do dashboard (4 blocos bem organizados)
2. ✅ Uso de Chart.js (leve e eficiente)
3. ✅ Carregamento paralelo (`Promise.all()`)
4. ✅ Endpoints separados (facilita manutenção)

---

### 🔧 O QUE CORRIGIR

| **Prioridade** | **Problema** | **Esforço** | **Impacto** |
|----------------|-------------|-------------|-------------|
| 🔴 ALTA | Gráfico de saldo (dados simulados) | Médio/Alto | Alto |
| 🟠 MÉDIA | Alertas de financiamento (campos inexistentes) | Baixo | Médio |
| 🟠 MÉDIA | Alertas de cartão (não verifica faturas) | Baixo | Médio |
| 🟡 BAIXA | Indicador "faturas próximas" (impreciso) | Baixo | Baixo |

---

### ❌ O QUE **NÃO** CRIAR

1. ❌ Novos endpoints que dupliquem `/api/despesas?competencia=X`
2. ❌ Novos endpoints que dupliquem `/api/cartoes/<id>/resumo`
3. ❌ Novas agregações mensais - já existem 6 endpoints funcionais
4. ❌ Novos cálculos de totais - reutilizar existentes

---

## 7. CONCLUSÃO FINAL

### 📊 Estado Atual

**O dashboard EXISTE, FUNCIONA, mas tem 3 bugs:**

1. **Gráfico de saldo** - Projeta passado em vez de usar histórico real
2. **Alertas de financiamento** - Usa campos inexistentes (sempre `0`)
3. **Alertas de cartão** - Não verifica faturas reais (impreciso)

---

### ✅ Próximos Passos

**NÃO criar novos endpoints.**
**Corrigir os 3 bugs identificados.**

#### Ordem Sugerida:
1. **Corrigir alertas de financiamento** (baixo esforço, médio impacto)
2. **Corrigir alertas de cartão** (baixo esforço, médio impacto)
3. **Decidir sobre gráfico de saldo:**
   - Opção A: Criar histórico mensal (alto esforço)
   - Opção B: Remover gráfico (baixo esforço)
   - Opção C: Manter como "projeção" + aviso (zero esforço)

---

**FIM DA AUDITORIA**

**Arquivos Analisados:**
- ✅ [backend/routes/dashboard.py](backend/routes/dashboard.py) - 506 linhas
- ✅ [frontend/templates/index.html](frontend/templates/index.html) - 184 linhas
- ✅ [frontend/static/js/dashboard.js](frontend/static/js/dashboard.js) - 512 linhas
- ✅ [backend/models.py](backend/models.py) - Validação de campos
