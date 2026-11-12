# FIN-MVP-SANEAMENTO-FINAL-01: consórcios legados, receitas históricas e pendências remanescentes

**Situação (11/11/2026):** diagnóstico, correção local, roteiro de saneamento e ensaio em cópia fiel concluídos (ramo `saneamento-final-01`). A execução em produção depende da aprovação do manifesto (seção 7) e das 2 decisões da seção 8.
**Base:** produção em `cbd6db7`, 67 migrations (última 1227). Nenhuma migration nova.
**Testes:** por impacto (N3 na tela de Receitas; N4 no saneamento, pelo ensaio em cópia fiel).

## 1. Contratos de consórcio 13 e 14

| Conferência | Contrato 13 | Contrato 14 |
|---|---|---|
| Cadastro | "Consórcio", obs. "Diego 1", perfil 1, **ativo** | "Consórcio", obs. "Diego 2", perfil 1, **ativo** |
| Dados | 10 parcelas desde 01/2026, R$ 500,00 + 10, contemplação 01/2026, prêmio R$ 5.000,00 | idem |
| Parcelas (contas) | nenhuma | nenhuma |
| Pagamentos, estornos, movimentos | nenhum | nenhum |
| Receitas vinculadas (`consorcio_id=13/14`) | nenhuma | nenhuma |
| Restrições de integridade | nenhuma tabela referencia `contrato_consorcio` | idem |
| Auditoria | sem registros próprios (criados pelo Flask em 07/05/2026) | idem |

**Conclusão:** são cadastros legados, sem nenhum vínculo financeiro. Proposta: **exclusão** das 2 linhas.
- Os contratos válidos 18 e 19 não são tocados.
- Depois, só o 18 e o 19 aparecem nos consórcios ativos (conferido no ensaio).

**Fora do escopo autorizado, só registrado:**
- Os legados inativos 11, 12, 15, 16 e 17 já não aparecem na operação.
- Os 67 itens de parcela `Consórcio - Parcela i/n` e `Consórcio Entre Amigos - Parcela i/9` (ids 389–455) estão inativos, sem contas e sem nenhuma referência. Não têm efeito financeiro.
- Os itens não são atribuíveis a um contrato específico, porque o prefixo "Consórcio" é comum a 13, 14, 11, 12, 16 e 17. Por isso ficam como estão; excluí-los seria outra decisão.

## 2. Inventário das receitas até 10/2026

O perfil 1 (Pessoal) é o único com receitas. Há 9 recebimentos (`receita_realizada`) e 12 previsões (`receita_orcamento`) com competência até 10/2026.

### 2.1 Recebimentos

| ID | Descrição | Competência | Valor | Situação | Origem | Conta | Movimento | Tratamento |
|---|---|---|---|---|---|---|---|---|
| 38 | Salário CBMGO | 05/2026 | 18.471,28 | recebida | recorrência (previsão 209) | Caixa | 150 crédito | **manter** |
| 39 | Cargo em Comissão | 05/2026 | 4.453,70 | recebida | recorrência (previsão 197) | Caixa | 151 crédito | **manter** |
| 45 | Cargo em Comissão | 08/2026 | 4.453,70 | recebida | recorrência (previsão 200) | Caixa | 169 crédito | **manter** |
| 46 | Salário CBMGO | 08/2026 | 18.471,28 | recebida | recorrência (previsão 212) | Caixa | 170 crédito | **manter** |
| 40 | Consórcio – contemplação (ID 3) | 01/2026 | 5.000,00 | recebida | legado (contrato 3 inexistente) | Caixa | 152 crédito (11/05/2026) | **excluir** (seção 3) |
| 41 | Consórcio – contemplação (ID 4) | 01/2026 | 5.000,00 | recebida | legado (contrato 4 inexistente) | Nubank | 153 crédito | **excluir** (seção 3) |
| 42 | Consórcio – contemplação (ID 3) | 01/2026 | 5.000,00 | recebida | legado; **duplica a 40** | Caixa | 154 crédito | **excluir** (seção 3) |
| 43 | Consórcio – contemplação (ID 4) | 01/2026 | 5.000,00 | recebida | legado; **duplica a 41** | Nubank | 155 crédito | **excluir** (seção 3) |
| 44 | Consórcio – contemplação (ID 7) | 06/2026 | 5.220,00 | a confirmar (sem conta) | legado (contrato 7 inexistente; mesmos valores dos contratos Rejane 16/17, inativos) | — | — | **excluir** |

