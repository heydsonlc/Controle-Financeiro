# Regras Financeiras do Sistema

Regras globais e por módulo que governam o comportamento do Controle Financeiro.

Última atualização: 2026-05-10

---

## Regras Globais de Proteção Financeira

Estas regras são invioláveis. Nenhuma funcionalidade nova pode quebrá-las.

1. **Dados financeiros executados não são alterados silenciosamente.** Qualquer mudança em parcelas ou contas já efetivadas exige bloqueio ou auditoria explícita.

2. **Parcelas pagas são preservadas.** Recálculos, edições estruturais e amortizações afetam apenas o trecho futuro.

3. **Contas pagas, baixadas, conciliadas ou efetivadas bloqueiam recálculos** que alterem seu valor ou competência.

4. **Recálculos atingem apenas parcelas ou contas pendentes.** O passado é soberano.

5. **Exclusões são permitidas apenas sem execução financeira.** Financiamento com parcela paga, consórcio contemplado, cartão com fatura paga — todos bloqueiam exclusão total.

6. **Cadastros mestres compartilháveis não são apagados automaticamente.** `ItemDespesa` usado por financiamento, recorrência ou cartão permanece mesmo após remoção da entidade principal.

7. **Alterações estruturais preservam rastreabilidade.** Amortizações, ajustes de saldo e recálculos são registrados com auditoria.

8. **Divergência entre simulação e extrato real usa marcos de ajuste documentados.** O sistema não reescreve o passado; registra a diferença e recalcula o futuro.

9. **Frontend não exibe botão visível sem função real**, salvo marcado explicitamente como "em desenvolvimento".

10. **Backend é soberano para regras financeiras.** Frontend apenas exibe dados já calculados e coleta entrada do usuário.

---

## Regras da Tela Despesas (Regra-Mãe)

A tela Despesas representa a **fatura mensal consolidada** da vida financeira. Tudo no sistema converge para essa regra.

**O que entra em Despesas**:
- Todas as `Conta` da competência selecionada
- Fatura de cartão de crédito (como `Conta` única por cartão)
- Parcelas de financiamento
- Despesas correntes e recorrentes

**O que não entra**:
- Lançamentos individuais de cartão
- Simulações
- Planejamentos sem execução
- Histórico bruto

**Regra soberana de fatura**:
- `status_pagamento == 'Pago'` → usar `total_executado` (soma de `LancamentoAgregado`)
- `status_pagamento == 'Pendente'` → usar `total_previsto` (soma de `OrcamentoAgregado`)

Esta regra não tem exceções.

**Competência**:
- Sempre definida explicitamente pelo usuário ou pelo sistema no momento da criação
- Nunca inferida de datas de transação, fechamento ou vencimento

---

## Regras de Receitas

- Receita prevista (`ReceitaOrcamento`) ≠ receita realizada (`ReceitaRealizada`)
- Valor realizado permanece zerado até efetivação explícita
- Pendências de competências anteriores permanecem visíveis até confirmação
- Confirmação de pendência preserva a competência original (não usa a data da confirmação)
- Contemplação de consórcio sem efetivação bancária aparece como receita prevista

---

## Regras de Cartões

**Fatura**:
- Fatura paga → valor = soma dos `LancamentoAgregado` (executado)
- Fatura pendente → valor = soma dos `OrcamentoAgregado` por Categoria do Cartão (previsto)

**Categoria do Cartão × Categoria da Despesa**:
- **Categoria do Cartão** (`CategoriaCartao`): organiza internamente a fatura do cartão
- **Categoria da Despesa** (`Categoria`): organiza o orçamento geral e o fluxo de despesas
- São independentes. Um lançamento pode ter as duas preenchidas ou apenas uma.

**Lançamentos da fatura**:
- Todo lançamento é `LancamentoAgregado`, independentemente da origem (recorrência ou manual)
- Editável via `PUT /api/cartoes/lancamentos/{id}`
- Categoria do Cartão obrigatória no fluxo de importação

**Status de limite por Categoria do Cartão**:
- Normal: utilizado < 80% do limite
- Atenção: utilizado entre 80% e 100%
- Estourado: utilizado > 100%
- Revisar: sem limite definido

---

## Regras de Importação de Cartão

**Descrição**:
- `descricao_original`: texto bruto do arquivo, imutável após importação
- `descricao_exibida`: editável pelo usuário, usada para exibição
- Reconhecimento futuro usa `descricao_original` como assinatura, não `descricao_exibida`

**Reconhecimento de recorrência**:
- Exige **mesmo cartão** como candidato (lançamentos de outro cartão não sugerem recorrência)
- Assinatura = descrição original + valor + cartão/competência

**Idempotência**:
- Garantida por `compra_id` (UUID v4) + `numero_parcela`
- Reimportação do mesmo arquivo não duplica lançamentos

