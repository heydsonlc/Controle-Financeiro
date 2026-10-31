# FIN-REGULARIZACAO-HISTORICO-01 — Histórico do Pessoal encerrado até 09/2026

**Situação (30/10/2026): execução autorizada pelo titular**, com trava exata: só confirmar se o plano de produção der 122 despesas (R$ 36.684,84), 22 faturas (R$ 44.350,00) e 29 parcelas (R$ 146.591,64), total 173 itens e R$ 227.626,48.
- A parcela 30 **não** é paga neste pacote (ver §6).

## 1. Decisão do titular (Opção 1)

Pagamento histórico **sem movimento**: até a competência 09/2026, o que está pendente passa a pago, com data de pagamento = vencimento.
- Sem movimento bancário e sem alterar saldo de conta.
- Sem alterar o saldo devedor do financiamento: o histórico estimado não é fonte do saldo; o saldo real vem do ajuste de 05/10/2026.
- Com auditoria e reversão.
- Outubro/2026 em diante, a Empresa e o que já está pago ficam intactos.

## 2. Diagnóstico (produção, só leitura)

No Pessoal, até 09/2026: 14 despesas pagas (com movimento) e 174 pendentes. Não existe status cancelado ou dispensado.

| Tipo | Pendentes | Valor |
|---|---|---|
| Despesas comuns (05–09/2026) | 123 | R$ 36.744,74 |
| Faturas de cartão (10/2025–09/2026; 4 com R$ 0,00) | 22 | R$ 44.350,00 |
| Parcelas 1–29 do financiamento CAIXA (valores estimados) | 29 | R$ 146.591,64 |

- O pagamento oficial (`pagar_despesa`, `pagar_fatura`) exige conta bancária e cria movimento. Só 17 das 123 despesas indicam a conta, e as faturas não indicam nenhuma.
- **"Apple One" (R$ 59,90, 05/2026):** é a despesa do item 459, pago pelo cartão 388, que tem compras mensais na fatura desde 05/2026. O gasto já está na fatura, então a despesa fica fora (regra genérica, não por id).

## 3. Mecanismo (migration `20261205090000`)

- **`financeiro.regularizar_historico(perfil, {ate_competencia, confirmar, esperado}, chave)`:**
  - **Sem `confirmar`:** só o plano (itens em ordem cronológica, totais por tipo e por competência, as despesas representadas na fatura). Nada é gravado.
  - **Com `confirmar`:** exige `esperado` {quantidade, valor} igual ao plano conferido; senão `PLANO_MUDOU` e nada é gravado.
  - **Grava, item a item, numa transação:**
    - despesa e fatura: `status_pagamento = 'Pago'`, `data_pagamento = data_vencimento`;
    - parcela: `status = 'pago'`, `valor_pago = valor_previsto_total` (estimado), `dif_apurada = 0`.
  - **Não grava:** movimento, saldo de conta, saldo devedor nem parcela histórica permanente.
- **Elegível:** pendente, sem data de pagamento, sem movimento algum, competência ≤ corte. O corte precisa ser anterior ao mês corrente (`COMPETENCIA_ABERTA`).
- **Guardas:** só quem gere o perfil e com o escritor NOVO. Idempotente pela chave.
- **Auditoria:** `financeiro.regularizacao_historica`, uma linha por item, com o estado anterior.
- **`financeiro.reverter_regularizacao_historica(perfil, lote, chave)`:** devolve o estado anterior, mas só se cada item continua como a regularização o deixou. Tudo ou nada.
- **Reversão da migration:** recusada enquanto houver lote vigente.

## 4. Testes

`tests/test_supabase_regularizacao_historica.py` (5 testes):
- plano sem gravar e elegibilidade: paga, outubro, Empresa e despesa no cartão ficam fora; 29 parcelas entram; ordem cronológica;
- confirmar: só os itens do plano mudam, sem movimento nem saldo de conta, financiamento intacto, compras e receitas intactas, auditoria, repetição;
- recusas: plano mudou, competência aberta, quem não gere, perfil no Flask;
- reversão do lote, com recusa se um item mudou;
- reversão da migration.

## 5. Ensaio numa cópia fiel e descartável da produção (já com a TR projetada e o ajuste real)

| Conferência | Resultado |
|---|---|
| Migration | Só a tabela de auditoria (vazia); nenhum dado existente alterado |
| Plano (Pessoal, até 09/2026) | **173 itens, R$ 227.626,48**: 122 despesas R$ 36.684,84; 22 faturas R$ 44.350,00; 29 parcelas R$ 146.591,64. Fora: Apple One (R$ 59,90), representado na fatura |
| Plano grava algo? | Não |
| Execução | Só `conta`, `financiamento_parcela`, `regularizacao_historica` e `operacao_despesa` mudam; todos os itens pagos na data do vencimento |
| Movimentos e saldos bancários | Nenhum movimento novo; saldos iguais |
| Financiamento | Saldo R$ 269.524,62, data-base 05/10/2026, prazo 390: iguais. Parcelas 1–29 pagas, 30–420 pendentes. Na tela: 29/420 pagas, próxima = parcela 30 (05/10/2026) |
| Outubro/2026 em diante | Igual |
| Pendente até 09/2026 depois | Só o Apple One (representado na fatura) |
| Reversão do lote | 173 revertidos; despesas e parcelas exatamente como antes |

## 6. Depois da execução real

- **Parcela 30 (10/2026): não pagar ainda.** Pagar uma parcela recalcula o saldo pela parcela paga de maior número (`saldo_devedor_pelas_parcelas`), e isso desconsideraria o ajuste de saldo real de 05/10/2026 (parcela-base 30), levando o saldo a cerca de R$ 464 mil estimados. Antes disso, um pacote próprio deve dar precedência ao ajuste de saldo válido ancorado nessa parcela (decisão do titular).
- **Apple One de 05/2026:** continua pendente. O gasto está na fatura; você pode excluí-lo pela tela.
- **Saldos das contas bancárias:** ajuste dos saldos reais pela tela (contrato separado).
