# FIN-CARTAO-CREDITOS-01 — Natureza do lançamento na importação de cartão (P18)

**Situação (07/11/2026): publicado (`39824b3`, deploy `b66d9555`).** Sem migration; as funções do banco não mudaram. As duas pendências que dependem de migration (seção 6) seguem no FIN-CARTAO-CREDITOS-02, e a reconstrução das faturas de 11/2026 fica bloqueada até essa correção.

## 1. Causa raiz

A prévia tinha três momentos de análise no banco, com dados diferentes para a mesma linha:

| Momento | Quem chama | O que o banco recebia | Resultado |
|---|---|---|---|
| Arquivo | `analisarArquivo` | todas as linhas, com o tipo | correto |
| Botão de prévia | `montarPayloadReconhecimento` → `/reconhecer` | só as linhas ativas, **sem o tipo** | crédito tratado como débito positivo |
| Confirmação | `montarPayloadImportacao` → `/previsualizar` e `/processar` | só as linhas a gravar, com o tipo | crédito correto |

Sem o tipo, `linhaParaBanco` assume `debito`. A devolução de IOF de R$ 0,99 parecia a cobrança de IOF de R$ 0,99 já lançada: o banco respondia `conciliado`, e a tela retirava a linha como "Já existe na fatura".

Comprovado por execução em cluster descartável, no código de produção:

- **Crédito:** a tela dizia "Já existe na fatura", mas `linhaImportavel` continuava verdadeira. A confirmação enviava o tipo certo e o crédito abatia: a tela afirmava o contrário do que seria gravado. O abatimento não se perdia neste fluxo.
- **Intermitência do E2E:** o teste conferia o texto da linha enquanto a resposta do `/reconhecer` não chegava. Passava quando ganhava essa corrida e falhava quando perdia. A "análise posterior que corrige" é a da confirmação, que sempre levou o tipo.
- **Débito (mesmo mecanismo):** sem as linhas retiradas, a análise parcial casava a compra lançada com outra linha de mesmo valor. Uma compra nova saía como "Já existe" e a linha original perdia o motivo real ("Retirado pelo usuário").
- **Mapeamento manual:** `interpretarLinhaPorPerfil` aplicava `Math.abs` e não definia o tipo. Um crédito de −40,00 foi gravado como compra de +40,00 (fatura 140,00 em vez de 60,00). Latente: o botão "Validar layout" fica em contêiner oculto, na página nova e no template do Flask, e a tela não alcança esse caminho.
- **Somatório:** "Valor em processamento" somava créditos como despesa.

Dados históricos: leitura em produção (06/11/2026) sem achados. `credito_fatura` vazia, nenhum valor negativo e nenhuma compra com aparência de crédito. Não há o que regularizar.

## 2. Fluxo da natureza

| Etapa | Onde | Regra |
|---|---|---|
| Arquivo | `importacao-csv.js`, `importacao-pdf.js`, `importacao-xlsx.js` | sinal, coluna Crédito/Débito da Caixa ou sufixo `C` do PDF definem `tipo_movimento`; o valor segue positivo |
| Análise | `analisar_importacao_cartao` | valor negativo é sempre crédito; depois vale o tipo informado. Crédito tem chave e tabela próprias |
| Prévia | `importar_cartao.js` | `linhaCreditoNova`, sinal na exibição, abatimento nas somas |
| Confirmação | `importar_fatura_cartao` | refaz a análise sob trava; crédito vai para `credito_fatura`, compra para `lancamento_agregado` |
| Fatura | `recalcular_fatura`, `executado_fatura` | valor a pagar = compras executadas − créditos |

Convenção preservada: `credito_fatura.valor` é positivo e a fatura subtrai. Nenhum sinal foi invertido.

## 3. Solução (só `frontend/static/js/importar_cartao.js`)

