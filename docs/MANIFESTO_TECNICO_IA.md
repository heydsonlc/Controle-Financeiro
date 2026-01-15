# 🤖 MANIFESTO TÉCNICO PARA IA — REGRA-MESTRE DE IMPLEMENTAÇÃO

## Precedência Hierárquica

Este documento tem **prioridade absoluta** sobre qualquer script ou solicitação pontual.

**Ordem de precedência**:
1. **MANIFESTO_TECNICO_IA.md** (este documento) — filosofia e regras soberanas
2. **AI_IMPLEMENTATION_STANDARD.md** — processo obrigatório de implementação
3. Scripts específicos do usuário — requisições pontuais

---

## PARTE 1: FILOSOFIA TÉCNICA SOBERANA

### 1.1 Consciência, não Controle

**Regra absoluta**: O sistema NUNCA diz ao usuário o que fazer.

#### O que você PODE implementar:
- ✅ Mostrar dados reais
- ✅ Apresentar fatos objetivos
- ✅ Organizar informações temporalmente
- ✅ Calcular totais, médias, percentuais
- ✅ Exibir comparações (previsto vs executado)

#### O que você NUNCA PODE implementar:
- ❌ Sugestões prescritivas ("Você deveria...")
- ❌ Julgamentos de comportamento ("Gasto excessivo em...")
- ❌ Conselhos financeiros ("Economize cortando...")
- ❌ Alertas moralistas ("Atenção: orçamento estourado!")
- ❌ Emojis de aprovação/reprovação (✅❌ em contexto de julgamento)
- ❌ Cores que indiquem "certo/errado" (vermelho = erro, verde = sucesso)

**Diferença crítica**:
- ✅ "Você gastou R$ 300 além do previsto" — **DESCRITIVO** (permitido)
- ❌ "Você gastou demais" — **PRESCRITIVO** (bloqueado)

---

### 1.2 Previsto vs Executado (ambos legítimos)

**Regra absoluta**: Valores previstos e executados têm mesma importância.

#### O que isso significa tecnicamente:

- **Previsto** não é "meta" — é **planejamento**
- **Executado** não é "erro" quando diferente — é **realidade**
- **Diferença** não é "falha" — é **informação**

#### Implementação:
```python
# ✅ CORRETO
total_previsto = calcular_orcamento()
total_executado = calcular_lancamentos()
diferenca = total_executado - total_previsto

return {
    'previsto': total_previsto,
    'executado': total_executado,
    'diferenca': diferenca  # SEM julgar se é bom ou ruim
}

# ❌ ERRADO
if total_executado > total_previsto:
    status = "ACIMA DO ORÇAMENTO"  # Implica erro
    cor = "vermelho"
```

**Cores permitidas**:
- Azul para previsto
- Roxo/lilás para executado
- Cinza para neutro
- **Vermelho/verde APENAS para status objetivo** (Pago/Pendente), nunca para julgamento

---

### 1.3 Mês como Eixo Soberano

**Regra absoluta**: Competência mensal (MM/AAAA) é a dimensão organizadora primária.

#### O que isso significa tecnicamente:

- Toda consulta de dados deve **começar** filtrando por `mes_competencia` ou `mes_referencia`
- Vencimentos, prazos, datas específicas são **refinadores secundários**
- Nunca cruzar dados de competências diferentes sem explicitar

#### Implementação:
```python
# ✅ CORRETO — Competência primeiro, vencimento depois
despesas = Despesa.query.filter(
    extract('year', Despesa.mes_competencia) == ano,
    extract('month', Despesa.mes_competencia) == mes
)

if data_vencimento_ate:
    despesas = despesas.filter(Despesa.data_vencimento <= data_vencimento_ate)

# ❌ ERRADO — Filtrar por vencimento sem competência
despesas = Despesa.query.filter(
    Despesa.data_vencimento.between(data_inicio, data_fim)
)
```

---

### 1.4 Backend Soberano

**Regra absoluta**: Lógica de negócio acontece APENAS no backend.

#### O que isso significa tecnicamente:

- Frontend **NUNCA** calcula totais financeiros
- Frontend **NUNCA** aplica regras de negócio
- Frontend **APENAS** exibe dados já processados

#### Implementação:
```javascript
// ✅ CORRETO — Frontend apenas exibe
async function carregarDespesas() {
    const response = await fetch('/api/despesas');
    const data = await response.json();

    exibirTotais(data.total_previsto, data.total_executado);
}

// ❌ ERRADO — Frontend calcula
async function carregarDespesas() {
    const response = await fetch('/api/despesas');
    const despesas = await response.json();

    let total = 0;
    despesas.forEach(d => {
        if (d.status === 'Pago') {
            total += d.valor_executado;  // LÓGICA NO FRONTEND!
        } else {
            total += d.valor_previsto;
        }
    });
}
```

