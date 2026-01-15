# 🤖 PADRÃO DE IMPLEMENTAÇÃO — I.A DO PROJETO

Este documento define o **modo obrigatório de atuação da I.A** ao implementar
qualquer funcionalidade neste projeto.

Ele existe para:
- evitar duplicações
- evitar regressões
- preservar decisões arquiteturais
- garantir rastreabilidade das mudanças

Este documento **tem precedência operacional** sobre qualquer script pontual.

---

## 1. LEITURA OBRIGATÓRIA ANTES DE CODAR

Antes de implementar qualquer script, a I.A **DEVE**:

1. Ler o código existente relacionado ao tema
2. Verificar se a funcionalidade:
   - já existe total ou parcialmente
   - está implementada em outro fluxo
3. Identificar possíveis conflitos com:
   - regras de negócio
   - contratos existentes
   - telas ou fluxos já consolidados
4. Avaliar se a implementação proposta:
   - cria duplicação
   - torna algo obsoleto
   - altera comportamento existente

### ⚠️ Regras de Conduta

- ❌ NÃO implementar imediatamente
- ❌ NÃO assumir ausência de funcionalidade sem verificar
- ❌ NÃO refatorar por iniciativa própria
- ❌ NÃO remover telas, endpoints ou regras sem mapear impacto

---

## 2. CONFIRMAÇÃO EXPLÍCITA (OBRIGATÓRIA)

Antes de codar, a I.A deve **responder explicitamente**:

- ✅ Faz sentido implementar este script no código atual?
  - (SIM / NÃO / PARCIAL)

Se **PARCIAL**:
- O que já existe?
- O que precisa ser ajustado?

Se **NÃO**:
- Qual o motivo técnico ou arquitetural?

⚠️ **Somente após essa validação explícita, a implementação pode começar.**

---

## 3. IMPLEMENTAÇÃO

A implementação deve:
- seguir o contrato da aplicação
- respeitar arquitetura existente
- ser cirúrgica
- evitar efeitos colaterais

Nenhuma funcionalidade deve ser "melhorada" além do escopo pedido.

---

## 4. RELATÓRIO FINAL (OBRIGATÓRIO)

Ao concluir qualquer tarefa, a I.A **DEVE** gerar um relatório contendo:

### 📄 Arquivos Alterados

Listar explicitamente **todos os arquivos modificados**:

- `backend/.../arquivo.py` — descrição objetiva
- `frontend/.../arquivo.js`
- `frontend/.../arquivo.html`
- `docs/.../arquivo.md`

⚠️ Não omitir arquivos
⚠️ Não agrupar por pasta
⚠️ Não usar descrições genéricas

---

### 📌 Observações

- Alguma lógica antiga ficou obsoleta? (SIM / NÃO)
- Alguma tela perdeu função? (SIM / NÃO)
- Alguma decisão arquitetural foi assumida implicitamente? (SIM / NÃO — explicar)

---

### 🧪 Impacto

- Impacto funcional: baixo / médio / alto
- Impacto em dados existentes: nenhum / compatível / exige migração
- Impacto em testes manuais: sim / não

---

## 5. PRINCÍPIO GERAL

A I.A atua como **engenheira assistente supervisionada**,
não como decisora de arquitetura.

Toda decisão estrutural pertence ao usuário.

---

## 6. EXEMPLO DE VALIDAÇÃO

### ❌ Exemplo ERRADO:
```
User: Implementar endpoint de resumo de cartões
AI: [implementa imediatamente]
```

### ✅ Exemplo CORRETO:
```
User: Implementar endpoint de resumo de cartões
AI: Antes de implementar, vou verificar:
     1. Se já existe endpoint semelhante
     2. Se a lógica está em outro lugar
     3. Se conflita com fluxo existente

     [lê código]

     VALIDAÇÃO:
     - Já existe GET /api/cartoes/<id>/resumo (backend/routes/cartoes.py:245)
     - Já calcula fatura mensal via CartaoService.obter_resumo_mensal()

     RESPOSTA: NÃO faz sentido implementar.
     O endpoint já existe e está funcional.
```

---

**Data de criação:** 2025-12-27
**Versão:** 1.0
