# FIN-SALDO-PRECEDENCIA-AJUSTE-01 — Precedência do ajuste real de saldo no financiamento

**Situação (31/10/2026): `FIN_SALDO_PRECEDENCIA_AJUSTE_01_PRONTO_PARA_PUBLICACAO`.** Implementado, testado e ensaiado numa cópia fiel da produção.
- Migration, deploy e pagamento real da parcela 30 aguardam autorização.

## 1. Defeito (diagnóstico, produção só lida)

| Item | Onde |
|---|---|
| Pagamento da parcela | `financeiro.pagar_despesa` → `financeiro.sincronizar_parcela_paga` (20261120) |
| Recálculo do saldo | `financeiro.saldo_devedor_pelas_parcelas` (20261123): saldo da parcela **paga de maior número**, menos as amortizações posteriores ao vencimento dela |
| Também gravam por ela | `reabrir_parcela_estornada` (estorno), `registrar_parcelas_historicas`, `registrar_amortizacao_extra` (saldo atual nulo) |
| Tabela de ajustes | `public.financiamento_ajuste_saldo` (id 1: referência = parcela 31, `data_referencia` 05/10/2026, `saldo_devedor_real` R$ 269.524,62, `saldo_devedor_anterior` R$ 464.285,71, `observacao` CAIXA, `criado_em`) |
| Parcela-base | Só no contrato: `financiamento.numero_parcela_base = 30` (a anterior à primeira recalculada), regravado por amortização |

Cadeia do defeito: `pagar_despesa` → `sincronizar_parcela_paga` → `saldo_devedor_atual = saldo_devedor_pelas_parcelas(...)`.
- A função não consulta ajuste algum: usa o `saldo_devedor_apos_pagamento` da parcela paga de maior número.
- O ajuste recalcula só as parcelas da referência em diante (31..420). A parcela 30 manteve o saldo estimado antigo (R$ 464.285,71).
- Pagar a 30 gravaria R$ 464.285,71 no lugar do saldo real.

**Mesma falha na amortização extraordinária:** a base do recálculo é o saldo estimado da parcela anterior à primeira recalculada. Hoje, uma amortização depois de 05/10/2026 recalcularia 31..420 a partir de R$ 464.285,71.

## 2. Regra implementada (migration `20261206090000`)

- **Parcela-base do ajuste:** a última parcela coberta pelo saldo real (a anterior à primeira recalculada).
  - Fica registrada em `financeiro.ajuste_saldo_base`, gravada por `ajustar_saldo_devedor`.
  - O ajuste vigente é o mais recente do contrato, porque ele recalcula tudo depois da base (`fin_ajuste_vigente`).
- **Saldo do contrato (`saldo_devedor_pelas_parcelas`):**
  - paga de maior número **≤ parcela-base** (ou nenhuma paga): vale o **saldo real do ajuste**;
  - paga **posterior** à parcela-base: vale a cadeia das parcelas, que já parte do saldo real (evolução normal, sem congelar);
  - nos dois casos, menos as amortizações posteriores à data da âncora.
- **Amortização:**
  - ancorada na parcela-base: parte do saldo real;
  - anterior a ela: recusada (`AJUSTE_POSTERIOR`), porque o saldo real já a contém e recalcular dali reescreveria o ajuste.
- **Pagamento continua igual:** parcela paga, valor pago, diferença, data, contador, despesa e movimento.
- **Sem ajuste:** tudo como antes.
- **Inalterado:** TR projetada (real prevalece, projetada só em memória, selo, recálculo ao cadastrar a TR real) e a regularização histórica.
- **Dados:** só a tabela nova. Ajuste já existente tem a parcela-base deduzida por duas vias que precisam concordar:
  - o contrato;
  - a contagem das recalculadas.

  Se não for identificável, a migration para sem gravar nada.
- **Reversão:** `supabase/reversao/20261206090000_precedencia_ajuste_saldo_anterior.sql` (funções ao texto de 20261123; nenhum saldo recalculado).

## 3. Parcela 30 — valor real

Valor real R$ 2.990,90; despesa prevista R$ 4.934,18 (cadeia estimada antiga).
- O pagamento usa o mecanismo existente: valor diferente do devido com `tipo_ajuste = AJUSTE` e justificativa.
- A parcela registra `valor_pago` 2.990,90 e `dif_apurada` 1.943,28, sem mexer no saldo real.

## 4. Testes

`tests/test_supabase_precedencia_ajuste_saldo.py` (9), contrato fictício equivalente ao real:
- **A:** parcela 30;
- **B:** parcelas anteriores à base, como histórica, paga em Despesas ou estornada;
- **C:** 31 e 32 pela cadeia, com estornos;
- **D:** sem ajuste, igual ao texto anterior;
- amortização ancorada e recusada;
- TR real cadastrada depois;
- base com referência paga e ajuste mais recente;
- dedução da base na migration, inclusive quando ela para;
- reversão e reaplicação.