Nenhum dos 9 tem estorno. Os créditos 152–155 não têm estorno nem pagamento vinculado.

### 2.2 Previsões

| ID | Fonte | Competência | Previsto | Recebido | Situação | Tratamento |
|---|---|---|---|---|---|---|
| 209 / 197 | Salário / Cargo | 05/2026 | 18.471,28 / 4.453,70 | igual | recebida | manter |
| 212 / 200 | Salário / Cargo | 08/2026 | 18.471,28 / 4.453,70 | igual | recebida | manter |
| 198 / 210 / 199 | Cargo 06, Salário 06, Cargo 07/2026 | 06–07/2026 | 0,00 ("Removido pelo usuário") | — | removida pelo titular | manter (marca que impede o valor-base de reaparecer) |
| **211** | Salário CBMGO | 07/2026 | 18.471,28 | 0 | **pendente** | **decisão** (seção 8) |
| **201 / 213** | Cargo / Salário | 09/2026 | 4.453,70 / 18.471,28 | 0 | **pendente** | **decisão** |
| **202 / 214** | Cargo / Salário | 10/2026 | 4.453,70 / 18.471,28 | 0 | **pendente** | **decisão** |

### 2.3 Consolidado por situação

| Situação | Quantidade | Valor |
|---|---|---|
| Recebidas legítimas (manter) | 4 recebimentos | 45.849,96 |
| Recebidas legadas com crédito (40–43) | 4 recebimentos | 20.000,00 |
| A confirmar legada (44) | 1 | 5.220,00 |
| Previsões pendentes sem recebimento | 5 | 64.321,24 |
| Previsões removidas (valor 0) | 3 | 0,00 |

De 11/2026 em diante nada é tocado, incluindo as contemplações de 12/2026 (50 e 51, R$ 5.500,00 cada) dos contratos 18 e 19.

## 3. Receitas legadas 40–43 (incluindo a 42 e a 43)

**Elas têm crédito bancário.** Os movimentos 152–155, de R$ 5.000,00 cada, foram lançados em 11/05/2026: R$ 10.000,00 na Caixa e R$ 10.000,00 no Nubank. O contrato 18/19 não foi alterado para compensar nada.

**Os créditos já foram absorvidos pela conciliação de 11/11/2026.**
- O saldo é `saldo_inicial` + todos os movimentos.
- Os ajustes "Ajuste por conciliação" 207 (Caixa, débito de 67.788,55) e 208 (Nubank, débito de 12.376,41) levaram os saldos aos valores reais.
- Hoje os saldos são Caixa 600,92 e Nubank 93,07.
- Apagar só os créditos deixaria cada conta R$ 10.000,00 abaixo do real.

**Opções:**

| Opção | O que faz | Saldos |
|---|---|---|
| **B (recomendada)** | exclui as 4 receitas e os 4 créditos; reduz os ajustes 207 (→ 57.788,55) e 208 (→ 2.376,41), que só existiam nesse tamanho para cancelar os créditos fictícios | **idênticos** (600,92 / 93,07) |
| C | exclui receitas e créditos, sem tocar nos ajustes | Caixa −9.399,08 / Nubank −9.906,93; o titular reconcilia |
| manter | nada | idênticos; 01/2026 continua com R$ 20.000,00 de receita fictícia |

## 4. Consolidação de categorias