**Exceção permitida**: Filtros client-side para **organização visual** (não cálculo).

---

### 1.5 Cálculo Dinâmico (não campos estáticos)

**Regra absoluta**: Valores financeiros calculados em tempo real, não armazenados.

#### Fonte de verdade:
- **Executado**: `LancamentoAgregado` (soma de valores efetivamente gastos)
- **Previsto**: `OrcamentoAgregado` (soma de orçamentos planejados) + executado

#### Implementação:
```python
# ✅ CORRETO — Calcular dinamicamente
def calcular_fatura(cartao_id, competencia):
    total_executado = db.session.query(
        func.sum(LancamentoAgregado.valor)
    ).filter(
        LancamentoAgregado.cartao_id == cartao_id,
        LancamentoAgregado.mes_fatura == competencia
    ).scalar() or 0

    # ... calcular previsto ...

    return total_previsto, total_executado

# ❌ ERRADO — Confiar em campo pré-calculado
def calcular_fatura(fatura_id):
    fatura = Conta.query.get(fatura_id)
    return fatura.valor_planejado, fatura.valor_executado  # Pode estar desatualizado
```

---

### 1.6 Regra Soberana de Fatura

**Regra absoluta**: Para faturas de cartão, aplicar hierarquia de valores.

#### Lógica:
- Se `status_pagamento == 'Pago'` → usar `total_executado`
- Se `status_pagamento == 'Pendente'` → usar `total_previsto`

#### Implementação:
```python
# ✅ CORRETO
if fatura.status_pagamento == 'Pago':
    valor_fatura = total_executado
else:
    valor_fatura = total_previsto

# ❌ ERRADO — Usar campo direto
valor_fatura = fatura.valor  # Ignora regra de status
```

**Esta regra é INVIOLÁVEL** — não aceitar "exceções" ou "casos especiais".

---

## PARTE 2: PROCESSO OBRIGATÓRIO DE IMPLEMENTAÇÃO

Antes de implementar QUALQUER funcionalidade, siga este protocolo:

### 2.1 Leitura Obrigatória

1. **Ler código existente relacionado**
   - Buscar por funcionalidades similares
   - Verificar se já existe implementação parcial
   - Identificar padrões do codebase

2. **Verificar se já existe**
   - A funcionalidade pode já estar implementada
   - Pode haver duplicação não intencional
   - Pode haver conflito com código existente

3. **Identificar conflitos**
   - Com regras de negócio existentes
   - Com cálculos de faturas/financiamentos
   - Com comportamento de outras telas

### 2.2 Confirmação Explícita (OBRIGATÓRIA)

Antes de codar, responder:

```
✅ Faz sentido implementar? (SIM / NÃO / PARCIAL)

Justificativa:
- [motivo técnico]
- [alinhamento com filosofia]
- [impacto em código existente]
```

**Não prosseguir sem aprovação explícita do usuário.**

### 2.3 Implementação

Seguir:
- Padrões existentes no código
- Nomenclatura consistente
- Comentários explicativos em pontos críticos
- Testes manuais (scripts de teste quando apropriado)

### 2.4 Relatório Final (OBRIGATÓRIO)

Após implementação, gerar:

```markdown
## Arquivos Alterados
- `caminho/arquivo.py` (linhas X-Y)
- `caminho/template.html` (linhas A-B)

## Observações
- [decisões técnicas tomadas]
- [lógica antiga que ficou obsoleta]
- [pontos de atenção]

## Impacto
- Funcional: [descrição]
- Em dados existentes: [descrição]
- Em testes: [descrição]
```

---

## PARTE 3: REGRAS DE DESIGN E UX

### 3.1 Minimalismo Apple-inspired

**Princípio**: Cada pixel tem propósito.

#### Diretrizes:
- Espaçamento generoso (padding, margin)
- Tipografia clara (16px+ para corpo)
- Cores sutis (rgba baixo para backgrounds)
- Animações suaves (0.2s ease)
- Bordas arredondadas (8px-12px)

#### O que evitar:
- ❌ Excesso de cores
- ❌ Bordas desnecessárias
- ❌ Sombras exageradas
- ❌ Ícones decorativos (apenas funcionais)
- ❌ Animações chamativas

### 3.2 Emojis (uso restrito)

