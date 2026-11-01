# FIN-CARTAO-NUBANK-CREDITOS-01 — Créditos, estornos e ajustes da fatura na importação

**Situação (01/11/2026): `FIN_CARTAO_NUBANK_CREDITOS_01_PRONTO_PARA_PUBLICACAO`.** Implementado, testado e ensaiado numa cópia fiel da produção, junto com o FIN-CARTAO-NUBANK-PARCELADAS-01.
- Migrations remotas `20261211090000` e `20261212090000`, push e deploy aguardam autorização.
- A regularização das faturas reais aguarda autorização.

Base: `docs/FIN_CARTAO_NUBANK_PARCELADAS_01.md` (commits locais até `0baa621`).

## 1. Composição dos R$ 53,40 (arquivo `Nubank_2026-11-05.csv`, Black)

| Data | Descrição no arquivo | Valor | Natureza | Compra original |
|---|---|---|---|---|
| 26/10 | Estorno de "Apple.Com/Bill" (Apple) | R$ 50,22 | estorno de compra (parcial) | 5 compras Apple.Com/Bill da fatura podem ser a original (R$ 99,90, 129,90, 64,90, 119,00, 799,90): a escolha é do titular |
| 26/10 | IOF de volta de Cloudflare | R$ 0,99 | devolução de IOF | IOF de "Cloudflare" R$ 0,99 (26/10) |
| 24/10 | IOF de volta de Dramawave | R$ 1,46 | devolução de IOF | IOF de "Dramawave" R$ 1,46 (24/10) |
| 18/10 | IOF de volta de Dramawave | R$ 0,73 | devolução de IOF | IOF de "Dramawave" R$ 0,73 (18/10) |
| **Total** | | **R$ 53,40** | | |

O arquivo tem mais um valor negativo: "Pagamento recebido", R$ 12.099,02 (30/09). É o pagamento da fatura anterior, não crédito desta fatura. Continua fora: o pagamento é registrado em Despesas ("pagar fatura").

**Conferência:** compras R$ 9.653,20 − créditos R$ 53,40 = R$ 9.599,80, o total do arquivo sem o pagamento.

## 2. Tratamento de cada tipo

| Tipo (texto do arquivo) | Natureza | Tratamento |
|---|---|---|
| "Pagamento recebido", "PGTO", "Obrigado pelo pagamento" | pagamento da fatura | fora (IGNORADA), com o motivo; não é crédito desta fatura |
| "IOF de volta de X", "Estorno de IOF" | `IOF_DEVOLVIDO` | abate a fatura; vinculado à cobrança "IOF de X" de mesmo valor |
| "Estorno de X", "Devolução", "Reembolso", "Cancelamento", "Chargeback" | `ESTORNO` | abate a fatura; vinculado à compra X com valor estornável suficiente; parcial ou integral |
| outro crédito ("Crédito de anuidade", "AJUSTE CREDITO PARC. LOJISTAA") | `AJUSTE` | abate a fatura, sem compra vinculada |

**Regras:**
- **Natureza própria:** o crédito não é compra negativa nem receita bancária. Fica em `financeiro.credito_fatura` e abate o valor a pagar da fatura uma vez.
- **Compra original:**
  - continua inteira, com valor, categoria e histórico;
  - vinculada só quando o texto do crédito a identifica sem dúvida: mesmo cartão, até 3 faturas antes, valor estornável ≥ crédito e, para o IOF, mesmo valor;
  - fica bloqueada para edição e exclusão: "Compra com crédito vinculado".
- **Escolha do titular:**
  - **mais de uma compra candidata:** Revisar até a escolha (`credito_compra_id`), ou 0 = sem compra vinculada;
  - **nenhuma candidata:** sem compra vinculada, com a descrição preservada.
- **Fatura paga:** não recebe crédito. O crédito vai para a próxima fatura aberta, como as compras; a paga fica intacta.
- **Fatura consolidada:** recusa a importação inteira.
- **Movimentação bancária:** nenhum movimento ou saldo bancário é criado ou alterado.

## 3. Mudanças

**Migration `20261212090000`** (gerada por `scripts/gerar_migration_cartao_nubank_creditos.py`; reversão em `supabase/reversao/20261212090000_cartao_nubank_creditos_anterior.sql`, recusada com crédito registrado):
- **`financeiro.credito_fatura`** (nova):
  - campos: natureza, descrição, data, valor, fatura, competência original, compra original, chave de duplicidade, operação e usuário;
  - RLS forçada, sem acesso direto do navegador.
- **`financeiro.creditos_fatura`** (nova, interna).
- **Valor a pagar = compras executadas − créditos**, nas mesmas funções de hoje:
  - pagamento e Dashboard: `executado_fatura`;
  - "contas a vencer": `recalcular_fatura`;
  - lista de Despesas: `contas_do_mes`;
  - faturas do mês: `faturas_do_mes`;
  - Cartões: `fatura_por_categoria` passa a dar `total_compras`, `total_creditos` e `total_fatura` (valor a pagar), e o grupo "Créditos e ajustes", negativo, com o status "Abatido";
  - lista da fatura: `lancamentos_fatura_por_categoria` traz o filtro `creditos` e o crédito em "Todos", com identificador próprio e sem ações de compra.
