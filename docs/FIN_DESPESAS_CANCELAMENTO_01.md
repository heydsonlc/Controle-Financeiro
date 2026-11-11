# FIN-DESPESAS-CANCELAMENTO-01 (P23): cancelar a obrigação com pagamento estornado

**Situação:** implementada e validada no ramo `despesas-cancelamento-02`, sobre `78b3df2` (já com a 1224 e a 1225). Migration `20261226090000`. A publicação foi autorizada pelo titular, condicionada às verificações abaixo. O cancelamento real da sessão de 03/11/2026 depende de autorização própria.
**Testes:** nível N4 (integridade financeira).

## 1. Problema

**Caso real (Psicóloga, 11/2026):** conta 2501, sessão de 03/11, R$ 250,00.
- Foi paga no lote (movimento 188) e depois estornada integralmente (movimento 193, ligado ao 188).
- Está pendente, mas a consulta não aconteceu.

**Dois bloqueios impediam o cancelamento:**
- No lápis, a tela recusava abrir a despesa: “Esta despesa não pode ser editada. Possui movimento financeiro vinculado.” Assim, não havia acesso à exclusão.
- No banco, `bloqueio_da_despesa` recusa excluir qualquer conta com movimento. Apagar a conta também romperia o histórico, porque `movimento_financeiro.conta_id` não tem cascata e `pagamento_fatura` apagaria em cascata.

**Pausa e retomada:** a primeira versão (`f844795`, migration 1223) foi pausada durante a publicação das 1224 e 1225. Foi retomada sobre o texto publicado delas: `contas_do_mes` e `dashboard_resumo_tela` mudaram, e as demais funções estavam iguais.

## 2. Regra

| Situação financeira | Resultado |
|---|---|
| Pendente, nunca paga | exclusão comum (como antes) |
| Pendente, pagamento integralmente estornado | **cancelamento permitido** |
| Paga (pagamento ativo) | bloqueada: “estorne antes de cancelar” |
| Estorno parcial (valor pago residual) | bloqueada |
| Movimento fora do par pagamento/estorno | bloqueada (não conciliado) |
| Já cancelada | idempotente |
| Outro vínculo (abastecimento, despesa prevista, regularização, parcela histórica, troca de Mobilidade) | bloqueada com o motivo |

**Cancelamento lógico:** reaproveita o estado “preservado fora dos indicadores” que já existia para a conta substituída na Mobilidade.
- A conta passa a `status_pagamento = 'Dispensada'`.
- O pagamento, o estorno e o registro em `pagamento_fatura` ficam intactos.
- Na recorrência, a ocorrência fica `DISPENSADA` com a conta e o motivo, e o gerador não a recria.
- A recorrência continua ativa; as outras ocorrências não mudam.
- **Auditoria:** registro `cancelar_despesa` em `financeiro.operacao_despesa`, com a conta antes, os pagamentos, os estornos e o motivo.

## 3. Solução (migration `20261226090000`)

**Funções novas:**

| Função | Acesso | Papel |
|---|---|---|
| `registrar_dispensa_recorrente` | interna | grava a dispensa da ocorrência; também usada pela exclusão |
| `situacao_cancelamento_despesa` | interna | aplica a matriz da seção 2 |
| `previa_cancelamento_despesa` | authenticated, só leitura | diz se a despesa pode ser cancelada e por quê |
| `cancelar_despesa(perfil, conta, versao)` | authenticated | cancela; trava conta, recorrência e geração, como a exclusão |

**Funções substituídas (só o necessário, a partir do texto publicado):**
- `dispensar_conta_recorrente`: passa a usar o registrador; o comportamento não muda.
- `bloqueio_do_pagamento`: obrigação cancelada não se paga.
- As leituras que já deixavam de fora a conta “Substituida” passam a deixar também a “Dispensada”: `contas_do_mes`, `dashboard_resumo_tela`, `despesas_diretas_tela`, `saidas_lastro`, `pagar_despesas_lote`, `candidatas_abastecimento`, `vincular_abastecimento`, `salvar_lancamento_abastecimento`.
- `ocorrencias_interrupcao` (P22): a prévia de “esta e as futuras” não lista a cancelada.

