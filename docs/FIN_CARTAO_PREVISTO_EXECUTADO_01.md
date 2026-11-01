# FIN-CARTAO-PREVISTO-EXECUTADO-01 — Separação definitiva entre previsão e execução das despesas fixas

**Situação (01/11/2026): `FIN_CARTAO_PREVISTO_EXECUTADO_01_PRONTO_PARA_PUBLICACAO`.** Implementado, testado e ensaiado numa cópia fiel da produção.
- Migration remota, push e deploy aguardam autorização.
- A conciliação real da Netflix 11/2026 e o apelido da Apple One continuam fora.

Base: `docs/FIN_CARTAO_DESPESAS_FIXAS_01.md` (natureza única, reconhecimento e conciliação, publicados em `a1d3be4`).

## 1. Defeito

A compra que a recorrência gera para o mês (a previsão) entrava no **executado** da fatura e no **valor a pagar**, mesmo sem cobrança real. No Visa 11/2026, as 4 previsões somavam R$ 329,60 no executado de R$ 2.595,45:

| Previsão | Valor | Cobrança real no arquivo |
|---|---|---|
| Claude | 109,90 | não |
| ChatGPT | 99,90 | não |
| Apple One | 59,90 | não |
| Netflix | 59,90 | sim, como compra comum (606, R$ 44,90, já executada) |

- **Os R$ 269,70 do diagnóstico** são as três sem cobrança.
- **A previsão da Netflix** também sai do executado: a cobrança real dela (R$ 44,90) já é executada pela compra 606, e mantê-la contaria a Netflix duas vezes.

## 2. Regras

| Situação da despesa fixa | Executado | Previsto | Na tela |
|---|---|---|---|
| **PREVISTA**: gerada, sem cobrança, fatura não paga | 0 | valor da recorrência | "Previsto R$ X · aguardando cobrança" |
| **CONFIRMADA**: cobrança importada, realizada ou conciliada | valor cobrado | o previsto guardado | "Previsto R$ X · diferença ±R$ Y" ou "· confirmado" |
| **NAO_COBRADA**: a fatura foi paga sem ela | 0 | valor da recorrência | "Previsto R$ X · não cobrada nesta fatura" |
| **PAGA**: em fatura paga antes desta regra (histórico) | valor (como foi pago) | valor | "Previsto R$ X · paga com a fatura" |

- **Previsto da fatura** = executado + previsões pendentes + o que falta dos limites. O valor exibido não muda; só o executado deixa de incluir previsões.
- **Pagamento:** paga o executado.
  - As previsões ainda pendentes ficam NAO_COBRADA naquela fatura (gatilho em `financeiro.pagamento_fatura`, só para pagamento de fatura pelo novo aplicativo), e a fatura paga fica igual ao que foi pago.
  - O **estorno** do pagamento desfaz as marcas: a previsão volta a aguardar cobrança.
  - Uma fatura só com previsões não tem o que pagar.
- **Cobrança que chega depois do pagamento:** a previsão NAO_COBRADA não é a ocorrência. A cobrança entra como compra da recorrência na próxima fatura aberta, com a competência original registrada.
- **Compra não reconhecida:** continua compra comum, executada uma vez. Candidatos ambíguos não conciliam (regra do FIXAS-01).
- **Conciliação e reversão:** como no FIXAS-01. Ao reverter, a previsão volta a PREVISTA, a compra absorvida volta, e o executado e o previsto voltam ao que eram.
- **Fatura fechada (consolidada):** a previsão continua fora do executado e não é realizada.
- **Faturas pagas:** preservadas.
- **Nenhum dado existente é alterado.**
  - O `valor_executado` gravado nas faturas abertas se atualiza no próximo recálculo.
  - Pagamento, lista de Despesas, faturas do mês, Cartões e Dashboard usam o executado calculado na hora.
- **Valor-base da recorrência:** não muda.

## 3. Onde mudou

**Migration `20261209090000`**, gerada por `scripts/gerar_migration_cartao_previsto_executado.py`.
- **Novas:** `situacao_previsao`, `valor_executado_compra` e o gatilho `previsoes_no_pagamento_da_fatura`.
- **Tabela de ocorrências:** `ocorrencia_recorrencia_cartao` ganha a origem `NAO_COBRADA` e a coluna `pagamento_id`.
- **Funções que passam a usar o executado sem previsões:**
  - pagamento e recálculo: `executado_fatura` e `recalcular_fatura`;
  - lista de Despesas e faturas do mês: `contas_do_mes` e `faturas_do_mes`;
  - Cartões: `fatura_por_categoria` (grupo "Despesas fixas" com `previsto_pendente`; `total_fatura` = executado; `total_previsto_pendente`) e `lancamentos_fatura_por_categoria` (situação, previsto e executado por compra);
  - Dashboard: `dashboard_resumo_tela`, em que "faturas em aberto" usa o executado atual;
  - `compras_da_fatura`, com a coluna nova `valor_executado`.
