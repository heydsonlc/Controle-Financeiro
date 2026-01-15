# 📅 FASE 6.1 — Agenda Financeira + Insights Temporais
## Dashboard: Linha do Tempo Financeira

---

## 1️⃣ VALIDAÇÃO PRÉVIA (REALIZADA)

### Análise do código existente:

✅ Verificado que **NÃO existia**:
- Timeline unificada por `data_vencimento`
- Leitura temporal tipo "até hoje"
- Ordenação cronológica visual consolidada

✅ Endpoint `/api/dashboard/alertas` **JÁ RETORNA** todos os dados:
- `contas_vencer` (com `data_vencimento`)
- `faturas_cartao` (com `data_vencimento` + cálculo dinâmico)
- `financiamentos` (com parcela do mês)
- `receitas_previstas`

### Confirmação explícita:

**Faz sentido implementar?** ✅ SIM
- Não duplica funcionalidade
- Não conflita com regras existentes
- Apenas reorganiza visualmente dados já existentes

**Ela não conflita?** ✅ SIM - ZERO conflito
- Não altera cálculos financeiros
- Não cria regras de negócio
- Endpoint `/alertas` já calcula corretamente (inclusive faturas com regra soberana)

---

## 2️⃣ OBJETIVO DA FEATURE

Implementar no Dashboard um novo bloco chamado:

### 📅 Agenda Financeira do Mês

Composto por:
1. **Timeline Cronológica:** Lista ordenada por `data_vencimento`
2. **Insights Temporais:** 3 frases descritivas sobre o comportamento temporal

---

## 3️⃣ REGRAS FUNCIONAIS (IMUTÁVEIS)

### 3.1 Timeline Cronológica

**Fonte de dados:** Endpoint `/api/dashboard/alertas` (existente)

**Itens incluídos:**
- Contas comuns (pendentes)
- Faturas de cartão (pendentes)
- Parcelas de financiamento (mês atual)

**Ordenação:** Ascendente por `data_vencimento`

**Cada item exibe:**
- Data (DD/MM/YYYY)
- Tipo (Conta | Cartão | Financiamento)
- Descrição
- Categoria (se disponível)
- Valor (formatado em R$)

