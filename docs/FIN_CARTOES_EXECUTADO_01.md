# FIN-CARTOES-EXECUTADO-01 — executado consolidado da fatura do cartão

**Situação:** publicado em 11/11/2026, depois da 1224 (push até `feca20e`, migration `20261225090000` = 65, deploy `a82961cc`).
**Testes:** nível N4 (integridade financeira).

## 1. Diagnóstico (11/11/2026, somente leitura)

**Exemplo:** o Visa de 12/2026 (fatura 2661) tem Netflix 59,90, Claude 109,90, Apple One 59,90 e ChatGPT 99,90 = **R$ 329,60**. São despesas fixas do cartão, ainda previstas e sem cobrança.

| Valor exibido | Antes | Esperado |
|---|---|---|
| Executado | R$ 0,00 | R$ 329,60 |
| Previsto | R$ 729,60 (329,60 + 400,00 do limite de Assinaturas) | R$ 729,60 |

**Causa:** a função `valor_executado_compra`, do FIN-CARTAO-PREVISTO-EXECUTADO-01, dava 0 às situações `PREVISTA` e `NAO_COBRADA`. As parcelas já entravam pelo valor. Essa função alimenta todas as leituras da fatura: `executado_fatura`, `contas_do_mes`, `faturas_do_mes`, `fatura_por_categoria`, `fatura_por_cartao`, `compras_da_fatura`, `lancamentos_fatura_por_categoria`, `recalcular_fatura`, `dados_pagamento_fatura`, `pagar_fatura`, `previa_limpeza_importacoes`, `custos_veiculos_tela` e o Dashboard.

**Despesas e Dashboard divergiam em 12/2026:**

| Fatura | Despesas | Dashboard |
|---|---|---|
| Master Card Black | R$ 4.973,47 | R$ 4.450,00 |
| Visa | R$ 729,60 | R$ 400,00 |
| **Total** | **R$ 5.703,07** | **R$ 4.850,00** |

O Dashboard usava “consolidado → executado → planejado gravado” e caía no planejado, que estava desatualizado.

**Conciliação existente (sem duplicar):** a cobrança importada reconhecida como a recorrência (`realizar_ocorrencia_recorrencia`) troca o valor no **próprio lançamento previsto**. O valor previsto original fica em `ocorrencia_recorrencia_cartao`.

**Pagamento:** um gatilho (`previsoes_no_pagamento_da_fatura`) marcava como `NAO_COBRADA` toda previsão ainda sem cobrança no momento do pagamento. A cobrança que chegasse depois entrava sozinha na fatura seguinte. Em produção existem 7 marcas, todas de 11/2026.

## 2. Regra

- **Executado consolidado** = compras lançadas ou importadas + parcelas da fatura + despesas fixas (previstas ou cobradas) − créditos. A recorrência registrada como não cobrada fica fora. O orçamento da Categoria do Cartão **não** é executado.
- **Previsto da fatura aberta** = executado + o que falta dos limites das Categorias do Cartão. A fixa prevista não é somada duas vezes.
- **Saldo da categoria** = limite − compras da categoria. As fixas e as parcelas continuam sem consumir o limite (regra do FIN-CARTAO-DESPESAS-FIXAS-01).
- **Compromisso consolidado × cobrança efetiva** (complemento do titular):
  - o executado consolidado é o valor **sugerido** no pagamento, identificado como tal e com a parte de fixas previstas;
  - o valor efetivamente cobrado pode ser outro, com a diferença classificada e justificada, registrada em `pagamento_fatura`;
  - nenhuma recorrência é marcada como não cobrada automaticamente;
  - não há pagamento, estorno, cobrança ou mudança de competência automáticos;
  - a cobrança que chega depois do pagamento pede **revisão** na importação, em vez de entrar de novo na fatura seguinte;
  - a conciliação posterior continua possível.
- **Faturas pagas não mudam:** a recorrência de fatura paga já entrava pelo valor. As 7 marcas existentes continuam valendo, e o estorno do pagamento as desfaz.

