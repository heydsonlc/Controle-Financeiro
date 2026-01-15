# 🔧 AJUSTE DE FILTRO — VENCIMENTO POR DATA (DD/MM/AAAA)
## Tela: Gerenciamento de Despesas

---

## 1️⃣ LEITURA OBRIGATÓRIA ANTES DE CODAR

✅ **ANÁLISE REALIZADA**

Verificado:
- Filtro de competência usa `MM/AAAA` e aplica client-side
- Filtro de vencimento usava `MM/AAAA` (removido)
- Backend `/api/despesas` retorna todas despesas sem filtros
- Nenhum conflito com cálculo de faturas ou dashboard

⚠️ Confirmação:
- **NÃO existe duplicação** - filtro antigo foi substituído
- **NÃO conflita** com cálculo de faturas (usa `cartao_competencia`)
- **NÃO afeta** dashboard (usa `mes_referencia`)

---

## 2️⃣ CONTEXTO DA DECISÃO

A tela possuía dois campos `MM/AAAA`:
- Competência (eixo principal)
- Vencimento (filtro refinador)

Isso gerava ambiguidade conceitual.

**Decisão tomada:**
- Competência permanece como eixo principal (`MM/AAAA`)
- Vencimento transformado em **DATA COMPLETA (DD/MM/AAAA)**
- Vencimento atua apenas como filtro refinador dentro da competência

---

## 3️⃣ REGRA FUNCIONAL OFICIAL

### 🎯 Regra

1. **Competência (obrigatória):** Define universo de despesas
2. **Vencimento até (opcional):** Filtra dentro da competência
   - Mostrar apenas despesas onde: `data_vencimento <= data_selecionada`

### Exemplos práticos

| Competência | Vencimento até | Resultado                              |
| ----------- | -------------- | -------------------------------------- |
| 12/2025     | —              | Todas as despesas de dezembro          |
| 12/2025     | 10/12/2025     | Só as que vencem até dia 10            |
| 12/2025     | 31/12/2025     | Todas (equivalente a não filtrar)      |
| 12/2025     | 05/01/2026     | Inclui parcelas/cartões que "escorrem" |

### ❌ Não fazer

- Não remover o filtro de competência
- Não cruzar despesas de outras competências
- Não alterar regras de cálculo financeiro
- Não alterar comportamento de cartões ou faturas

---

## 4️⃣ ALTERAÇÕES REALIZADAS

### Frontend - HTML
**Arquivo:** `frontend/templates/despesas.html`

**Linha 34-36:** Substituído input de texto por input de data
```html
<!-- ANTES -->
<input type="text" id="filtro-mes" class="filter-input"
       placeholder="Vencimento (MM/AAAA)" maxlength="7"
       onkeyup="mascaraMesAno(this)" onchange="aplicarFiltros()">

<!-- DEPOIS -->
<input type="date" id="filtro-vencimento-ate" class="filter-input"
       placeholder="Vencimento até" onchange="aplicarFiltros()"
       title="Filtrar despesas que vencem até esta data (dentro da competência)">
```

### Frontend - JavaScript
**Arquivo:** `frontend/static/js/despesas.js`

**Linha 27:** Atualizado event listener
```javascript
// ANTES
document.getElementById('filtro-mes').addEventListener('change', aplicarFiltros);

// DEPOIS
document.getElementById('filtro-vencimento-ate').addEventListener('change', aplicarFiltros);
```

**Linhas 223-243:** Reordenada lógica de filtros
```javascript
// 1. Filtrar por competência PRIMEIRO (eixo soberano)
if (competenciaFiltro && competenciaFiltro.length === 7) {
    const competenciaISO = converterMesAnoBRparaISO(competenciaFiltro);
    if (competenciaISO) {
        const anoMes = competenciaISO.substring(0, 7);
        despesasFiltradas = despesasFiltradas.filter(d => {
            if (!d.mes_competencia) return false;
            return d.mes_competencia === anoMes;
        });
    }
}

// 2. Filtrar por vencimento até (data completa) DENTRO da competência
if (vencimentoAteFiltro) {
    despesasFiltradas = despesasFiltradas.filter(d => {
        if (!d.data_vencimento) return false;
        return d.data_vencimento <= vencimentoAteFiltro;
    });
}
```

### Backend
**Nenhuma alteração necessária** - filtros aplicados client-side

---

## 5️⃣ CRITÉRIOS DE ACEITE

✅ Competência continua sendo o eixo soberano
✅ Vencimento funciona como refinamento temporal
✅ Nenhuma regra de fatura/cartão foi alterada
✅ Dashboard e alertas continuam consistentes
✅ UX mais clara (não existem dois MM/AAAA)

---

## 6️⃣ LISTA DE ARQUIVOS ALTERADOS

- `frontend/templates/despesas.html` (linha 34-36)
- `frontend/static/js/despesas.js` (linhas 27, 204, 223-243)
- `docs/AI_TASK_FILTRO_VENCIMENTO_POR_DATA.md` (NOVO - este documento)

---

## 7️⃣ OBSERVAÇÕES

- **Lógica antiga ficou obsoleta?** SIM - filtro antigo de vencimento `MM/AAAA` foi removido
- **Alguma tela perdeu função?** NÃO - funcionalidade aprimorada
- **Decisão arquitetural assumida?** SIM - **Competência como eixo soberano, vencimento como refinador**

---

## 8️⃣ IMPACTO

- **Impacto funcional:** MÉDIO - melhora UX significativamente
- **Impacto em dados existentes:** NENHUM - compatível
- **Impacto em testes manuais:** SIM - requer validação visual

---

**Data de implementação:** 2025-12-27
**Versão:** 1.0
**Status:** ✅ CONCLUÍDO
