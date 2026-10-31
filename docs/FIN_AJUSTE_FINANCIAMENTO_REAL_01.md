# FIN-AJUSTE-FINANCIAMENTO-REAL-01 — Financiamento CAIXA ao contrato real (TR projetada)

**Situação (30/10/2026): autorizado pelo titular.** Sequência: commit → push → migration `20261204090000` → deploy → ajuste de saldo real (função oficial) → conferência só por leitura.
- Regularização histórica até 09/2026 (parcelas 1–29 incluídas): pacote separado, FIN-REGULARIZACAO-HISTORICO-01, que não usa o histórico estimado como saldo.

## 1. Diagnóstico (produção, só leitura)

| Item | Situação |
|---|---|
| Contrato | id 4 "Financiamento CAIXA" (Pessoal): SAC/TR, R$ 500.000, 420 meses, 1ª parcela em 05/05/2024, taxa nominal 9,3764% a.a. Criado no Flask em 10/05/2026, sem TR aplicada |
| Parcelas | As 420 estão pendentes, com despesas pendentes. Sem movimentos, parcelas históricas, ajustes nem amortizações. Seguro estimado (DFI + MIP, 8 faixas) |
| Fonte da verdade (CAIXA, demonstrativo de 30/10/2026) | Saldo após a parcela 30 (05/10/2026): R$ 269.524,62, 390 meses restantes. Parcela 31 (05/11/2026): 2.801,62 + 163,44 + 25,00 = **R$ 2.990,06** |
| Função oficial | `ajustar_saldo_devedor` (botão "Ajustar saldo"), com referência na parcela 31: o saldo informado é o de entrada da 31 |
| Bloqueio | O recálculo SAC/TR exigia TR cadastrada para **cada** competência futura (até 2059); a TR publicada vai até 2026-10. O Flask faz igual |

**Decisão do titular (Opção B):** corrigir o motor. Não cadastrar TR fictícia em Indexadores.

## 2. Regra (migration `20261204090000`)

- **TR publicada:** sempre prevalece.
- **Competência depois da última publicada:** TR projetada = a última publicada, só em memória durante o cálculo, nunca gravada em Indexadores.
- **Sem TR entre competências publicadas:** continua recusado (`TR_AUSENTE`), porque é dado real faltando.
- **Marca:** a parcela calculada com TR projetada fica em `financeiro.parcela_tr_projetada`, com o saldo e a quota de entrada da cadeia SAC/TR. A tela mostra o selo **TR PROJETADA** no cronograma e o aviso na próxima parcela.
- **TR real cadastrada depois (cadastro ou importação):** as parcelas projetadas dali em diante são recalculadas pela mesma cadeia (`fin_reprojetar_tr`). Só em perfil com escritor NOVO e sem parcela paga, histórica ou com movimento na faixa; caso contrário, ficam como estavam.
- **Simulação de quitação:** informa quando a TR é projetada.
- **Nenhum dado existente é alterado.** Reversão: `supabase/reversao/20261204090000_tr_projetada_anterior.sql`, em ordem (antes da reversão da 20261123).

## 3. Testes

- `tests/test_supabase_tr_projetada.py` (6 testes). O contrato fictício equivale ao real, com a TR só até 2026-10:
  - regra da TR, inclusive a lacuna recusada;
  - ajuste a partir da 31 (1–30 intactas, despesa de novembro atualizada no lugar, prazo 390);
  - TR real depois dá o mesmo resultado que o ajuste feito já com a TR (cadastro e importação);
  - escritor Flask e parcela paga na faixa: nada recalculado;
  - quitação com aviso;
  - reversão.
- **Testes ajustados à regra nova:**
  - simulação de quitação em 2099 (agora projeta) e lacuna em 2030 (recusada);
  - Indexadores: sem TR nenhuma, recusado; depois da última, projetada;
  - reversão da 20261123 em ordem.
- `web/tests/e2e/financiamentos_motor.spec.mjs`: contrato além da última TR publicada, com o selo só nas parcelas projetadas.

## 4. Ensaio numa cópia fiel e descartável da produção

| Conferência | Resultado |
|---|---|
| Migration | Só a tabela nova (vazia) e as 10 funções previstas; nenhum dado existente alterado |
| Ajuste oficial (parcela 31, R$ 269.524,62, 05/10/2026) | 390 parcelas recalculadas; saldo, data-base 05/10/2026, parcela-base 30, prazo 390 |
| Parcela 31 | 692,21 + 2.109,38 + seguro 161,55 + 25,00 = **R$ 2.988,13**: −R$ 1,93 em relação à CAIXA (amortização + juros −0,03; seguro −1,89) |
| Integridade | Parcelas e despesas 1–30 intactas; continuam 420 despesas, uma só em 11/2026 (a mesma linha, atualizada); nada gravado em Indexadores |
| Tabelas alteradas pelo ajuste | `financiamento`, `financiamento_parcela`, `conta`, `financiamento_ajuste_saldo`, `operacao_despesa`, `parcela_tr_projetada` |
| TR real de 11/2026 cadastrada depois (simulada na cópia) | Parcela 31 → R$ 2.988,15 (−1,91); as projetadas passam a começar na 32 |
| Reversão / reaplicação | Funções iguais às anteriores / iguais à aplicação |

## 5. Pendências (separadas, por decisão do titular)

- **Parcelas 1–30:** continuam pendentes, com despesas vencidas estimadas. Na tela:
  - "Parcelas pagas" fica em 0/420;
  - "Próxima parcela" segue apontando a parcela 1 (05/05/2024), porque a tela original usa a primeira não paga.

  Contrato próprio: os documentos têm os valores reais das parcelas 9–30, mas não das 1–8.
- **Amortização extraordinária de R$ 220.000 (2025):** não registrada, porque o saldo real já a contém e a função atual reduziria o saldo de novo.
- **Seguro:** −R$ 1,89 em relação à CAIXA (estimativa DFI + MIP), para calibração posterior.
- **Cadastro da TR real:** recalcula sozinho as projetadas do perfil com escritor NOVO. Depois de usada, a TR não pode ser editada (regra anterior de Indexadores).
- **Pagamento da parcela 30 (10/2026) pela tela de Despesas:** o saldo devedor passa a ser o da parcela paga de maior número (`saldo_devedor_pelas_parcelas`), e a parcela 30 ainda tem o valor estimado do cronograma antigo (R$ 464.285,71 depois dela). Depois de pagá-la, repetir o mesmo ajuste (parcela 31, R$ 269.524,62, 05/10/2026) recoloca o saldo real. O pagamento real foi de R$ 2.990,90; em Despesas, use a classificação da diferença ("ajuste").