## 3. Solução (migration `20261225090000`)

**Função nova:** `previsto_fatura(fatura)`, interna. Devolve o valor da fatura exatamente como em Despesas: paga = executado; aberta = executado + o que falta dos limites.

| Função substituída | Mudança |
|---|---|
| `valor_executado_compra` | só `NAO_COBRADA` vale 0 |
| `executado_fatura`, `recalcular_fatura` | só o comentário da regra |
| `contas_do_mes`, `faturas_do_mes` | o previsto da fatura aberta deixa de somar a previsão pendente, que já está no executado |
| `fatura_por_categoria` | o aviso das fixas passa a dizer “já no executado; a cobrança importada substitui o valor previsto” |
| `previsoes_no_pagamento_da_fatura` | o pagamento não grava mais a marca de não cobrada; o estorno continua desfazendo as marcas antigas |
| `dados_pagamento_fatura` | informa `previsto_sem_cobranca`, a parte prevista do valor sugerido |
| `dashboard_resumo_tela` (texto da 1224) | “Faturas em aberto” e “Próximos vencimentos” usam `previsto_fatura` |

**Importação:** `analisar_importacao_cartao` não mudou. Sem a marca do pagamento, a cobrança tardia cai no ramo existente “a previsão está em fatura paga”, que pede revisão.

**Tela** ([despesas-adaptacoes.js](../web/src/js/despesas-adaptacoes.js), [despesas-adaptador.js](../web/src/js/despesas-adaptador.js)):
- No pagamento da fatura, o cartão de valores mostra “Executado consolidado”, e a opção padrão diz “Executado consolidado (valor sugerido)”.
- Uma nota informa a parte de fixas previstas sem cobrança e como pagar outro valor.
- Na fatura, a classificação “ajuste” aparece como “Valor cobrado pelo banco diferente do consolidado”.
- O quadro da fatura é refeito a cada abertura; antes, ficava com os valores da primeira fatura aberta.
- Rota nova do adaptador: `GET /api/despesas/:id/composicao-fatura`.

**Reversão** ([supabase/reversao/20261225090000_cartoes_executado_anterior.sql](../supabase/reversao/20261225090000_cartoes_executado_anterior.sql)): devolve as funções do cartão ao texto publicado e o Dashboard ao texto da 1224, e remove `previsto_fatura`. Nenhum dado muda.

## 4. Testes por impacto (N4)

| Bateria | Resultado |
|---|---|
| Nova: `tests/test_supabase_cartoes_executado.py`. Cobre: Visa só com fixas, parcelas + compras + fixas uma vez, Despesas = faturas do mês = Dashboard (inclusive próximos vencimentos), cobrança com valor diferente, não cobrada fora, valor sugerido com a parte prevista, **fixa prevista ainda não cobrada pelo banco**, estorno de marca antiga, segurança, reversão | 10/10 |
| Cartões atualizados para a regra nova: `cartao_previsto_executado`, `cartao_despesas_fixas`, `cartao_importacao_fixas`, `nubank_creditos`, `nubank_parceladas`, `fatura_unica` (16 testes ajustados, com o motivo no próprio teste) | 126/126 |
| Regressão de banco pelas funções alteradas (25 arquivos: cartões, contas do mês, Dashboard, despesas, lote, mobilidade, recorrências, P22, movimentações, documentos, guardas, perfis, receitas, cadeia de reversões i7), com PostgREST | 754/754 (3 testes de `cartoes` e `mobilidade_integridade` ajustados à regra nova) |
| Unitários web | 92/92 |
| E2E novo: `web/tests/e2e/fatura_executado.spec.mjs` (o nome o põe depois de `contas.spec`; limpa recorrências, pagamento e cartão) | 1/1 |
| E2E de regressão (18 specs: cartões, contas, Dashboard, despesas, lote, fatura, importações, mobilidade, pendência, recorrência, receitas, lançamentos) | 67/68: a falha é anterior e alheia, ver seção 6 |

