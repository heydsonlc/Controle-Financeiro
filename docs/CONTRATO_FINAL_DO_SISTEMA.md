📘 CONTRATO FINAL DO SISTEMA

Sistema de Controle Financeiro Pessoal

1. VISÃO GERAL

Este sistema tem como objetivo representar a vida financeira real do usuário, de forma previsível, consistente e auditável.

O sistema não é um simples registro de lançamentos, mas sim um modelo financeiro estruturado, baseado em obrigações reais, consolidadas mensalmente.

2. PRINCÍPIO CENTRAL (REGRA-MÃE)

A tela DESPESAS representa a FATURA MENSAL CONSOLIDADA da vida financeira.

Tudo no sistema converge para essa regra.

3. CONCEITOS FUNDAMENTAIS (GLOSSÁRIO)
3.1 Conta

Representa uma obrigação financeira indivisível

É a unidade mínima da fatura mensal

Cada Conta aparece como uma linha na tela DESPESAS

Conta = obrigação real

3.2 Fatura Mensal

Conjunto de todas as Contas existentes em uma competência

Não depende de lançamentos

Não depende de categorias

Não é calculada no frontend

3.3 Competência

Mês/ano de referência da obrigação financeira

Define quando a Conta pertence à fatura

Exemplo: 2025-05

**REGRA FUNDAMENTAL:** A competência é sempre definida explicitamente pelo usuário ou pelo sistema durante a criação da obrigação. Nenhuma funcionalidade do sistema infere ou calcula competência a partir de datas de transação ou fechamento.

3.4 Planejamento × Execução

Planejamento: intenção futura (simulações, contratos, previsões)

Execução: obrigação real cobrável

Apenas execução gera Conta.

4. CONTRATO DA TELA DESPESAS
4.1 O que ENTRA em DESPESAS

Todas as Contas da competência:

Fatura de cartão de crédito

Parcelas de financiamento

Despesas correntes

Despesas recorrentes (mensais ou intra-mensais)

4.2 O que NÃO ENTRA em DESPESAS

Lançamentos individuais

Simulações

Planejamentos

Histórico bruto

4.3 Regras imutáveis da DESPESAS

❌ Não soma lançamentos

❌ Não calcula valores

❌ Não infere previsto/executado

❌ Não agrupa obrigações automaticamente

✔️ Apenas consome Conta

5. CONTRATOS POR DOMÍNIO
5.1 Cartão de Crédito
Regras

Cada cartão gera uma única Conta por competência

A fatura é consolidada no backend

O backend decide:

valor da fatura

status (pago ou pendente)

O frontend recebe:

valor_fatura soberano

status já decidido

Proibições

❌ Frontend decidir previsto/executado

❌ Mostrar ambos ao mesmo tempo

❌ Recalcular valores

5.2 Despesas Recorrentes
Tipos

Mensal ou superior

1 Conta por competência

Intra-mensal (semanal, dias da semana, quinzenal)

1 Conta por ocorrência

Podem existir N Contas no mesmo mês

Regras

Cada ocorrência = obrigação real

Nenhum agrupamento automático

Descrição pode incluir data para clareza

5.2.1 Despesas Recorrentes Pagas via Cartão

Conceito

Despesas recorrentes cujo meio de pagamento é cartão de crédito (ex: Netflix, Spotify, assinaturas).

São configuradas como despesas recorrentes, mas geram lançamentos no cartão ao invés de Contas diretas.

Comportamento

ItemDespesa com recorrente=True e meio_pagamento='cartao'

Gera automaticamente LancamentoAgregado a cada competência

Aparece no bloco "Despesas Fixas" do detalhamento da fatura do cartão

Entra no valor PREVISTO da fatura do cartão

NÃO gera Conta separada (a Conta é a fatura do cartão)

Regras

1 despesa recorrente = 1 lançamento por mês (idempotência)

Não são parcelamentos (total_parcelas = 1)

Não dependem de lançamento manual mensal

São obrigações previsíveis e automáticas

Marcado com is_recorrente=True no LancamentoAgregado

Classificação no Detalhamento

Bloco "Despesas Fixas" da fatura do cartão

Não entram em "Compras Parceladas"

Não entram em "Por Categoria" (exceto se tiver item_agregado_id)