| Verificação | Resultado |
|---|---|
| Categorias duplicadas (nome normalizado) | nenhuma |
| `categoria_id` órfão (12 tabelas) | nenhum |
| Vínculos inválidos | nenhum |
| Mecanismo de incorporação | operacional: a prévia oficial (`scripts/consolidar_categorias.py previa`, só leitura) diz "executável", hash `ec77b2ae…` |
| Integração (cartões, despesas, recorrências, Mobilidade) | preservada; Mobilidade sem `MOB_REVISAO` (9 sistêmicas) desde a publicação de 02/11 |
| Funções ou telas incompletas | nenhuma |

**Pendência real:** as 4 incorporações aprovadas no FIN-CATEGORIAS-CONSOLIDACAO-01 nunca foram executadas. Elas estavam condicionadas à reconstrução de 11/2026, que foi encerrada sem execução. Impacto atual pela prévia:

| Origem → destino | Referências que mudam |
|---|---|
| 96 Transporte por App → **8 Transporte por Aplicativo** | 1 categoria do cartão (Mobilidade 58), 6 palavras-chave |
| 98 Manutenção de Veículo → **5 Manutenção Veicular** | 1 categoria do cartão, 11 palavras-chave (`pneu` → Pneus 6, `lavajato` → Lavagem 10), 1 recorrência, 4 lançamentos de cartão |
| 4 Revisão → **5 Manutenção Veicular** | nenhuma |
| 99 Assinaturas → **100**, renomeada **Assinaturas** | 1 categoria do cartão (já no destino), 14 palavras-chave (netflix, spotify, disney, prime…), 1 recorrência, 7 lançamentos de cartão |

Nada foi executado. Executar exige autorização própria, pelo procedimento já publicado (`previa` → conferência → `executar --hash … --confirmo "INCORPORAR CATEGORIAS"`). Continua aberta a ambiguidade, anterior a este MVP, de "netflix" e "streaming" entre Assinaturas e Entretenimento.

## 5. Correção local: previsão removida não é pendência

**Defeito herdado do Flask:**
- "Remover previsão" de fonte recorrente grava a previsão com valor 0 ("Removido pelo usuário"), para o valor-base não reaparecer naquele mês.
- Mesmo assim, a tela a mostrava como "Prevista R$ 0,00" e a contava nas **atrasadas**.
- Em produção, isso já acontecia com as previsões 198, 199 e 210.

**Correção** (`web/src/js/receitas-adaptacoes.js`, commit `16179bf`; `js/original` intacto): a previsão com valor 0 e sem recebimento sai da lista do mês e das atrasadas. Ela continua gravada e o valor-base não volta a aparecer.

## 6. Testes e ensaio

| Bateria | Resultado |
|---|---|
| E2E nova `receitas_dispensadas.spec.mjs` (usuário E, fictício) | **falhou antes da correção** (3 atrasadas depois de remover uma); depois, aprovada |
| E2E de Receitas: nova + `receitas_tela`, `receitas_saldo`, `consorcios_p24` | 11/11 |
| Unitários web | 92/92 |
| Banco | sem migration nem função alterada: dispensado |

**Ensaio em cópia fiel** (`scratchpad/san01/ensaio_copia.py`; a produção só foi lida):
- Ressalva: os dados de `ir_comprovante_arquivo` (binários de IR, fora do escopo) ficaram fora da cópia, porque o `pg_dump` caía por SSL nessa tabela.