## 5. Ensaio em cópia fiel (11/11/2026)

Script `scratchpad/cx01/ensaio_1225.py`. Cópia da produção em PostgreSQL local descartável; a produção só foi lida. A 1224 foi aplicada antes da 1225.

| Conferência | Resultado |
|---|---|
| Cópia | idêntica à produção (63 migrations) |
| Funções substituídas antes da 1225 | iguais ao texto da reversão (as 9) |
| Migration | nenhum dado alterado; 1 função nova (`previsto_fatura`), 9 alteradas, nenhuma removida |
| Faturas pagas de 11/2026 | idênticas (Master 9.599,80; Visa 3.928,91) |
| Previsto das faturas abertas (12/2026 a 04/2027) | idêntico em todas |
| **Visa 12/2026** | previsto **729,60**, executado 0,00 → **329,60** |
| Master Black 12/2026 | previsto 5.613,31 igual; executado 1.202,15 → 1.525,62 (+323,47: Plano NullCel, SUPABASE SINGAPORE, CloudFlare previstos) |
| Dashboard × Despesas | iguais em todos os meses; 12/2026: 1.602,15 → 6.342,91 = soma das faturas abertas em Despesas |
| Marcas de não cobrada | as 7 existentes ficam (nenhuma criada ou removida) |
| Segurança | nenhuma função definer sem `search_path`; nenhuma para anon; `previsto_fatura` sem acesso de authenticated; permissões das leituras mantidas |
| Reversão e reaplicação | funções e faturas iguais ao antes; reaplicação igual à primeira; nenhum dado alterado |

## 6. Testes ajustados à regra nova

Todos trocam só o valor esperado do executado, ou o comportamento de pagamento que o titular decidiu mudar. As conferências de integridade ficaram:
- soma dos grupos = total (“nada perdido nem duplicado”);
- previsto inalterado;
- limite da categoria intacto;
- uma ocorrência por cobrança;
- reversões devolvendo os registros.

Cada valor novo está decomposto no próprio teste.

| Arquivo | Teste | Antes | Depois |
|---|---|---|---|
| cartao_previsto_executado | previsão sem cobrança | executado 40 (previsão fora) | 99,90 (40 + 59,90 prevista); previsto 559,90 igual; `previsto_sem_cobranca` 59,90; Dashboard = Despesas; a importação não soma |
| | recorrência futura | executado de junho 0 | 59,90 |
| | compra não reconhecida | 99,90 | 219,70: compra comum uma vez + 2 previsões até a conciliação (risco documentado) |
| | conciliação e reversão | 44,90 antes/depois | 104,80 antes (compra comum + previsão), 44,90 conciliado, 104,80 revertido |
| | fatura fechada | 40 | 99,90 |
| | pagamento | pagava 40 e marcava não cobrada; estorno devolvia | paga 99,90; **nenhuma marca criada**; estorno volta à prevista |
| | (novo) banco cobra menos | — | paga 40 com ajuste justificado; nada vira não cobrada; 1 movimento; compras intactas |
| | cobrança depois do pagamento | entrava em junho | **pede revisão**; nada em dobro |
| | pagamento sem compra real | recusado (executado 0) | fatura só com fixa pode ser paga (59,90 sugerido) |
| | reversão da 1209 | recusada pela marca do pagamento | o pagamento não cria marca (conferido) |
| cartao_despesas_fixas | fatura por categoria | fixas 0; total 150 | fixas 45,90; total 195,90; soma = total |
| | previsto da lista | executado 150; previsto 655,90 | 195,90; previsto 655,90 igual |
| | importação realiza a previsão | 44,90 | 314,60 (44,90 + 269,70 das outras três) |
| | conciliação Netflix | 44,90 antes/depois da reversão | 104,80 antes e depois da reversão; 44,90 conciliado |
| cartao_importacao_fixas | tratar como compra comum | 44,90 | 374,50 (escolha do usuário; previsão até conciliar) |
| | compra já lançada | 44,90 antes | 104,80 antes; 44,90 depois |
| | reimportação | 81,90 | 351,60 |
| | duas cobranças do mesmo serviço | 75,80 | 345,50 |
| cartoes | recorrência convive com a compra | 15,00 | 54,90 (15 + 39,90 prevista) |
| | compra concorrente com a geração | 7,50 | 47,40 |
| mobilidade_integridade | custo novo no cartão | total da fatura 0 | 275 (combustível previsto no executado; pendente 275 igual) |
| e2e fatura_agrupamento | totais do detalhe | 410 / 350 | 410 / 410 |