- **Importação (`analisar_importacao_cartao`):** a previsão não cobrada não é a ocorrência.
- **Reversão de conciliação (`reverter_ocorrencia_recorrencia`):** recusa a marca de não cobrada, que só sai pelo estorno.
- **Reversão da migration:** `supabase/reversao/20261209090000_cartao_previsto_executado_anterior.sql`.
  - É recusada com marca de não cobrada vigente.
  - Em produção, a ordem é 1209 antes de 1208.

**Telas** (design preservado):
- **Despesas (`despesas.js`):** a linha da fixa mostra o executado (R$ 0,00 enquanto aguarda) e a legenda com o previsto e a situação. O subtotal mostra o executado e "· R$ X aguardando cobrança". O total previsto usa o previsto das pendentes, e o total executado não as inclui.
- **Cartões (`cartoes.js`):** a compra prevista ganha a marcação "Prevista · aguardando cobrança". O total da fatura é o executado.
- **Compatibilidade com o Flask:** sem os campos novos, as duas telas ficam como antes.

## 4. Testes

- **`tests/test_supabase_cartao_previsto_executado.py`** (19):
  - previsão sem cobrança (lista, faturas do mês, Cartões, lançamentos, pagamento, gravado e Dashboard);
  - recorrência futura;
  - cobrança igual, menor e maior;
  - compra não reconhecida;
  - conciliação e reversão;
  - fatura fechada;
  - fatura paga histórica;
  - pagamento, repetição e estorno;
  - cobrança depois do pagamento;
  - fatura só com previsões;
  - concorrência;
  - perfis separados;
  - limites preservados;
  - funções internas;
  - reversão e reaplicação sem alterar dados.
- **`tests/test_gerador_migration_cartao_previsto_executado.py`** (2): a migration é a saída exata do gerador.
- **`web/tests/unit/fatura-blocos.test.mjs`:** as quatro situações, os totais previsto e executado, e a fixa sem os campos (Flask).
- **Ajustados à regra** (a previsão sai do executado):
  - 4 testes de `tests/test_supabase_cartao_despesas_fixas.py`;
  - 2 de `tests/test_supabase_cartoes.py`;
  - 1 de `tests/test_supabase_recorrencia_cartao.py` (a definição vigente da análise passa a ser a da 1209).
- **Regressão:**
  - Python por impacto: 26 arquivos, 596 aprovados; a única falha é a i3, dívida conhecida de `regularizar_historico`;
  - unitários 38/38;
  - E2E 116/116.

## 5. Ensaio (cópia fiel e descartável da produção, com a 1208)

| Conferência | Antes | Depois |
|---|---|---|
| Cópia × produção | idêntica | — |
| Dados (compras, faturas, movimentos, contas bancárias) | — | iguais (a migration não muda dado) |
| Visa 11/2026: executado / valor a pagar | R$ 2.595,45 | **R$ 2.265,85** (só cobranças reais) |
| Visa 11/2026: previsto (lista de Despesas) | R$ 2.767,75 | R$ 2.767,75 |
| Visa: Despesas Fixas | 4 · R$ 329,60 executados | 4 · R$ 0,00 executado, R$ 329,60 aguardando cobrança |
| Visa: Assinaturas (Categoria do Cartão) | R$ 227,70 | R$ 227,70 |
| Black 11/2026: executado | R$ 7.264,80 | **R$ 7.194,80** (sem a previsão "Plano NullCel" de R$ 70,00) |
| Black 11/2026: previsto | R$ 8.889,84 | R$ 8.889,84 |
| Black: categorias / Outros | 51 · R$ 4.312,25 / 38 · R$ 2.882,55 | iguais |
| Dashboard: faturas em aberto (11/2026) | R$ 9.790,25 | R$ 9.460,65 |
| Dashboard: uso dos limites e categorias | — | iguais |
| Faturas pagas (Visa 05–09/2026) | — | iguais |
| Faturas abertas só com previsões (Black 10 e 12/2026; Visa 10 e 12/2026, 03 e 04/2027) | executado = previsões | executado R$ 0,00 |
| Netflix 11/2026 conciliada (só na cópia) | — | executado R$ 2.265,85 (igual); previsto R$ 2.752,75; aguardando R$ 269,70 |
| Reversão da conciliação (cópia) | — | compras iguais; faturas iguais fora o executado gravado do Visa, recalculado para R$ 2.265,85 |

**Dados de produção desde a homologação de 01/11:** o titular cadastrou a recorrência "Plano NullCel" (R$ 70,00, Black, de 10/2026), inativou o "X Premium" e reclassificou "Emporio Prime" (R$ 140,08). É uso normal do aplicativo; o ensaio partiu desse estado.

## 6. Pendências

- **Publicação:** migration `20261209090000`, push e deploy, com autorização.
- **Netflix 11/2026 e Apple One:** conciliação e apelido, com autorização específica.
- **Faturas de 10/2026 (Black e Visa) abertas só com previsões:** o executado passa a R$ 0,00. Se foram pagas fora do aplicativo, o registro do pagamento é assunto à parte; nada foi alterado.
- **Previsão de recorrência inativada** (X Premium 10/2026): continua na fatura aberta como prevista. Dispensá-la é decisão do titular.
- **Confirmação sem importação:** uma despesa fixa só deixa de ser prevista com a cobrança importada ou conciliada com uma compra lançada. Não há "confirmar cobrança" manual (não pedido).
