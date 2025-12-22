# 📜 CONTRATO DE API

## Projeto: Controle Financeiro

> Este documento define **regras obrigatórias** de comunicação entre Backend e Frontend.
> O objetivo é **evitar inconsistências, selects vazios, bugs silenciosos e retrabalho**.

---

## 1️⃣ Princípios Gerais (OBRIGATÓRIOS)

### 1.1 Backend é a fonte da verdade

* O **frontend não calcula**
* O **frontend não deduz regras**
* O **frontend não interpreta dados**
* O frontend **apenas exibe o que a API retorna**

---

### 1.2 Frontend nunca assume formato de resposta

❌ **Proibido**:

```js
response.forEach(...)
```

✅ **Obrigatório**:

```js
const json = await response.json();
const dados = extrairArray(json);
```

---

## 2️⃣ Conceito Central do Sistema (FUNDAMENTO)

### 2.1 Despesas como Fatura Mensal Consolidada

> **Princípio:** A tela de Despesas representa a **fatura mensal consolidada** da vida financeira do usuário.

**Analogia do Cartão de Crédito:**

Assim como uma fatura de cartão de crédito:
* Lista TODOS os itens do mês (competência)
* Não importa quando cada compra foi feita
* Importa quando a fatura vence (mês de competência)
* Cada item é uma linha da fatura

**No sistema:**
* Cada **Conta** = Item da fatura mensal
* **Despesas** = Fatura mensal consolidada
* **Competência** = Mês de referência (igual ao "mês da fatura")

### 2.2 O que entra na "Fatura Mensal" (Despesas)

Em cada competência, a tela de Despesas deve listar **TODAS as Contas** que representam valores a serem pagos naquele mês, independentemente da origem:

| Tipo de Conta | Entra em Despesas? | Motivo |
|---------------|-------------------|--------|
| Parcela de financiamento | ✅ SIM | Obrigação do mês |
| Parcela de consórcio | ✅ SIM | Obrigação do mês |
| Fatura de cartão de crédito | ✅ SIM | Obrigação do mês |
| Despesa direta (paga) | ✅ SIM | Compromisso do mês |
| Despesa direta (pendente) | ✅ SIM | Compromisso do mês |

**Regra Definitiva:**
```
Se existe uma Conta com aquela competência → aparece na "fatura mensal" (Despesas)
```

### 2.3 Por que Lançamentos é diferente

**Lançamentos** = Registro de eventos pontuais
* Não é fatura
* É histórico operacional
* Serve para rastreamento

**Despesas** = Fatura mensal consolidada
* É obrigação
* É planejamento
* Serve para controle de caixa

### 2.4 Fluxo Financeiro Completo

```
┌─────────────────────────────────────────────┐
│ 1. RECEITA CAI NO MÊS                      │
│    "Salário de Janeiro chegou"              │
└──────────────┬──────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────┐
│ 2. CONSULTAR DESPESAS (COMPETÊNCIA JAN/25) │
│    "Minha fatura do mês de Janeiro"         │
│                                              │
│    - Financiamento casa: R$ 8.000           │
│    - Consórcio carro: R$ 1.200              │
│    - Fatura Nubank: R$ 2.500                │
│    - Internet (pendente): R$ 100            │
│    ────────────────────────────              │
│    TOTAL A PAGAR: R$ 11.800                 │
└──────────────┬──────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────┐
│ 3. PAGAR ITENS DA FATURA                    │
│    Marcar como "Pago" quando efetuar        │
└─────────────────────────────────────────────┘
```

**Esse é o conceito central do sistema.**

---

## 3️⃣ Formato PADRÃO de Resposta da API

### 3.1 Estrutura obrigatória

Todos os endpoints **DEVEM** seguir este padrão:

```json
{
  "success": true,
  "data": [],
  "message": "Mensagem opcional"
}
```

### Campos:

| Campo   | Tipo                  | Obrigatório | Descrição              |
| ------- | --------------------- | ----------- | ---------------------- |
| success | boolean               | ✅           | Indica sucesso ou erro |
| data    | array | object | null | ✅           | Dados retornados       |
| message | string                | ❌           | Mensagem amigável      |

---

### 3.2 Resposta de erro

```json
{
  "success": false,
  "message": "Descrição clara do erro"
}
```

📌 **Nunca retornar erro sem mensagem**.

---

## 4️⃣ Função Obrigatória no Frontend

### 4.1 Função padrão de normalização

Essa função **DEVE existir** e **DEVE ser usada em todo o frontend**:

```js
function extrairArray(response) {
    if (Array.isArray(response)) return response;
    if (response?.data && Array.isArray(response.data)) return response.data;
    return [];
}
```

### Uso correto:

```js
const response = await fetch('/api/categorias');
const json = await response.json();
const categorias = extrairArray(json);
```