| Função | Alteração |
|---|---|
| `camposPreviaLinha` (nova) | campos que o banco usa para julgar a linha, em um lugar só; análise e confirmação não divergem mais |
| `montarPayloadReconhecimento` | usa `camposPreviaLinha`: tipo, cartão de origem, parcela e decisões da prévia |
| `reconhecimentoSeparadoNecessario` (nova), `previsualizarImportacao` | linha já classificada pelo banco não passa por segundo reconhecimento; mapeamento manual e Flask continuam como antes |
| `montarPayloadImportacao` | a compra casada pelo valor vai junto, ignorada e primeiro, para a confirmação repetir a atribuição da análise |
| `reconhecimentoLinha` | crédito nunca recebe reconhecimento de compra |
| `interpretarLinhaPorPerfil` | preserva a natureza: crédito fica retirado, nunca vira compra. Regra "despesas são negativas" mantém o débito |
| `valorFinanceiroLinha` (nova), `formatarValorLinha`, `calcularKpisImportacao`, `calcularResumoLocal` | crédito exibido com `−` e abatido das somas |

## 4. Testes

`tests/test_supabase_cartao_creditos_importacao.py` (contrato do banco), `web/tests/unit/importar-creditos.test.mjs` e `web/tests/e2e/importar_creditos.spec.mjs`.

| # | Cenário do contrato | Cobertura |
|---|---|---|
| 1 | Compra comum | pytest |
| 2 | Crédito | pytest, E2E |
| 3 | Devolução de IOF | pytest, E2E |
| 4 | Estorno integral | pytest, E2E |
| 5 | Estorno parcial | pytest, E2E |
| 6 | Crédito e débito de mesmo valor e competência | pytest, E2E |
| 7 | Reimportação de crédito | pytest, E2E |
| 8 | Reimportação de compra | pytest, E2E |
| 9 | Importação conjunta | pytest, E2E |
| 10 | Confirmação sem segunda análise | unitário, E2E |
| 11 | Totais da fatura | pytest, E2E |
| 12 | Repetições do cenário intermitente | E2E repetido |

Os testes novos falham no código anterior (6 unitários e 2 E2E) e passam com a correção.

Resultados (06/11/2026): pytest por impacto 258 aprovados e 2 `xfail` esperados; unitários web 77/77; E2E completo 124/124 duas vezes, sem novas tentativas; `importar_creditos.spec.mjs` 30/30 em clusters novos. A repetição com `--repeat-each` no mesmo banco não serve como medida para o primeiro teste: as faturas de execuções anteriores têm o mesmo nome e o cartão fica ativo quando a execução para antes da limpeza.

## 5. Integridade

Nenhum arquivo de `supabase/` mudou. Os mesmos arquivos fictícios (Nubank e Caixa), importados pela tela no código anterior e no novo em clusters descartáveis, deram resultado idêntico: compras, créditos, faturas, categorias, despesas do mês, cadastro de contas bancárias, quantidades e identificadores. Movimentos e saldos bancários: a importação não os altera (md5 de `movimento_financeiro` e `conta_bancaria` em `test_credito_novo_abate_o_valor_a_pagar_uma_vez`).

## 6. Pendências

**Dependiam de migration.** Corrigidas no FIN-CARTAO-CREDITOS-02 (migration `20261216090000`, `docs/FIN_CARTAO_CREDITOS_02.md`); os `xfail` viraram testes.

1. **Mesmo crédito por outro tipo de arquivo abate duas vezes.** A chave do crédito usa o texto, e a trava `OUTRA_FONTE` só olha compras novas. Crédito importado de CSV e reimportado de PDF com outro texto: 100,00 − 20,00 − 20,00 = 60,00.
2. **Estorno com "pagamento" no texto não abate.** `pagamento_fatura` é testado antes do estorno: `Estorno de "Pagamento Facil Loja"` fica retirado como pagamento recebido.

A migration precisa de versão posterior a `20261215090000` (MVP-MOB-01, não publicada) e substitui `analisar_importacao_cartao` e `importar_fatura_cartao`.

**Outras.**

3. "Validar layout" oculto: o mapeamento manual não é alcançável pela tela. Ao expô-lo, o crédito retirado precisa de caminho para abater a fatura.
4. Naturezas gravadas: `ESTORNO`, `IOF_DEVOLVIDO` e `AJUSTE`. "Devolução de valores" entra como `ESTORNO` e "crédito recebido" como `AJUSTE`, com o mesmo efeito financeiro. Separá-las exige migration (restrição `check`).
5. O botão "Criar despesas (N)" conta créditos no N. Texto mantido para não alterar a tela.