| Conferência | Resultado |
|---|---|
| Cópia | idêntica à produção |
| Aplicação (B + dispensar) | COMMIT; 18 operações (manifesto); as 86 tabelas fora do escopo idênticas (inclui contas, compras, faturas, pagamentos, recorrências, contratos 18/19, receitas 50/51 e tudo de 11/2026 em diante) |
| Saldos | Caixa 600,92 → 600,92; Nubank 93,07 → 93,07 |
| Integridade referencial | sem violação (exclusões na ordem crédito → receita; nenhuma referência aos contratos) |
| Consórcios ativos | 13, 14, 18, 19 → **18, 19** |
| Idempotência | a segunda execução para na conferência ("contrato 13: 0 linhas") sem gravar |
| Reversão (`reverter(lote)`) | devolve contratos, receitas e créditos com os mesmos ids, ajustes e previsões; todas as tabelas voltam idênticas; em `conta_bancaria` só muda o carimbo `data_atualizacao` do recálculo do saldo (saldos idênticos); o roteiro pode ser aplicado de novo |
| Opção C (simulada, sem gravar) | Caixa 600,92 → −9.399,08; Nubank 93,07 → −9.906,93 |
| Regeneração | 44 e 40–43: os contratos 7, 3 e 4 não existem, então nada as recria; previsões dispensadas: o gerador só cria do mês atual em diante, e a marca de valor 0 impede o valor-base no mês (E2E) |

**Impacto previsto nos indicadores (Dashboard, perfil Pessoal):**

| Mês | Receitas previstas | Receitas recebidas | Saldo final projetado |
|---|---|---|---|
| 01/2026 | 20.000,00 → 0 | 20.000,00 → 0 | 15.675,55 → −4.324,45 |
| 06/2026 | 5.220,00 → 0 | 0 | −7.743,64 → −12.963,64 |
| 07/2026 | 18.471,28 → 0 | 0 | 4.927,00 → −13.544,28 |
| 09/2026 | 22.924,98 → 0 | 0 | 9.109,43 → −13.815,55 |
| 10/2026 | 22.924,98 → 0 | 0 | 11.292,07 → −11.632,91 |
| 11/2026 em diante | sem alteração | sem alteração | sem alteração |

Os saldos projetados de 07, 09 e 10/2026 ficam negativos se as previsões forem dispensadas. O salário desses meses nunca foi registrado como recebido; o dinheiro real está no saldo conciliado em 11/11.

## 7. Manifesto de saneamento (opções recomendadas)

| ID | Tipo | Competência | Valor | Situação atual | Operação | Justificativa | Impacto financeiro |
|---|---|---|---|---|---|---|---|
| 13 | contrato de consórcio | 01/2026 | prêmio 5.000,00 | ativo, sem vínculos | excluir | legado do Flask, não corresponde ao contrato real | nenhum |
| 14 | contrato de consórcio | 01/2026 | prêmio 5.000,00 | ativo, sem vínculos | excluir | idem | nenhum |
| 44 | receita | 06/2026 | 5.220,00 | a confirmar, sem conta | excluir | contemplação de contrato inexistente | −5.220,00 previsto em 06/2026 |
| 40 | receita | 01/2026 | 5.000,00 | recebida (Caixa) | excluir | contemplação de contrato inexistente | −5.000,00 recebido em 01/2026 |
| 41 | receita | 01/2026 | 5.000,00 | recebida (Nubank) | excluir | idem | −5.000,00 |
| 42 | receita | 01/2026 | 5.000,00 | recebida (Caixa) | excluir | idem, duplica a 40 | −5.000,00 |
| 43 | receita | 01/2026 | 5.000,00 | recebida (Nubank) | excluir | idem, duplica a 41 | −5.000,00 |
| 152, 154 | crédito | 11/05/2026 | 2 × 5.000,00 | Caixa | excluir | créditos das receitas 40 e 42 | compensado pelo 207 |
| 153, 155 | crédito | 11/05/2026 | 2 × 5.000,00 | Nubank | excluir | créditos das receitas 41 e 43 | compensado pelo 208 |
| 207 | ajuste de conciliação | 11/11/2026 | 67.788,55 | débito Caixa | valor → 57.788,55 | absorvia os 10.000,00 fictícios | saldo Caixa idêntico |
| 208 | ajuste de conciliação | 11/11/2026 | 12.376,41 | débito Nubank | valor → 2.376,41 | idem | saldo Nubank idêntico |
| 211 | previsão | 07/2026 | 18.471,28 | pendente | dispensar (valor 0) | sem recebimento registrado | −18.471,28 previsto |
| 201, 213 | previsões | 09/2026 | 22.924,98 | pendentes | dispensar | idem | −22.924,98 |
| 202, 214 | previsões | 10/2026 | 22.924,98 | pendentes | dispensar | idem | −22.924,98 |