**Regra**: Usar APENAS quando:
- Funcional (identificar tipo de item)
- Neutro (sem julgamento)
- Consistente (padrão em todo sistema)

#### Permitido:
- ✅ 📅 para datas/agenda
- ✅ 💳 para cartões
- ✅ 🏦 para financiamentos
- ✅ 📊 para dashboard

#### Bloqueado:
- ❌ ✅❌ para aprovação/erro
- ❌ 🎉 para conquistas
- ❌ ⚠️ para alertas moralistas
- ❌ 😊😢 para sentimentos

### 3.3 Linguagem (tom descritivo)

**Regra**: Usar linguagem objetiva, sem julgamento.

#### Exemplos:

| ❌ Errado | ✅ Correto |
|-----------|-----------|
| "Gastos excessivos" | "Total executado: R$ 1.200" |
| "Você está no vermelho" | "Diferença: -R$ 300" |
| "Meta atingida!" | "Executado = Previsto" |
| "Atenção: orçamento estourado" | "Executado R$ 200 acima do previsto" |

---

## PARTE 4: RESTRIÇÕES TÉCNICAS

### 4.1 Não adicionar bibliotecas sem necessidade

Antes de adicionar nova dependência:
1. Verificar se já existe solução nativa
2. Avaliar impacto no tamanho do bundle
3. Confirmar que é realmente necessário

**Preferir**: Vanilla JS, SQL puro, Python stdlib

### 4.2 Não criar endpoints desnecessários

Antes de criar novo endpoint:
1. Verificar se dados existem em endpoint atual
2. Avaliar se frontend pode reorganizar dados existentes
3. Confirmar que lógica requer backend

**Preferir**: Reusar endpoints existentes, reorganizar no frontend (visualmente, não lógica)

### 4.3 Não alterar esquema de banco sem motivo

Antes de alterar tabelas:
1. Confirmar que não há campo existente
2. Avaliar impacto em dados históricos
3. Planejar migração

**Preferir**: Usar campos existentes, calcular dinamicamente

---

## PARTE 5: CASOS ESPECIAIS E EXCEÇÕES

### 5.1 Quando aceitar "exceção" de regra

**Critério único**: Se a regra técnica conflita com **realidade verificável do usuário**.

**Exemplo válido**:
- Usuário: "Meu banco cobra taxa no 5º dia útil, não calendário"
- Sistema: Ajustar cálculo de vencimento para considerar dias úteis

**Exemplo inválido**:
- Usuário: "Quero que o sistema me avise quando gastar demais"
- Sistema: ❌ NÃO implementar — viola "Consciência, não Controle"

### 5.2 Quando divergir da filosofia

**Resposta padrão**:
```
Entendo a solicitação, mas isso conflita com a filosofia central do sistema:
[explicar qual pilar é violado]

Alternativa compatível:
[sugerir implementação descritiva em vez de prescritiva]
```

**Exemplo**:
```
Usuário: "Quero que o sistema mostre em vermelho quando eu gastar mais que o previsto"

Resposta:
"Entendo a solicitação, mas cores vermelho/verde implicam julgamento (certo/erro),
o que conflita com 'Previsto vs Executado — ambos legítimos'.

Alternativa compatível:
- Mostrar diferença em número: '+R$ 200' ou '-R$ 200'
- Usar cor neutra (azul/roxo) para destacar visualmente
- Permitir que usuário interprete o significado"
```

---

## PARTE 6: CHECKLIST PRÉ-COMMIT

Antes de finalizar qualquer implementação, verificar:

- [ ] Lógica de negócio está no **backend**?
- [ ] Valores são calculados **dinamicamente**?
- [ ] Linguagem é **descritiva** (não prescritiva)?
- [ ] Código segue **padrões existentes**?
- [ ] Não há **duplicação de funcionalidade**?
- [ ] Não conflita com **regras soberanas**?
- [ ] Documentação foi **atualizada**?
- [ ] Relatório final foi **gerado**?

---

## HIERARQUIA DE PRIORIDADES

Em caso de conflito entre requisitos:

1. **Filosofia soberana** (Consciência, não Controle)
2. **Regras técnicas invioláveis** (Backend soberano, Cálculo dinâmico, etc.)
3. **Padrões do código existente**
4. **Solicitação específica do usuário**

**Se usuário solicitar algo que viola (1) ou (2), questionar antes de implementar.**

---

**Versão**: 1.0
**Data**: 2025-12-27
**Status**: Regra-mestre ativa

---

*"Este documento governa toda implementação futura. Não é sugestão — é mandato técnico."*