- **Compra com crédito vinculado** (`bloqueio_da_parcela`): preservada.
- **Prévia** (`analisar_importacao_cartao`):
  - classificação `CREDITO`, ou `REVISAR` com as candidatas, ou `JA_EXISTENTE` na reimportação;
  - campo `credito` com natureza, rótulo, compra, candidatas, parcial e fatura;
  - `creditos_a_abater` e `total_creditos_a_abater`.
- **Confirmação** (`importar_fatura_cartao`): grava os créditos na mesma transação e sob as mesmas travas. O resultado traz `creditos` e `total_creditos`.

**Leitores do arquivo:** o crédito não é mais retirado no navegador (CSV, XLSX e PDF). A prévia, no banco, classifica.

**Telas** (só com os campos novos; no Flask nada muda):
- **Importar (`importar_cartao.js`):**
  - a linha mostra "Crédito · Devolução de IOF · abate R$ 0,99 da fatura 11/2026 · compra original: IOF de "Cloudflare"" e entra na confirmação;
  - com mais de uma candidata: "Revisar", com o seletor compacto "Compra original do crédito" (as candidatas ou "Sem compra vinculada");
  - o pagamento recebido fica retirado, com o motivo do banco;
  - um crédito repetido legítimo (três ajustes de R$ 0,01) é mantido com "Manter";
  - a confirmação mostra "Créditos da fatura (abatem o valor a pagar)".
- **Cartões (`cartoes.js`):**
  - "Total da fatura" com "Compras R$ X · créditos −R$ Y";
  - o crédito na lista, sem botões de compra.
- **Despesas (`despesas.js` + adaptador):** o detalhe da fatura ganha o bloco "Créditos e Ajustes". O previsto e o executado descontam os créditos, e o total é o mesmo da lista e do pagamento.

O pacote das parceladas fica como estava. As 12 parcelas entram na confirmação, as 89 compras não se duplicam e a categoria é informada na linha. As parceladas ficam fora dos limites, e as despesas fixas continuam reconhecidas e conciliáveis.

## 4. Ensaio (cópia fiel e descartável da produção, migrations 1211 e 1212)

| Conferência | Resultado |
|---|---|
| Cópia × produção | idêntica |
| Migrations 1211 (md5 `5000de8e…`) e 1212 (md5 `f50dd11e…`) | compras, faturas, movimentos e contas bancárias iguais; leituras de valor iguais |
| Prévia do Nubank real | 89 `JA_EXISTENTE`, 12 `PARCELADA`, 3 `CREDITO` (IOF, vinculados), 1 `REVISAR` (estorno Apple, 5 candidatas), 1 `IGNORADA` (pagamento) |
| Prévia do Visa real (PDF Caixa, vencimento 05/11/2026) | ver seção 5 |
| Regularização simulada (categoria de ensaio nas parcelas; estorno Apple sem compra vinculada; ajustes de R$ 0,01 mantidos) | Black: 12 parcelas e 4 créditos; Visa: 11 parcelas, 1 despesa fixa (Netflix) e 3 créditos |
| Reimportação dos dois arquivos | nada novo ("Nenhuma linha para importar") |
| Faturas pagas, movimentos, contas bancárias | intactos |

**Black (Nubank) 11/2026:**

| | Hoje | Depois |
|---|---|---|
| Compras executadas | R$ 7.194,80 | R$ 9.653,20 |
| Créditos | — | R$ 53,40 |
| **Valor a pagar** (Cartões, Despesas, pagamento, Dashboard) | R$ 7.194,80 | **R$ 9.599,80** (= boleto) |
| Categorias do Cartão / disponível | R$ 4.312,25 / R$ 337,75 | iguais |

## 5. Visa (Caixa) 11/2026: a mesma falha das parcelas

A conferência do Visa pedida no contrato comparou o PDF real (`Fatura Outubro.pdf`, vencimento 05/11/2026, total R$ 3.928,91) com a produção. Na importação de 30/10, também não foram gravadas:
- **11 parcelas** (R$ 1.603,19): Fraga Festas 2/5, 2/3 e 2/3, Appgas 2/2, Multiartes 2/8, Sabesp 2/4, Wil Imports 2/3, BBF Store 2/4, Mirak 2/4, Brasil Paral 1/12 e Anuidade 11/12. O leitor da Caixa já as reconhece ("02 DE 05").
- **NETFLIX.COM, R$ 59,90 (29/09):** a tela de então a reteve como "possível recorrência".
- **3 créditos de R$ 0,01** ("AJUSTE CREDITO PARC. LOJISTAA").

| | Hoje | Depois (ensaio) |
|---|---|---|
| Compras executadas | R$ 2.265,85 | R$ 3.928,94 |
| Créditos | — | R$ 0,03 |
| **Valor a pagar** | R$ 2.265,85 | **R$ 3.928,91** (= PDF) |