`tests/test_supabase_financiamentos_motor.py`: a reversão do motor reverte a 20261206 antes e a reaplica.

## 5. Ensaio (cópia fiel e descartável da produção; cada cenário numa transação desfeita)

| Conferência | Resultado |
|---|---|
| Cópia | Idêntica à produção |
| Migration (arquivo final, md5 `4d103233…344c`) | Só a tabela nova; nenhum dado existente alterado; parcela-base deduzida: ajuste 1 → **30** |
| **A — parcela 30** (R$ 2.990,90, `AJUSTE`, conta Caixa) | 29/420 → **30/420**; saldo **R$ 269.524,62 → R$ 269.524,62**; próxima **31**; sem novo ajuste |
| A — pagamento | Parcela paga, `valor_pago` 2.990,90, `dif_apurada` 1.943,28; despesa paga em 05/10/2026; 1 movimento de débito R$ 2.990,90 (23 → 24); saldo da Caixa no ensaio 71.006,24 → 68.015,34 (efeito do pagamento normal) |
| A — futuras | Parcelas 31..420 idênticas; 390 projetadas (31..420); data-base 05/10/2026, base 30, prazo 390 |
| **B — parcela anterior** (lote revertido; 29 paga em Despesas; 1..28 históricas; depois a 30) | Saldo **R$ 269.524,62** em todos os passos (antes: R$ 465.476,19 ao pagar a 29); depois 30/420, próxima 31 |
| **C — parcela 31** depois da 30 | Saldo evolui pela cadeia: **R$ 269.267,97** (o saldo após a 31, calculado do saldo real); 31/420, próxima 32 |
| **D — sem ajuste** (parcela-base retirada na transação) | Comportamento anterior: saldo R$ 464.285,71 (o estimado da 30) |
| Cópia depois dos cenários | Só as sequências de id (não voltam com rollback); dados iguais |

## 6. Observações e pendências

- **Saldo exibido na linha da parcela 30:** a tabela de parcelas continua mostrando R$ 464.285,71 em "saldo após", que é o estimado antigo. O ajuste não recalcula a parcela-base.
  - O saldo do contrato (R$ 269.524,62) é o que vale.
  - Aceito temporariamente pelo titular (31/10/2026): a linha fica como está; a apresentação do "saldo após" da parcela-base é tratada à parte, se necessário.
- **Dívida técnica (registrada pelo titular; não bloqueia a publicação):** `test_i3_toda_escrita_do_novo_aplicativo_recusa_perfil_do_flask_sem_gravar` falha desde `98c75fb`, já no HEAD sem este pacote.
  - Causa: `regularizar_historico` valida o formato do mês antes da permissão de escrita do perfil (guarda de escritor).
  - Nada é gravado, mas a recusa não vem pela guarda.
  - A correção (ordem das guardas) fica para um pacote próprio; aqui a regularização não é alterada.
- **Depois da publicação:** pagamento real da parcela 30 (R$ 2.990,90, conta Caixa, diferença `AJUSTE`), e em seguida o ajuste dos saldos reais das contas.

## 7. Publicação e pagamento real da parcela 30 (31/10/2026)

- **Publicação:**
  - commit `dda1bdd`, push `98c75fb..dda1bdd`;
  - migration `20261206090000` aplicada sozinha (47 versões), com as duas vias de dedução da parcela-base iguais a 30;
  - sem deploy, porque não há mudança de tela.
- **Validação da publicação** (só leitura):
  - saldo R$ 269.524,62, ajuste 1 e parcela-base 30;
  - 29/420, parcela 30 pendente;
  - parcelas 31..420, TR projetada, despesas, movimentos, saldos bancários, amortizações e a regularização (173 itens) iguais ao retrato anterior.
- **Pagamento da parcela 30:**
  - feito por `pagar_despesa`, como titular, numa transação com as conferências antes do commit;
  - R$ 2.990,90 em 05/10/2026, conta Caixa, diferença `AJUSTE` com justificativa.

| Conferência (sessão nova, só leitura) | Resultado |
|---|---|
| Parcela 30 | Paga; `valor_pago` R$ 2.990,90; `dif_apurada` R$ 1.943,28; despesa paga em 05/10/2026 pela Caixa |
| Contador / próxima | **30/420**; próxima = parcela **31** (05/11/2026, R$ 2.988,13, TR PROJETADA) |
| Saldo do financiamento | **R$ 269.524,62** (preservado; sem novo ajuste) |
| Movimentos | 23 → 24: débito de R$ 2.990,90 na Caixa (movimento 172); anteriores iguais |
| Saldo da Caixa | R$ 71.006,24 → R$ 68.015,34 (efeito normal do pagamento); Nubank R$ 12.469,48 |
| Ajuste 1, parcelas 31..420, TR projetada, amortizações, regularização, Apple One | Iguais |
| Tabelas alteradas | `conta`, `financiamento_parcela`, `movimento_financeiro`, `conta_bancaria`, `operacao_despesa`, `pagamento_fatura` |