**Fluxo**:
- Triagem primeiro (decidir se lançamento vira despesa)
- Classificação depois (Categoria da Despesa + Categoria do Cartão obrigatória)

---

## Regras de Financiamentos

### Composição do total

```
total_previsto = amortização + juros + seguro + taxa_administrativa
```

Nenhum componente pode ser omitido do extrato ou da visualização.

### Seguro habitacional

**Modo fixo/manual**:
- Seguro = valor fixo da vigência ativa no mês
- Definido pelo usuário por período de vigência

**Modo estimado DFI+MIP**:
- DFI = base_DFI × fator_DFI (base pode ser original ou segurada)
- MIP = juros_contratuais × fator_MIP da faixa etária corrente
- Faixa etária determinada por competência configurável
- Todos os cálculos usam o helper central de seguro (único ponto de verdade)

### Modo CAIXA SAC/TR

- Opt-in por financiamento (não global)
- Taxa mensal = taxa_nominal_anual / 12
- TR mensal aplicada ao saldo: `saldo_corrigido = saldo × (1 + TR_mensal)`
- Quota de amortização = `saldo_corrigido / parcelas_restantes`
- Juros = `saldo_corrigido × taxa_mensal`
- TR ausente para a competência bloqueia a geração (erro explícito)
- Seguro calculado pelo helper central após correção

### Ajuste de saldo devedor real

- Preserva todas as parcelas do passado (pagas ou não)
- Recalcula apenas parcelas futuras (a partir do mês seguinte ao ajuste)
- Registra auditoria: saldo informado, saldo calculado, diferença, data do ajuste
- Bloqueia se houver conta efetivada no trecho a ser recalculado

### Amortização extraordinária

- Não altera parcelas pagas nem contas efetivadas
- Recalcula saldo devedor e parcelas futuras
- Seguro recalculado pelo helper central para cada parcela futura
- Comportamento padrão: reduz valor da prestação, mantém prazo
- Opção de reduzir prazo mantendo prestação: pendência futura (FIN-AMORT-OPCAO-1)

### Exclusão

Bloqueada quando existir qualquer dos seguintes:
- Parcela com `status_pagamento == 'Pago'`
- `Conta` efetivada vinculada
- `FinanciamentoAmortizacaoExtra` registrada
- Ajuste de saldo registrado
- Movimentação financeira vinculada

### ItemDespesa e Financiamento

- `ItemDespesa` nunca é excluído automaticamente (é cadastro mestre)
- Troca de `item_despesa_id` bloqueada com execução financeira
- Sem execução: contas pendentes sincronizadas automaticamente após troca

---

## Regras de Contas Bancárias

1. `saldo_atual` é sempre derivado: `saldo_inicial + Σ(créditos) - Σ(débitos)`
2. Toda alteração de saldo gera `MovimentoFinanceiro` (sem exceção)
3. Ajuste manual é lançamento explícito — aparece no extrato, auditável
4. Extrato é a fonte de verdade do saldo
5. Transferência entre contas gera 2 movimentos atômicos (débito na origem, crédito no destino)

---

## Regras de Recorrências

- Despesas recorrentes com prazo: termo oficial (não "recorrência parcelada" ou "recorrência com prazo")
- Parcelas pagas são protegidas contra recálculos
- Encerramento por quantidade de parcelas ou data final (configurável)
- Débito automático vinculável a conta bancária específica
- Vínculo com cartão e Categoria do Cartão disponível

---

## Regras de Veículos / Mobilidade

- Cenário ativo persistido via backend (`data/mobilidade_cenario_ativo.json`)
- Efetivação atômica: guard `status == 'PREVISTA'` + rollback em caso de falha
- Meio cartão → `LancamentoAgregado` via `CartaoService.adicionar_lancamento()`
- Demais meios → `ItemDespesa(tipo='Simples')` + `Conta`
- Categoria padrão Mobilidade criada automaticamente se não existir

---

## Regras de UX / Frontend

- Botão visível = função real implementada
- Se funcionalidade incompleta: ocultar o botão ou marcar como "em desenvolvimento"
- Ícones monocromáticos com `currentColor` (sem emoji em botões funcionais)
- Cores vermelho/verde apenas para status objetivo (Pago/Pendente), nunca como julgamento
- Linguagem descritiva e neutra: "Você gastou R$ 300 além do previsto" (não "Você gastou demais")
- Colunas de ação: slots fixos, botões desabilitados quando indisponível (não ausentes)

---

## Filosofia Central

O sistema descreve a realidade financeira. Não prescreve comportamento.

- "Você gastou R$ 300 além do previsto" ✅
- "Você gastou demais" ❌

Previsto vs Executado são **ambos legítimos**. A diferença é informação, não falha.