**Visual:**
- Destaque especial para **HOJE** (cor azul #007aff)
- Itens passados com opacidade reduzida (0.5)
- Itens futuros com opacidade normal (0.9)

### 3.2 Insights Temporais

**Geração automática de até 3 frases** com base na timeline:

#### Insight 1: Percentual vencido
```
"Até hoje, X% das despesas do mês já venceram."
```

#### Insight 2: Concentração temporal
```
"O maior volume de vencimentos ocorre na [primeira|segunda|terceira] dezena do mês."
```

#### Insight 3: Cartões
```
"As despesas de cartão concentram-se após o dia 20."
```

**Regras dos insights:**
- Linguagem descritiva (NUNCA prescritiva)
- Sem emojis
- Sem cores chamativas
- Sem verbos imperativos ("deveria", "cuidado", etc.)
- Frases independentes e autossuficientes

---

## 4️⃣ RESTRIÇÕES TÉCNICAS

### 🚫 O que NÃO FOI FEITO (por design)

- NÃO criou novos endpoints
- NÃO criou novas regras de negócio
- NÃO recalculou valores financeiros
- NÃO alterou status de pagamento
- NÃO permitiu ações ou edições

### ✅ O que FOI FEITO

- Reutilizado endpoint `/alertas` existente
- Consolidação client-side de dados já disponíveis
- Visualização puramente informativa (somente leitura)

---

## 5️⃣ IMPLEMENTAÇÃO TÉCNICA

### Frontend - HTML

**Arquivo:** `frontend/templates/index.html`

**Localização:** Após "Leitura do Mês", antes de "Alertas e Agenda Financeira"

**Bloco adicionado (linhas 107-122):**
```html
<section class="agenda-financeira">
    <h2>📅 Agenda Financeira do Mês</h2>

    <!-- Insights Temporais -->
    <div id="insights-temporais">
        <p class="loading">Carregando insights...</p>
    </div>

    <!-- Timeline Cronológica -->
    <div id="timeline-agenda">
        <p class="loading">Carregando agenda...</p>
    </div>
</section>
```

### Frontend - JavaScript

**Arquivo:** `frontend/static/js/dashboard.js`

**Funções adicionadas (linhas 594-791):**

1. **`carregarAgendaFinanceira()`** (linha 598)
   - Busca dados de `/api/dashboard/alertas`
   - Consolida timeline
   - Renderiza visual
   - Gera insights

2. **`consolidarTimeline(alertas)`** (linha 624)
   - Unifica contas, faturas e financiamentos
   - Converte datas para objetos Date
   - Ordena cronologicamente

3. **`parseDataBR(dataStr)`** (linha 684)
   - Converte DD/MM/YYYY → Date

4. **`renderizarTimeline(itens)`** (linha 690)
   - Gera HTML da timeline
   - Aplica destaque para HOJE
   - Reduz opacidade de itens passados

5. **`gerarInsightsTemporais(itens)`** (linha 744)
   - Calcula percentual vencido
   - Identifica concentração temporal
   - Analisa comportamento de cartões
   - Gera até 3 frases descritivas

**Integração no carregamento (linha 29):**
```javascript
await Promise.all([
    // ... outros carregamentos
    carregarAgendaFinanceira()
]);
```

---

## 6️⃣ UX / VISUAL

**Estilo minimalista**, integrado ao dashboard atual:

- **Background:** `rgba(255,255,255,0.05)` (sutil)
- **Insights:** Box com `rgba(255,255,255,0.08)` (destaque leve)
- **Itens de hoje:** Border azul `#007aff`
- **Itens passados:** Opacidade 0.5
- **Itens futuros:** Opacidade 0.9
- **Separação:** Gap de 12px entre itens

**Sem:**
- Cards grandes
- Cores chamativas
- Emojis excessivos
- Ações/botões

---

## 7️⃣ CRITÉRIOS DE ACEITE

✅ Timeline ordenada cronologicamente
✅ Destaque visual para "HOJE"
✅ Insights coerentes com os dados
✅ Zero duplicação de lógica
✅ Zero impacto em cálculos existentes
✅ Valores idênticos aos de /alertas e /despesas

---

## 8️⃣ ARQUIVOS ALTERADOS E CRIADOS

### Arquivos alterados:

- **frontend/templates/index.html** (linhas 107-122)
  - Adicionado bloco HTML da Agenda Financeira

- **frontend/static/js/dashboard.js** (linhas 29, 594-791)
  - Adicionado carregamento da agenda
  - Implementadas 5 funções auxiliares
  - Integrado ao fluxo de carregamento paralelo

### Arquivos criados:

- **docs/AI_TASK_AGENDA_FINANCEIRA_E_INSIGHTS.md** (este documento)
  - Documentação completa da feature

### Arquivos apenas lidos (análise):

- `backend/routes/dashboard.py` (linhas 520-619)
  - Endpoint `/alertas` analisado
  - Confirmado cálculo dinâmico de faturas

- `frontend/static/js/dashboard.js` (linhas 394-495)
  - Funções de alertas analisadas
  - Estrutura de dados confirmada

---

## 9️⃣ OBSERVAÇÕES

### Lógica antiga ficou obsoleta?
**NÃO** - Nenhuma lógica foi removida ou substituída.
A feature é **aditiva**, não **modificadora**.

### Alguma tela perdeu função?
**NÃO** - Todas as telas continuam funcionando normalmente.
O bloco de "Alertas" permanece inalterado.

### Decisão arquitetural assumida?
**SIM** - **Timeline como visão cronológica unificada**

Consolidar diferentes tipos de despesas (contas, faturas, financiamentos) em uma única linha do tempo ordenada por `data_vencimento` cria:

- **Consciência temporal:** Usuário vê o "ritmo" do mês
- **Leitura educativa:** Insights descritivos sem alarmes
- **Base para evolução:** Fundação para comparações mensais futuras (Fase 7)

---

## 🔟 IMPACTO

- **Impacto funcional:** MÉDIO
  - Nova visualização, não altera funcionalidades existentes

- **Impacto em dados existentes:** NENHUM
  - Apenas leitura, sem modificações

- **Impacto em testes manuais:** SIM
  - Requer validação visual da timeline e insights

- **Impacto no dashboard:** BAIXO
  - Adicionado novo bloco, não modificou blocos existentes

- **Impacto em cálculos:** NENHUM
  - Usa valores já calculados pelo endpoint `/alertas`

---

## 1️⃣1️⃣ PRÓXIMOS PASSOS NATURAIS (FASE 7)

Esta implementação cria a base perfeita para:

### "Como este mês se compara com meses anteriores?"

Possibilidades futuras (NÃO implementadas agora):

- Comparação de ritmo de vencimentos entre meses
- Identificação de padrões temporais recorrentes
- Alertas inteligentes baseados em histórico
- Mentoria financeira baseada em comportamento

👉 **Mas por agora: Agenda + Insights é o passo perfeito.**

---

**Data de implementação:** 2025-12-27
**Versão:** 1.0
**Status:** ✅ CONCLUÍDO
**Fase:** 6.1 (Agenda Financeira + Insights Temporais)