---

## 5️⃣ Contratos Específicos do Sistema

### 5.1 Categorias da Despesa (Analíticas)

📍 **Tabela:** `categoria`

* Usadas para:
  * Relatórios
  * Análises
  * Dashboards
* **Obrigatórias em todo lançamento**

```txt
Categoria da Despesa ≠ Categoria do Cartão
```

---

### 5.2 Categorias do Cartão (Orçamentárias)

📍 **Tabela:** `item_agregado`

* Usadas para:
  * Controle de limite do cartão
  * Alertas
* **Nunca representam despesas**
* **Podem não existir em um lançamento**
* **`nome` é obrigatório e soberano**
  * Origem: `item_agregado.nome`
  * O frontend deve exibir **exclusivamente** este campo (proibido “Categoria 1/2…” por índice)

```txt
item_agregado_id = nullable
```

---

### 5.3 Lançamentos no Cartão

📍 **Tabela:** `lancamento_agregado`

| Campo            | Regra         |
| ---------------- | ------------- |
| cartao_id        | ✅ Obrigatório |
| categoria_id     | ✅ Obrigatório |
| item_agregado_id | ❌ Opcional    |

#### 4.3.1 Categoria da Despesa (Analítica) — OBRIGATÓRIA

* **Campo:** `categoria_id`
* **Origem:** tabela `categoria`
* **Finalidade:** análise financeira, relatórios e dashboards

**Regras:**
* Todo lançamento DEVE possuir `categoria_id`
* Frontend deve bloquear submit sem esse campo
* Backend deve rejeitar lançamento sem `categoria_id`

#### 4.3.2 Categoria do Cartão (Orçamentária) — OPCIONAL

* **Campo:** `item_agregado_id`
* **Origem:** tabela `item_agregado`
* **Finalidade:** controle de limite do cartão

**Regras:**
* Pode ser `null`
* Pode não existir no DOM
* Nunca é obrigatória

**Lançamentos sem `item_agregado_id`:**
* Entram na fatura
* **NÃO** consomem limite
* **NÃO** disparam alertas

#### 4.3.3 Regras de Frontend (OBRIGATÓRIAS)

**O frontend NUNCA deve assumir que:**
* O campo de categoria do cartão existe
* O campo possui valor

**Toda leitura deve ser null-safe:**

```js
// ✅ CORRETO
const selectCategoriaCartao = document.getElementById('categoria-cartao');
const itemAgregadoId = selectCategoriaCartao && selectCategoriaCartao.value
    ? parseInt(selectCategoriaCartao.value)
    : null;

// ❌ ERRADO
const itemAgregadoId = parseInt(document.getElementById('categoria-cartao').value);
```

**O payload:**
* Só inclui `item_agregado_id` se houver seleção válida
* **NUNCA** enviar `item_agregado_id: null` explicitamente

```js
// ✅ CORRETO
const payload = {
    cartao_id: cartaoId,
    categoria_id: categoriaDespesaId, // OBRIGATÓRIA
    descricao,
    valor
};

if (itemAgregadoId !== null) {
    payload.item_agregado_id = itemAgregadoId;
}

// ❌ ERRADO
const payload = {
    item_agregado_id: itemAgregadoId || null, // NÃO enviar null explícito
    ...
};
```

#### 4.3.4 Regras de Backend (Garantias)

**Backend deve aceitar:**
* Lançamentos com `item_agregado_id`
* Lançamentos sem `item_agregado_id`

**Backend NÃO deve:**
* Rejeitar lançamento sem categoria do cartão
* Criar despesa individual por lançamento

#### Regras Gerais:

* Lançamento **sempre** entra na fatura
* Só consome limite se tiver `item_agregado_id`

---

### 5.4 Fatura do Cartão

📍 **Tabela:** `conta`

* **A única despesa real do cartão**
* Consolidada por mês
* Inclui:
  * Lançamentos com categoria
  * Lançamentos sem categoria

```txt
Cartão NÃO gera várias despesas.
Cartão gera UMA fatura mensal.
```

---

## 6️⃣ Regras de Exclusão (Obrigatórias)

### 6.1 Categoria do Cartão

| Situação        | Ação         |
| --------------- | ------------ |
| Sem lançamentos | Pode excluir |
| Com lançamentos | ❌ Bloquear   |

Mensagem obrigatória:

```txt
"Não é possível excluir esta categoria. Existem X lançamento(s) vinculados."
```

---

### 6.2 Financiamentos

| Situação                    | Ação                  |
| --------------------------- | --------------------- |
| Nenhuma parcela paga        | Pode excluir          |
| Parcela paga ou amortização | ❌ Bloquear (inativar) |

---

## 7️⃣ Mudanças Estruturais (CHECKLIST OBRIGATÓRIO)