Não entram em "Outros Lançamentos"

Exemplo Prático

Usuário cadastra: Netflix R$ 45,90 recorrente mensal via Cartão Nubank

Sistema gera automaticamente todo mês: LancamentoAgregado(is_recorrente=True)

Aparece em: Despesas → Fatura Nubank → Despesas Fixas → Netflix R$ 45,90

5.3 Financiamentos / Empréstimos
Regras

Financiamento é contrato

Parcela é cálculo

Cada parcela gera exatamente uma Conta

1 parcela = 1 Conta = 1 linha em DESPESAS

Pagamento

Pagar parcela:

marca a parcela como paga

sincroniza a Conta vinculada

Backend é soberano

5.4 Pagamento Parcial de Fatura (Planejado — Fase 3)

⚠️ FUNCIONALIDADE NÃO IMPLEMENTADA

O sistema foi arquitetado para suportar pagamento parcial de faturas de cartão de crédito, porém esta funcionalidade NÃO está ativa no escopo atual.

Decisão de projeto

Priorizar simplicidade, previsibilidade e educação financeira

Evitar complexidade prematura

Implementar apenas após estabilização do core (3+ meses em produção)

Evitar incentivo a práticas financeiras prejudiciais (rotativo)

Conceito (quando implementado)

Pagamento parcial: valor pago < valor total da fatura

Saldo residual: diferença entre valor fatura e valor pago

Rotativo: saldo residual que entra na próxima fatura

Juros: aplicados sobre saldo residual (configurável por cartão)

IOF: imposto sobre operações de rotativo (configurável)

Impactos da implementação futura

Backend

Novos campos: valor_pago, saldo_devedor, taxa_juros, iof

Migration para adicionar campos ao modelo Conta

Endpoint: POST /api/cartoes/{id}/faturas/{competencia}/pagar-parcial

Lógica de cálculo de juros e IOF

Geração automática de lançamento "Saldo rotativo" na próxima fatura

Validação de múltiplos pagamentos parciais

Frontend

Modal de pagamento com opção "Pagar valor diferente"

Indicador visual de "Pagamento Parcial Realizado"

Exibição de saldo devedor pendente

Histórico de pagamentos parciais por fatura

UX e Educação Financeira

Avisos sobre custo de juros rotativos

Calculadora de simulação de rotativo

Alertas de endividamento progressivo

Incentivo ao pagamento integral (melhores práticas)

Regra atual (vigente)

Pagamento de fatura é SEMPRE integral

Ao pagar: status_fatura → PAGA

Novos lançamentos após pagamento → próxima fatura

Não existe saldo residual

6. PAPEL DO BACKEND × FRONTEND
Backend (soberano)

Decide:

existência da Conta

valor

status

vínculo com domínio (cartão, recorrência, financiamento)

Garante idempotência

Garante consistência

Frontend (consumidor)

❌ Não decide regra de negócio

❌ Não recalcula valores

❌ Não infere status

✔️ Apenas exibe dados consolidados

7. CATEGORIAS (METADADO)

Categoria nunca decide existência de Conta

Categoria nunca interfere em valor ou status

Categoria é apenas:

organização

filtro

análise posterior

8. ANTI-REGRAS (COISAS PROIBIDAS)

Estas regras NUNCA devem ser quebradas:

❌ Frontend calcular fatura

❌ Agrupar obrigações automaticamente

❌ Usar lançamentos para compor DESPESAS

❌ Misturar planejamento com execução

❌ Criar exceções visuais que escondam regra

❌ Duplicar regra de negócio em mais de um lugar

9. CONSEQUÊNCIAS DESTE CONTRATO

Ao seguir este contrato, o sistema garante:

Previsibilidade

Consistência financeira

Facilidade de manutenção

Facilidade de expansão

Ausência de ambiguidade conceitual

Backend como fonte única da verdade

10. ESTADO DO SISTEMA (CONGELAMENTO)

No momento deste documento:

Pilar	Status
Cartão	✅ Fechado
Recorrência	✅ Fechado
Financiamentos	✅ Fechado
DESPESAS	✅ Contrato consolidado
Backend soberano	✅
Frontend simples	✅
👉 Este contrato está congelado.
Qualquer mudança futura deve partir deste documento, nunca do código isoladamente.