**A Netflix muda de figura.**
- **Duas cobranças na fatura:**
  - NETFLIX.COM, R$ 59,90: confirma a previsão 580 exatamente (previsto e executado R$ 59,90);
  - NETFLIX ENTRETENIMENTO, R$ 44,90 (compra 606): continua compra comum, sem conciliação sugerida.
- **Consequência:** a conciliação planejada (580 + 606, −R$ 15,00) não deve ser feita. É provável que os R$ 44,90 sejam outra assinatura, ou outro plano, da Netflix.

## 6. Testes

- **`tests/test_supabase_cartao_nubank_creditos.py`** (17):
  - prévia sem gravar (estorno, IOF, ajuste, pagamento);
  - crédito novo abatendo o valor a pagar em todas as leituras, sem mexer na Categoria do Cartão nem no banco;
  - crédito na lista da fatura sem ações;
  - Dashboard, pagamento líquido e estorno do pagamento;
  - estorno integral e valor estornável;
  - IOF pelo valor e pelo nome;
  - crédito sem compra;
  - mais de uma candidata (escolha, sem vínculo, escolha inválida);
  - crédito já importado e reimportação integral;
  - complementar;
  - repetidos legítimos;
  - duas confirmações simultâneas;
  - falha transacional (fatura consolidada: nada gravado);
  - fatura paga preservada, com o crédito na próxima aberta;
  - compra original bloqueada;
  - permissões e RLS;
  - reversão recusada com crédito, e reaplicação.
- **`tests/test_gerador_migration_cartao_nubank_creditos.py`** (2).
- **Ajustados à regra nova**:
  - `tests/test_supabase_importacao_cartao.py`: estorno e ajuste passam a abater a fatura; o pagamento recebido continua fora;
  - `tests/test_supabase_recorrencia_cartao.py`: a análise vigente passa a ser a da 1212;
  - leitores, em `web/tests/unit/importacao-csv.test.mjs` e `importacao-pdf.test.mjs`: o crédito não é retirado no navegador.
- **`web/tests/unit/importar-creditos.test.mjs`** (5), com o `importar_cartao.js` real:
  - crédito na confirmação;
  - escolha da compra;
  - pagamento retirado com o motivo;
  - linha do Flask como antes;
  - crédito repetido mantido.
- **`web/tests/e2e/importar_creditos.spec.mjs`** (1), pela tela, com CSV no formato Nubank:
  - estorno com duas candidatas escolhido;
  - IOF vinculado, ajuste, pagamento fora;
  - confirmação;
  - Cartões (resumo e lista);
  - bloco "Créditos e Ajustes" e executado líquido em Despesas;
  - reimportação sem nada novo.
- **Regressão:**
  - Python por impacto: 1714 aprovados, 7 pulados; a única falha é a i3, dívida conhecida de `regularizar_historico`;
  - unitários 54/54;
  - E2E 118/119. A falha foi `contratos_pagamento` (estorno de parcela de contrato, fora deste pacote). Sozinho, o teste passou nas duas vezes em que rodou de novo. É intermitente: depois do primeiro estorno, o último diálogo já diz "Pagamento estornado com sucesso.", e a espera do segundo pode passar antes do fim.

## 7. Pendências

1. **Publicação conjunta:** 1211 + 1212, push e deploy, com autorização.
2. **Regularização das faturas reais de 11/2026**, depois da publicação e com autorização. Pela tela, reimportando os mesmos arquivos e com retrato só de leitura antes e depois. Nenhuma compra existente é alterada; pagamentos, movimentos e saldos ficam como estão.

   | Cartão e arquivo | O que a reimportação grava | O que o titular decide | Valor a pagar |
   |---|---|---|---|
   | Black, `Nubank_2026-11-05.csv` | 12 parcelas e 4 créditos | a Categoria da despesa de cada parcela e a compra original do estorno Apple (ou "Sem compra vinculada") | R$ 9.599,80 |
   | Visa, `Fatura Outubro.pdf` | 11 parcelas, a Netflix R$ 59,90 como despesa fixa e os 3 ajustes de R$ 0,01 | a Categoria de cada parcela; "Manter" nos dois ajustes repetidos | R$ 3.928,91 |
3. **Netflix:** a conciliação 580 + 606 não deve ser feita (seção 5). A compra 606 (R$ 44,90) fica como compra comum, ou vira outra recorrência, a critério do titular.
4. **Plano NuCel:** a cobrança de R$ 70 (compra 652), lançada como compra comum, e a previsão "Plano NullCel" de 11/2026 continuam separadas. Decisão do titular.
5. **Sem função para desfazer um crédito importado por engano.** Hoje a reversão é só por suporte. Uma função oficial de estorno do crédito fica como pacote futuro.
6. **Estorno e compra no mesmo arquivo:** o estorno só se vincula a uma compra que já está gravada. Na primeira importação de um arquivo com os dois, o crédito entra sem compra vinculada (abate do mesmo jeito).
7. **Apelido da Apple One:** segue com autorização própria.
8. **Teste E2E intermitente** `contratos_pagamento` (espera do diálogo do segundo estorno): corrigir num pacote de testes.