Sempre que **qualquer campo, regra ou relacionamento** for alterado, a I.A **DEVE executar** este checklist:

### 🔁 Varredura obrigatória:

* [ ] Models (`models.py`)
* [ ] Services (`services/*.py`)
* [ ] Routes (`routes/*.py`)
* [ ] Frontend JS relacionado
* [ ] HTML (inputs, selects, labels)
* [ ] Banco de dados (migration)

🚫 **Proibido** entregar alteração sem essa varredura.

---

## 8️⃣ Separação de Responsabilidades (Telas do Sistema)

### 8.1 Tela de Lançamentos

**Definição:** Registro histórico de **execuções financeiras pontuais**.

**O que DEVE aparecer:**
* Despesas Diretas (tipo: Simples) - pagas e pendentes
* Lançamentos de Cartão de Crédito
* Receitas / Entradas Pontuais

**O que NÃO DEVE aparecer:**
* Parcelas de Financiamentos (tipo: individual)
* Parcelas de Consórcios (tipo: individual)
* Obrigações futuras estruturadas

**Finalidade:** Visão operacional e histórica de transações cotidianas.

---

### 8.2 Tela de Despesas

**Definição:** Mapa de **obrigações financeiras** que devem ser pagas quando houver disponibilidade de receita.

> **Princípio:** "As despesas serão o retrato dos pagamentos que eu devo fazer quando a receita cair."

**O que DEVE aparecer:**
* Despesas Diretas (pagas ou pendentes)
* Parcelas de Financiamentos e Consórcios
* Faturas de Cartão de Crédito
* **QUALQUER Conta que represente obrigação financeira real**

**Regras:**
* A entidade `Conta` é a base desta tela
* Todas as Contas (tipo: Simples, individual, etc.) devem ser exibidas
* Categoria é metadado - sua ausência NUNCA pode impedir renderização
* Filtro de competência deve mostrar apenas parcelas do mês selecionado

**Finalidade:** Planejamento financeiro e controle de obrigações.

---

### 8.3 Tela de Financiamentos

**Definição:** Planejamento e detalhamento de **financiamentos e consórcios**.

**O que DEVE aparecer:**
* Simulações (SAC, PRICE)
* Tabela de evolução do saldo
* Geração de parcelas
* Amortizações

**Finalidade:** Gerenciamento detalhado de financiamentos.

**Relação com outras telas:**
* Alimenta a tela de Despesas (gera Contas)
* NÃO substitui a tela de Despesas

---

### 8.4 Regra de Ouro - Histórico e Metadados

> **Histórico é registro de fato ocorrido.
> Categoria é metadado.
> Metadado nunca pode decidir existência.**

**Aplicação prática:**
* Se uma Conta existe, ela DEVE ser renderizada
* Categoria ausente → exibir "Sem categoria"
* Categoria ausente → NUNCA bloquear exibição
* Frontend NUNCA deve assumir formato de resposta

---

## 9️⃣ Convenções Visuais (Frontend)

### 9.1 Selects obrigatórios

* Categoria da Despesa → **obrigatória**
* Categoria do Cartão → **opcional**
* Texto explicativo quando opcional

Exemplo:

```html
<small>Lançamentos sem categoria não afetam limites.</small>
```

---

## 🔟 Regra Final (a mais importante)

> ❗ **Nenhuma funcionalidade é considerada pronta
> se não funcionar no fluxo completo de ponta a ponta.**

Fluxo mínimo de validação:

1. Criar cartão
2. Criar categoria do cartão
3. Definir limite
4. Criar lançamento
5. Ver impacto na fatura
6. Ver impacto nos limites

---

## 📌 Status do Documento

* ✔️ Contrato definido
* ✔️ Regras claras
* ✔️ Evita regressões
* ✔️ Orienta a I.A corretamente

---

## 🔧 Implementação da Função `extrairArray`

### Localização: `frontend/static/js/utils.js`

```js
/**
 * Extrai array de uma resposta de API
 * Garante compatibilidade com diferentes formatos de resposta
 *
 * @param {*} response - Resposta da API
 * @returns {Array} Array de dados ou array vazio
 */
function extrairArray(response) {
    // Se já é array, retorna direto
    if (Array.isArray(response)) return response;

    // Se tem propriedade 'data' com array, retorna
    if (response?.data && Array.isArray(response.data)) return response.data;

    // Se tem propriedade 'categorias' com array, retorna
    if (response?.categorias && Array.isArray(response.categorias)) return response.categorias;

    // Se tem propriedade 'itens' com array, retorna
    if (response?.itens && Array.isArray(response.itens)) return response.itens;

    // Fallback: retorna array vazio para evitar erros
    console.warn('⚠️ extrairArray: formato inesperado', response);
    return [];
}
```

