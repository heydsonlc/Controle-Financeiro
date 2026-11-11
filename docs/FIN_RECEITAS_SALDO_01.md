# FIN-RECEITAS-SALDO-01 — previsões de receita pelo valor-base e saldo do mês

**Situação:** implementado localmente no ramo `receitas-saldo-01`, sobre `d69dddd`. Migration `20261224090000`, não aplicada em produção. Publicação só com autorização.
**Testes:** nível N4 (integridade financeira).

## 1. Diagnóstico (11/11/2026, somente leitura)

### P01 — o valor-base novo não aparecia em “Receitas do mês”

O salvamento funcionava: as fontes 81 (Cargo em Comissão, R$ 4.643,44) e 82 (Salário CBMGO, R$ 19.217,39) estavam gravadas com o valor novo.

A tela salva pela função `redefinir_fonte_receita`, que repete a regra do Flask ([backend/routes/receitas.py:268-291](../backend/routes/receitas.py#L268-L291)):
- grava o valor na fonte;
- só cria as previsões que faltam nos 12 meses seguintes;
- as previsões já gravadas não mudam.

Os dois salvamentos de 11/11 (00:21 e 00:28 UTC) criaram as previsões de 05/2027 a 10/2027 com o valor novo. As de 11/2026 a 04/2027 ficaram com o valor antigo, porque foram geradas em 05/2026.

Novembro já estava recebido com o valor antigo: recebimentos 47 e 48, créditos 173 e 174.

### P02 — saldo do mês

O cálculo está certo; a exibição não estava. A tela de Despesas soma as receitas de `receitas_do_mes` e subtrai `contas_do_mes`. Em 11/2026: 22.924,98 − 25.954,60 = **−3.029,62**.

O cartão escrevia `Math.abs(saldo)`, sem sinal, e indicava o negativo só pela cor. A cor também não aparecia, porque o tema claro força `p, span, div, label { color: #1d1d1f !important }` ([theme-light.css:364](../frontend/static/css/theme-light.css#L364)). O resultado era “R$ 3.029,62” em preto.

Os R$ 28.984,22 “implícitos” não existiam: as receitas usadas eram R$ 22.924,98, de dois recebimentos.

**Defeitos latentes na soma** (não afetavam 11/2026):

| Onde | Defeito |
|---|---|
| Tela de Despesas | recebimento estornado sem previsão era somado |
| Tela de Despesas | parcial contava só o recebido |
| Dashboard | somava o orçado mais os recebimentos sem `orcamento_id`, o que conta em dobro o recebimento ligado só pela fonte |
| Dashboard | “recebidas” incluía os estornados |

## 2. Correção de 11/2026 em produção

Autorizada pelo titular com a opção “Corrigir e compensar” e executada em 11/11/2026, numa transação, com ensaio prévio desfeito por rollback.

**Correções** (valores antigos conferidos com `FOR UPDATE` antes de gravar):

| Fonte | Previsão | Recebimento | Crédito | Antes | Depois |
|---|---|---|---|---|---|
| Cargo em Comissão | 203 | 47 | 173 | R$ 4.453,70 | R$ 4.643,44 |
| Salário CBMGO | 215 | 48 | 174 | R$ 18.471,28 | R$ 19.217,39 |

- Cada recebimento recebeu uma observação “[CORRECAO]”.
- O saldo da conta foi recalculado pela função oficial.

**Compensação:**
- Ajuste pela função oficial `ajustar_saldo_conta`, executada como o titular: movimento 212, débito de R$ 935,85, “Ajuste manual de saldo - correção dos recebimentos de 11/2026 (reajuste)”.
- A Caixa (conta 96) continua com o saldo conciliado de **R$ 822,95**, igual ao recalculado.

**Auditoria:** registro `corrigir_recebimento_reajuste` em `financeiro.operacao_receita`, com o antes e o depois de cada registro.

**Resultado:**
- Receitas de 11/2026: **R$ 24.860,83** (Cargo 4.643,44 + Salário 19.217,39 + AC-5 1.000,00).
- Saldo do mês: 24.860,83 − 25.954,60 = **−R$ 1.093,77**.

**Conferência por retrato antes e depois:** só mudaram as 6 tabelas previstas (`conta_bancaria`, `movimento_financeiro`, `receita_orcamento`, `receita_realizada`, `operacao_receita`, `operacao_despesa`). As outras 82 ficaram idênticas.

## 3. Solução (migration `20261224090000`)

### 3.1 Atualização das previsões pelo valor-base

Funções novas:

| Função | Acesso | O que faz |
|---|---|---|
| `previsoes_para_atualizar(item, a_partir)` | interna | classifica cada previsão da fonte a partir da competência |
| `previa_atualizacao_previsoes(perfil, item, a_partir)` | authenticated, só lê | o que muda e o que fica, com o motivo |
| `atualizar_previsoes_fonte(perfil, item, versao, a_partir, esperadas, chave)` | authenticated | aplica a atualização |

`atualizar_previsoes_fonte`:
- confere a versão da fonte (`travar_fonte`) e a quantidade da prévia;
- trava as previsões;
- é idempotente pela chave;
- registra `atualizar_previsoes_fonte` em `operacao_receita`, com o antes e o depois.

Uma previsão só é atualizada se for gerada automaticamente, estiver pendente e tiver valor diferente do valor-base. Ficam preservadas, com o motivo:
- recebida (há recebimento na competência, inclusive estornado);
- parcialmente recebida;
- valor alterado manualmente;
- data prevista definida manualmente;
- zerada ou removida;
- criada ou anotada manualmente (observação diferente de “Gerado automaticamente…”).

**Marca nova:** coluna `receita_orcamento.valor_manual`, que nasce `false`. A função `editar_receita` passa a marcá-la quando o usuário muda o valor de uma previsão. Mudar só a data não marca.

**Tela de Receitas:** ao salvar uma fonte existente, se houver previsões pendentes com outro valor, abre “Atualizar previsões pelo valor-base”:
- competência inicial (padrão: o mês atual);
- tabela com a competência, o valor atual e o novo;
- lista “Ficam como estão”;
- botões “Manter as previsões” e “Atualizar N previsão(ões)”.

Salvar a fonte continua igual ao Flask.

### 3.2 Regra única do total de receitas

A função `receitas_totais_do_mes(perfil, mes)` soma sobre as mesmas linhas de “Receitas do mês” (`receitas_do_mes`):

| Situação | Previstas | Recebidas |
|---|---|---|
| Previsão | maior entre o previsto e o recebido válido (parcial conta o previsto; acima do previsto conta o recebido) | o recebido válido |
| Removida | 0 | 0 |
| Recebimento estornado | 0 | 0 |
| Recebimento sem previsão | o recebido (uma vez) | o recebido |
| Previsão de consórcio | o valor previsto | 0 |

Ela é usada pela tela de Despesas (saldo do mês) e pelo Dashboard (`dashboard_resumo_tela`, só o trecho das receitas).

### 3.3 Saldo do mês com sinal

[despesas-adaptacoes.js](../web/src/js/despesas-adaptacoes.js) mostra o saldo no formato de moeda com o sinal (“-R$ 1.093,77”), com as classes `saldo-negativo` e `saldo-positivo`. A cor fica no CSS próprio, que vence o `!important` do tema. O título do cartão mostra a conta “Receitas do mês − despesas do mês”.

### 3.4 Reversão

[supabase/reversao/20261224090000_receitas_saldo_anterior.sql](../supabase/reversao/20261224090000_receitas_saldo_anterior.sql):
- devolve `editar_receita` (bytes exatos, corpo em CRLF) e `dashboard_resumo_tela`;
- remove as funções novas e a coluna;
- recusa se houver previsão com `valor_manual`.

As previsões atualizadas continuam com o valor gravado.

## 4. Competências futuras (12/2026 a 04/2027)

O mecanismo está disponível, mas nada foi executado em produção. Depois da publicação, o titular abre a fonte em Receitas, salva e confirma na prévia. O ensaio (seção 6) mostra o resultado esperado.

## 5. Testes por impacto (N4)

| Bateria | Arquivos | Resultado |
|---|---|---|
| Banco (novo) | `tests/test_supabase_receitas_saldo.py`: prévia, atualização, preservadas, auditoria, idempotência, prévia velha, versão, recebimento depois da prévia, marca manual, consórcio, perfis e permissões, regra do total, Dashboard e reversão | 13/13 |
| Regressão de banco | Receitas (4 arquivos), recorrências e categorias, Dashboard, movimentações, Lançamentos, carga, cartões que leem o Dashboard (3), cadeia de reversões (i7), com PostgREST | 254/254 (com os 13 novos) |
| Unitários web | `web/tests/unit` (listas de RPC) | 92/92 |
| E2E (novo) | `web/tests/e2e/receitas_saldo.spec.mjs`: prévia, competência inicial, confirmação, “manter”, saldo negativo com sinal e cor | 3/3 |
| E2E (regressão) | `receitas_saldo`, `receitas_tela`, `despesas`, `despesas_pagamento_lote`, `dashboard_tela`, `movimentacoes`, `recorrencias_inativacao` | 24/24 (uma falha intermediária do teste novo: lia o perfil ativo antes de a moldura carregar; corrigido no teste) |

**Não executados, com justificativa:** suíte completa (N5) e demais E2E, porque Cartões, Mobilidade, Financiamentos, Documentos e Importação não leem receitas nem usam as funções alteradas.

## 6. Ensaio em cópia fiel

Script `scratchpad/rec01/ensaio_1224.py`, executado em 11/11/2026. Cópia da produção em PostgreSQL local descartável; a produção só foi lida.

| Conferência | Resultado |
|---|---|
| Cópia | idêntica à produção (63 migrations, até `20261222090000`) |
| Funções substituídas antes da migration | iguais ao texto da reversão (`editar_receita`, `dashboard_resumo_tela`) |
| Migration | nenhum dado alterado (só a coluna nova, toda `false`); 4 funções novas, 2 alteradas, nenhuma removida |
| Dashboard | receitas previstas e recebidas idênticas: 11/2026 = 24.860,83 / 24.860,83; 12/2026 = 23.924,98 / 0,00 |
| Prévia a partir de 12/2026 | Cargo: 5 previsões (12/2026 a 04/2027, +948,70); Salário: 5 (+3.730,55); AC-5: nada a mudar; nenhuma preservada |
| Atualização **só na cópia** | 5 + 5 previsões; mudaram só `receita_orcamento` e `operacao_receita`; recebimentos, movimentos e saldos iguais; dezembro passa a 24.860,83 |
| Segurança | nenhuma função definer sem `search_path`; nenhuma para anon; a interna sem acesso de authenticated |
| Reversão e reaplicação | funções iguais ao antes; coluna removida; reaplicação igual à primeira |

## 7. Pendências e observações

- A P23 (`f844795`, ramo `despesas-cancelamento-01`) também tem migration 1223 e altera `dashboard_resumo_tela`. Quem for publicado depois precisa ser regenerado a partir do texto de produção daquele momento e, se for o caso, renumerado.
- O E2E deixa no usuário E fictício previsões de 11/2026 a 10/2027 da fonte de teste, criadas pela regra do Flask (os 12 meses a partir de hoje). A fonte de teste fica inativa.