**Tela:**
- O lápis da despesa estornada abre o formulário só para consulta: aviso, campos e Salvar bloqueados, e o botão “Cancelar obrigação”.
- O botão leva à confirmação: “Esta despesa possui um pagamento anteriormente estornado. O cancelamento encerrará a obrigação pendente, preservando o histórico financeiro.”
- A edição continua recusada no banco.

**Reversão:** devolve o texto publicado das 11 funções e remove as 4 novas. Recusa se já houver obrigação cancelada.

## 4. Testes por impacto (N4)

| Bateria | Resultado |
|---|---|
| Banco, nova: `tests/test_supabase_despesas_cancelamento.py`. Cobre: caso real, auditoria, sem movimento novo, sem recriar, idempotência, versão, nunca paga, pagamento ativo, estorno parcial, pagamento sem estorno, 3 casos de movimento não conciliado, outro vínculo, avulsa, pagamento e lote recusados, Dashboard e despesas diretas, P22, concorrência com pagamento, perfis, permissões, reversão | 22/22 |
| Regressão de banco: 21 arquivos (despesas, lote, P21, reversão do lote, P22, recorrências e categorias, gerador, contas do mês, Dashboard, receitas, cartões, abastecimento, documentos, movimentações, consórcios, cadeia de reversões i7), com PostgREST | 538/538 |
| Unitários web | 92/92 |
| E2E nova: `web/tests/e2e/despesas_cancelamento.spec.mjs` (lápis → formulário bloqueado → Cancelar obrigação → confirmação; 750 → 500; lote só com as 2 restantes; recorrência ativa; saldo igual; sem estorno, o modal de sempre) | 2/2 |
| E2E de regressão: 19 specs | 69 aprovados, 4 falhas e 9 não executados (série interrompida). Ver nota abaixo |

**Nota sobre o E2E de regressão:**
- `recorrencia.spec` (“excluir só esta e esta e as futuras”) é a falha conhecida, anterior à P23: o teste espera o fluxo de antes da P22.
- As outras 3 falhas (`lancamentos_tela`, `recorrencias_inativacao` 1920 e `recorrencias_tela` “cadastrar…”) passaram **isoladamente com a P23: 14/14**.
- Na mesma bateria rodada **sem a P23** (código publicado `78b3df2`), também falharam `recorrencia.spec` e outro teste de `recorrencias_tela` (“semanal”).
- São intermitências de ordem e tempo na geração de meses distantes nos perfis de teste. Nenhuma é atribuível à P23.

## 5. Ensaio em cópia fiel (11/11/2026)

Script `scratchpad/p23b/ensaio_1226.py`. Cópia da produção em PostgreSQL local descartável; a produção só foi lida. O cancelamento da conta 2501 foi feito **só na cópia**.

| Conferência | Resultado |
|---|---|
| Cópia | idêntica à produção (65 migrations) |
| Funções substituídas | as 11 iguais ao texto da reversão |
| Migration | nenhum dado alterado; 4 novas, 11 alteradas; leituras de 11/2026 iguais |
| Reversão e reaplicação | funções iguais; nenhum dado alterado |
| Segurança | nenhuma função definer sem `search_path`; nenhuma para anon; as internas sem acesso de authenticated |
| Prévia da conta 2501 | elegível; pagamento [188], estorno [193], R$ 250,00 / R$ 250,00 |
| Cancelamento (na cópia) | Psicóloga pendente: 03, 17 e 24/11 (**R$ 750,00**) → 17 e 24/11 (**R$ 500,00**) |
| Total de despesas de 11/2026 | 26.907,16 → 26.657,16 (**−250,00**) |
| Dashboard (despesas previstas de 11/2026) | 13.378,45 → 13.128,45 (**−250,00**) |
| Preservado | movimentos, saldos, `pagamento_fatura`, recorrência (ativa) e todas as outras contas idênticos |
| Conta 2501 | `Dispensada`, valor 250,00, sem data de pagamento; ocorrência de 03/11 `DISPENSADA` com a conta e o motivo; auditoria com [188] e [193] |
| Pagamento | recusado: “Obrigação cancelada: nada a pagar” |
| Geração | o plano de 11/2026 não recria a sessão (0 a gerar) |
| Reversão depois do cancelamento | recusada, sem alterar nada |