**Mantidas:**
- Receitas 38, 39, 45, 46 e seus créditos.
- Previsões 197, 209, 200, 212 (recebidas) e 198, 199, 210 (removidas).
- Contratos 18 e 19 e receitas 50 e 51.
- Tudo de 11/2026 em diante.

**Categorias:** nenhuma alteração neste manifesto.

**Auditoria da execução:**
- `operacao_despesa` / `operacao_receita` com a operação `saneamento_final` e as linhas inteiras de antes, num só lote.
- `reverter(lote)` devolve tudo.

## 8. Decisões do titular

1. **Receitas 40–43:** opção B (recomendada), C ou manter (seção 3).
2. **Previsões 211, 201, 213, 202 e 214** (salário e comissão de 07, 09 e 10/2026 sem recebimento registrado):
   - dispensar (recomendada; nenhum crédito é criado);
   - ou manter como pendentes.
   - Registrá-las como recebidas não é feito sem comprovante, e criaria créditos que o saldo conciliado não comporta.
3. **Categorias:** autorizar ou não as 4 incorporações da seção 4.

## 9. Encerramento técnico

**Commits não publicados:**
- `e747613`: documentação final da P24.
- `16179bf`: correção da tela de Receitas.
- O commit da documentação deste MVP.
- Ramos antigos à frente da `main`, **substituídos e que não devem ser publicados**: `despesas-cancelamento-01` (`f844795`, P23 pausada, trocada pela 1226) e `despesas-pagamento-lote-01` (`fa671a2`, `1d7f7fa`, P20 publicada por outro caminho).

**Situação final das pendências:**

| Item | Situação |
|---|---|
| P14, P20, P21, P22, P23, P24 | concluídas |
| MVP-MOB-02, FIN-MVP-LANCAMENTOS-03 | concluídos |
| Reconstrução das faturas de 11/2026 | encerrada por decisão do titular, sem execução |
| Consórcios legados | 13 e 14 sem vínculos; exclusão pronta (manifesto) |
| Receitas históricas | inventário fechado; 1 exclusão sem efeito no saldo (44), 4 com decisão (40–43), 5 previsões com decisão |
| Consolidação de categorias | módulo íntegro; só restam as 4 incorporações aprovadas e não executadas |
| Cancelamento da conta 2501 (P23) | aguarda autorização própria |

## 10. Validação futura: importação de dezembro/2026

O titular decidiu não reconstruir as faturas de 11/2026; as compras de novembro já foram lançadas manualmente. A importação das faturas de 12/2026, na operação normal, valida o processo. Critérios:
- **Duplicidade:** compras de 11/2026 lançadas à mão e repetidas no arquivo de 12/2026 (parcelas, compras na virada) aparecem como "já existente" na prévia, sem segundo lançamento; reimportar o mesmo arquivo não duplica nada.
- **Classificação:** palavras-chave e categoria do cartão sugerem a categoria; nada é gravado sem a confirmação da prévia.
- **Créditos:** estorno/crédito na fatura abate uma vez só (planilha e PDF, P18 e FIN-CARTAO-CREDITOS-02).
- **Recorrências:** as despesas fixas do cartão (assinaturas) casam com a cobrança do mês, sem duplicar o previsto (1225).
- **Parceladas:** a prévia mostra a parcela do mês e as futuras (P14), sem recriar parcelas já existentes.
- **Abastecimentos:** a compra de combustível sugere o abastecimento compatível (FIN-MVP-LANCAMENTOS-03), sem vínculo automático.
- **Conferência final:** o total da fatura importada é igual ao do arquivo, e o executado da fatura e as Despesas do mês ficam coerentes.