### Uso em todos os JS:

```js
// ❌ ANTES (errado):
const response = await fetch('/api/categorias');
const categorias = await response.json();
categorias.forEach(...); // PODE QUEBRAR!

// ✅ DEPOIS (correto):
const response = await fetch('/api/categorias');
const json = await response.json();
const categorias = extrairArray(json);
categorias.forEach(...); // SEMPRE FUNCIONA
```

---

## 🔄 Despesas Recorrentes Pagas via Cartão

### Conceito

Despesas recorrentes cujo `meio_pagamento='cartao'` (ex: Netflix, Spotify, assinaturas) **não geram Conta**, mas sim **LancamentoAgregado** automaticamente a cada competência.

### Modelo de Dados

**ItemDespesa (despesa recorrente):**
```python
{
  "id": 123,
  "nome": "Netflix",
  "valor": 45.90,
  "recorrente": true,
  "tipo_recorrencia": "mensal",
  "meio_pagamento": "cartao",  # ← NOVO CAMPO
  "cartao_id": 1,               # ← NOVO CAMPO (obrigatório quando meio_pagamento='cartao')
  "item_agregado_id": 5,        # ← NOVO CAMPO (opcional - categoria do cartão)
  "categoria_id": 10            # ← Categoria analítica (obrigatório)
}
```

**LancamentoAgregado (gerado automaticamente):**
```python
{
  "id": 456,
  "cartao_id": 1,
  "item_agregado_id": 5,         # opcional
  "categoria_id": 10,
  "descricao": "Netflix",
  "valor": 45.90,
  "data_compra": "2025-01-15",
  "mes_fatura": "2025-01-01",
  "is_recorrente": true,          # ← NOVO CAMPO (marca como Despesa Fixa)
  "item_despesa_id": 123,         # ← NOVO CAMPO (referência à despesa recorrente)
  "numero_parcela": 1,
  "total_parcelas": 1
}
```

### Regras Técnicas

#### Backend

1. **Geração Automática:**
   - Quando `ItemDespesa.recorrente=True` e `meio_pagamento='cartao'`
   - Função `gerar_lancamentos_cartao_recorrente()` gera `LancamentoAgregado`
   - **NÃO** gera `Conta` (a Conta é a fatura do cartão)

2. **Idempotência:**
   - 1 despesa recorrente = 1 lançamento por competência
   - Verificação por `(item_despesa_id, mes_fatura, is_recorrente=True)`

3. **Campos Obrigatórios:**
   - `meio_pagamento='cartao'` → `cartao_id` é obrigatório
   - `categoria_id` é sempre obrigatório (categoria analítica)

#### Frontend

1. **Classificação no Detalhamento da Fatura:**
   - Lançamentos com `is_recorrente=True` aparecem no bloco **"Despesas Fixas"**
   - Não entram em "Compras Parceladas"
   - Não entram em "Outros Lançamentos" (exceto se não tiver categoria)

2. **Cálculo da Fatura:**
   - Lançamentos recorrentes entram no **valor PREVISTO** da fatura
   - São computados normalmente no total

#### Endpoint Afetado

**GET /api/despesas:**
- Retorna fatura do cartão como Conta
- Lançamentos recorrentes estão **dentro** da fatura (não como Conta separada)

**GET /api/cartoes/{id}/lancamentos:**
- Inclui lançamentos com `is_recorrente=True`
- Frontend classifica em "Despesas Fixas"

**GET /api/cartoes/{id}/resumo:**
- Inclui lançamentos recorrentes no cálculo do `total_gasto`

### Exemplo Prático

**Cadastro:**
```
POST /api/despesas
{
  "nome": "Netflix",
  "valor": 45.90,
  "recorrente": true,
  "tipo_recorrencia": "mensal",
  "meio_pagamento": "cartao",
  "cartao_id": 1,
  "categoria_id": 10,
  "data_vencimento": "2025-01-15"
}
```

**Resultado Automático:**
- Sistema gera `LancamentoAgregado` todo mês 15
- Aparece em "Despesas Fixas" da fatura do Cartão 1
- Não cria Conta separada

---

## 📋 Checklist de Validação de Endpoint

Antes de considerar um endpoint **pronto**, validar:

- [ ] Retorna formato padrão `{ success, data, message }`
- [ ] Frontend usa `extrairArray()`
- [ ] Nenhum `forEach` direto em `response.json()`
- [ ] Erro retorna mensagem clara
- [ ] Testado com sucesso no fluxo completo
- [ ] Logs de debug removidos (ou comentados)
- [ ] Documentado neste contrato (se for novo)

---

**Versão:** 1.1.0
**Data:** 2025-01-17
**Última atualização:** 2025-12-22 (Adicionado: Despesas Recorrentes Pagas via Cartão)
