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

## 2️⃣ Formato PADRÃO de Resposta da API

### 2.1 Estrutura obrigatória

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

### 2.2 Resposta de erro

```json
{
  "success": false,
  "message": "Descrição clara do erro"
}
```

📌 **Nunca retornar erro sem mensagem**.

---

## 3️⃣ Função Obrigatória no Frontend

### 3.1 Função padrão de normalização

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

## 4️⃣ Contratos Específicos do Sistema

### 4.1 Categorias da Despesa (Analíticas)

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

### 4.2 Categorias do Cartão (Orçamentárias)

📍 **Tabela:** `item_agregado`

* Usadas para:
  * Controle de limite do cartão
  * Alertas
* **Nunca representam despesas**
* **Podem não existir em um lançamento**

```txt
item_agregado_id = nullable
```

---

### 4.3 Lançamentos no Cartão

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

### 4.4 Fatura do Cartão

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

## 5️⃣ Regras de Exclusão (Obrigatórias)

### 5.1 Categoria do Cartão

| Situação        | Ação         |
| --------------- | ------------ |
| Sem lançamentos | Pode excluir |
| Com lançamentos | ❌ Bloquear   |

Mensagem obrigatória:

```txt
"Não é possível excluir esta categoria. Existem X lançamento(s) vinculados."
```

---

### 5.2 Financiamentos

| Situação                    | Ação                  |
| --------------------------- | --------------------- |
| Nenhuma parcela paga        | Pode excluir          |
| Parcela paga ou amortização | ❌ Bloquear (inativar) |

---

## 6️⃣ Mudanças Estruturais (CHECKLIST OBRIGATÓRIO)

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

## 7️⃣ Convenções Visuais (Frontend)

### 7.1 Selects obrigatórios

* Categoria da Despesa → **obrigatória**
* Categoria do Cartão → **opcional**
* Texto explicativo quando opcional

Exemplo:

```html
<small>Lançamentos sem categoria não afetam limites.</small>
```

---

## 8️⃣ Regra Final (a mais importante)

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

**Versão:** 1.0.0
**Data:** 2025-01-17
**Última atualização:** 2025-01-17