**Falha anterior e alheia:** `web/tests/e2e/recorrencia.spec.mjs`, teste “excluir só esta e esta e as futuras”. Ele ainda espera o alerta anterior à P22 (`d082378`, 09/11): “esta e as futuras” agora abre a prévia da interrupção. O arquivo não muda desde `646912c` (30/10). Corrigir o teste fica como pendência própria.

## 7. Riscos residuais

- **Cobrança importada não reconhecida** como a recorrência (descrição diferente, sem apelido) aparece junto da previsão no executado até ser conciliada. A importação já sinaliza as pendências de recorrência, e conciliar resolve.
- **Fixa que o banco não cobrou:** continua no executado consolidado da fatura paga. A diferença fica registrada no pagamento, com classificação e justificativa. Se for preciso tirá-la do consolidado, isso fica para uma operação própria de “marcar como não cobrada”, que não existe na tela hoje.
- **Ordem de publicação:** 1224 → 1225. A P23 (`f844795`, migration 1223) altera `contas_do_mes` e `dashboard_resumo_tela`: precisa ser regenerada sobre o texto vigente e renumerada antes de publicar.

## 8. Publicação (11/11/2026)

Publicada logo depois da 1224, por autorização expressa do titular. As etapas comuns estão em `docs/FIN_RECEITAS_SALDO_01.md`: pré-condições, push `080e26b..feca20e`, deploy `a82961cc` e auditoria.

- **Migration 1225:** APLICADA E CONFERIDA (65 migrations).
  - As 9 funções eram iguais ao texto da reversão.
  - 1 função nova e 9 substituídas, com os 10 corpos iguais ao arquivo.
  - Nenhum acesso novo ou perdido; nenhum dado alterado; segurança sem bloqueios.

**Homologação de leitura (como o titular, nada gravado):**

| Critério | Resultado |
|---|---|
| Visa 12/2026 | previsto **R$ 729,60**, executado **R$ 329,60**; por categoria: fixas 329,60, parceladas 0, Assinaturas com o limite de 400 inteiro (o orçamento não é executado) |
| Master Black 12/2026 | previsto R$ 5.613,31; executado R$ 1.525,62, sendo R$ 323,47 de fixas previstas |
| Despesas × Dashboard | faturas em aberto iguais: 12/2026 R$ 6.342,91; 01/2027 R$ 5.860,10; 11/2026 R$ 0,00 |
| Faturas pagas 11/2026 | Master R$ 9.599,80 e Visa R$ 3.928,91, como antes; pagamento com o executado gravado |
| Conciliação | nenhuma recorrência com mais de um lançamento na mesma competência |
| Pagamento | sugerido = executado consolidado; parte prevista informada (Visa 329,60; Master 323,47) |
| Marcas de não cobrada | as 7 de 11/2026, vigentes e intactas |

**Exceção registrada (E2E):** `web/tests/e2e/recorrencia.spec.mjs`, “excluir só esta e esta e as futuras”. O teste espera o alerta anterior à P22 (`d082378`), mas desde então “esta e as futuras” abre a prévia da interrupção. O arquivo não muda desde `646912c` (30/10). A falha é anterior e alheia às 1224/1225. O teste continua no repositório, sem ser ocultado; corrigi-lo é uma pendência própria.
