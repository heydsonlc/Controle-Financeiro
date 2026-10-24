# FIN-MOVIMENTACOES-1 — Pagamento de despesas, recebimento de receitas, estornos e movimentos do mês

**Situação:** concluído e validado localmente; aguardando validação real. A migration `20261101090000` **não** foi aplicada no Supabase remoto (§9).

O novo aplicativo passa a pagar despesas comuns, receber receitas, estornar cada operação e mostrar os movimentos do mês. Tudo usa o mesmo motor do FIN-CARTOES-PAGAMENTO-1: não existe um segundo motor financeiro.

## 1. Diagnóstico

| Operação | Flask | Novo aplicativo (antes) | Reaproveitado | Implementado |
|---|---|---|---|---|
| Pagar despesa | `POST /api/despesas/<id>/pagar`: débito `DESPESA`, conta `Pago` com valor = pago; sincroniza parcela de financiamento | Só leitura (situação) | Regra, origem, travas, saldo, escritor único | `pagar_despesa` |
| Receber receita | `POST /api/receitas/realizadas`: um registro por recebimento + crédito `RECEITA`; vários se acumulam na previsão (Parcial) | Só leitura (`receitas_do_mes`) | Regra, tabelas, situação Parcial/Recebida, `receita_estornada` | `receber_receita` |
| Estornar despesa | Crédito `ESTORNO_DESPESA`, conta `Pendente`; o 2º estorno depois de pagar de novo é bloqueado (defeito, ver §6) | — | Regra e origem | `estornar_pagamento_despesa` |
| Estornar receita | Débito `ESTORNO_RECEITA` por recebimento | — | Regra e origem | `estornar_recebimento` |
| Atualizar saldo | `saldo_inicial + créditos − débitos` gravado em `saldo_atual` | Já no PAGAMENTO-1 (`atualizar_saldo_conta`) | Integral | — |
| Consultar movimentos | Extrato por conta bancária | — | `movimento_financeiro` | `movimentos_do_mes` (seção na tela de Contas) |

## 2. Decisões

| Código | Decisão | Como ficou |
|---|---|---|
| D1 | Pagar despesa existente | Despesa comum (inclui as geradas por veículos ou assinaturas). Ficam fora: faturas (tela de Cartões) e parcelas de consórcio e de financiamento, que continuam no Flask porque os módulos delas sincronizam o próprio estado (§5) |
| D2 | Receber receita existente | Previsão do mês; o recebimento pontual sem previsão continua no Flask |
| D3 | Valor diferente | **Despesa:** quitação integral; diferença só com `JUROS`, `DESCONTO` ou `AJUSTE` e justificativa; o devido original fica em `pagamento_fatura.valor_executado`. **Receita (decisão do titular):** mantida a semântica de parcial. O formulário vem com o que falta; valor menor = recebimento parcial (sem justificativa); acima do que falta exige justificativa, gravada no recebimento (`[ACIMA DO PREVISTO]`) |
| D4 | Estorno | Motivo obrigatório; ligado ao movimento original; compensatório; o original fica; duplicado recusado |
| D5 | Um motor de saldo | Movimentos + `atualizar_saldo_conta` do PAGAMENTO-1 |
| D6 | Um sistema por perfil | A mesma atribuição do T1/PAGAMENTO-1 (`financeiro.gerador_recorrencia`). Perfil `NOVO`: só o novo aplicativo paga e recebe. O Flask recusa (409 `SISTEMA_NOVO`) pagar ou estornar despesa (exceto consórcio e financiamento) e receber ou estornar recebimento de previsão. **Débito automático (decisão do titular):** o Flask não baixa automaticamente nesses perfis; a despesa fica pendente e é paga pelo botão Pagar. Nenhum perfil real foi migrado |

## 3. Regras (no banco, uma transação por operação)

**Ordem de travas:** chave → perfil (trava consultiva do T1) → registro (despesa, ou tabela de recebimentos e previsão) → conta bancária → movimento.

- **Recebimento:** a ordem é a mesma de `travar_previsao`; primeiro a tabela de recebimentos, depois a previsão, para não haver ciclo de espera com a edição de previsões.

**Pagamento de despesa:**
1. Exige gestão do perfil, chave da operação (a repetição devolve o mesmo resultado) e o perfil no novo aplicativo.
2. Trava a despesa e recusa se for fatura, consórcio ou financiamento (`BLOQUEADA`), ou se já estiver paga (`DESPESA_PAGA`).
3. Confere o valor devido visto na tela (`VALOR_MUDOU`) e a classificação com justificativa (`AJUSTE_OBRIGATORIO`).
4. Exige a conta do perfil e ativa.
5. Grava o débito `DESPESA`, atualiza o saldo e marca a conta `Pago` (valor = pago, data e conta). Registra o detalhe em `pagamento_fatura`.

**Estorno de despesa:**
- Precisa ser o débito vigente: o mais recente da despesa sem crédito ligado (`JA_ESTORNADO`).
- Grava o crédito `ESTORNO_DESPESA` com `movimento_original_id`.
- A despesa volta a `Pendente` **com o valor devido original**. Um pagamento feito pelo Flask (inclusive débito automático) também pode ser estornado.

**Recebimento:**
- Previsão do perfil, sem fonte do módulo de consórcios e não removida (`BLOQUEADA`).
- O "falta receber" é calculado como em `receitas_do_mes` (mesma fonte e competência, sem estornados nem previsão de consórcio) e conferido contra o visto na tela (`VALOR_MUDOU`).
- Acima do que falta, exige justificativa (`JUSTIFICATIVA_OBRIGATORIA`).
- Grava o recebimento (`receita_realizada` ligada à previsão) e o crédito `RECEITA` **juntos**, e atualiza o saldo.

**Estorno de recebimento:**
- Por recebimento; recusa o já estornado (`JA_ESTORNADO`).
- Grava o débito `ESTORNO_RECEITA` com `movimento_original_id`. O registro e o crédito ficam, e a previsão volta a contar só o que não foi estornado.

**Movimentos do mês (`movimentos_do_mes`, só leitura):**
- contas do perfil com o saldo calculado pelos movimentos;
- cada movimento com data, descrição, tipo, origem, valor, conta, o item que o originou (despesa, fatura ou receita) e o movimento estornado, quando houver.

**Recorrências:** a geração só cria previsões e contas. Nenhuma execução financeira é automática no novo aplicativo. As regras D5 e D6 de cartões não mudaram.

## 4. Telas

- **Contas do mês, ao abrir uma despesa:** histórico dos pagamentos (com ajuste e estorno) e o botão **Pagar** ou **Estornar pagamento**.
- **Formulário de pagamento:** já vem com o valor devido, a data de hoje e as contas ativas com saldo. A classificação e a justificativa só aparecem se o valor for diferente.
- **Seção "Movimentos do mês":** saldos das contas e os movimentos do mês.
- **Receitas, ao abrir uma previsão:** recebimentos, cada um com **Estornar recebimento**, e o botão **Receber**. O formulário vem com o que falta, avisa quando o recebimento é parcial e pede justificativa só acima do que falta.
- **Código:** formulários em `web/src/js/liquidacao.js`, compartilhado pelas duas telas. As chamadas ao banco ficam em `despesas.js` e `receitas.js`.

## 5. Banco (migration `20261101090000`)

| Objeto | Acesso |
|---|---|
| `dados_pagamento_despesa`, `pagar_despesa`, `estornar_pagamento_despesa`, `dados_recebimento_receita`, `receber_receita`, `estornar_recebimento`, `movimentos_do_mes` | Só `authenticated`; conferem o perfil (leitura: acesso; escrita: gestão) |
| `debito_vigente`, `bloqueio_do_pagamento`, `bloqueio_do_recebimento`, `recebido_da_previsao`, `contas_ativas_com_saldo`, `travar_conta_bancaria` | Internas: sem EXECUTE para PUBLIC, anon e authenticated |

- **Nenhuma tabela nova** e nenhum objeto existente alterado; só o comentário de `financeiro.pagamento_fatura`.
- Essa tabela passa a guardar também os detalhes do pagamento de despesa comum (`fatura_id = public.conta.id`).
- Idempotência: `operacao_despesa` e `operacao_receita`.
- Saldo: o mesmo `saldo_atual` recalculado pelos movimentos.

**Flask:**
- `despesas.py`: `_paga_pelo_novo_aplicativo` vale para faturas e despesas comuns, exceto consórcio e financiamento.
- `receitas.py`: recusa receber e estornar em perfil `NOVO`.
- `debito_automatico_service.py`: não baixa em perfil `NOVO`.
- A verificação vem antes de travar o registro, na mesma ordem do novo aplicativo.

## 6. Diferenças em relação ao Flask

| Flask | Novo aplicativo | Classificação |
|---|---|---|
| O recebimento é gravado (commit) **antes** do crédito: uma falha no movimento deixa recebimento sem dinheiro | Recebimento e crédito na mesma transação (teste de falha injetada) | Correção intencional |
| Despesa: pagar, estornar, pagar de novo e estornar de novo → o 2º estorno é recusado (busca alternativa por `conta_id + origem`) | Cada estorno se liga ao seu débito | Correção intencional |
| Estorno de despesa mantém o valor pago | Volta ao valor devido original | Correção intencional |
| Valor pago diferente do devido sem registro | Classificação e justificativa | Regra nova (D3) |
| Sem idempotência por solicitação | Chave da operação | Proteção nova |

## 7. Testes

Tudo local, em bancos descartáveis e com dados fictícios.

| Conjunto | Resultado |
|---|---|
| `tests/test_movimentacoes.py` (novo, 14 testes: cenários 1 a 18, D6 nos dois sentidos, débito automático, consórcio no Flask, estorno de pagamento feito pelo Flask) | 14/14 |
| Contraprova: três mutações (sem o bloqueio de despesa paga; "recebido" contando estornados; débito automático sem o escritor único) | Os testes correspondentes falharam, como esperado |
| E2E `web/tests/e2e/movimentacoes.spec.mjs` (novo, cenário 20: despesa com juros e estorno; receita parcial, acima do que falta e estorno; movimentos e saldo na tela) | 2/2 |
| `despesas.spec.mjs` (texto do bloqueio de despesa paga atualizado) e demais telas afetadas | §7.1 |
| Cenário 19 (pagamento de cartões preservado) | `tests/test_cartoes_pagamento.py` e `pagamento.spec.mjs` na regressão por impacto (§7.1) |
| Conferência local da migration | OK: 13 funções novas (7 expostas a `authenticated`, 6 internas), nada alterado, dados idênticos |

### 7.1 Regressão por impacto

Seleção: 44 de 110 arquivos Python, web unitário e as 11 specs E2E.

| Conjunto | Aprovados | Falhas | Duração |
|---|---|---|---|
| Python (seleção) | 711 de 714 | 3, abaixo | 11,5 min |
| Web unitário | 15 | 0 | < 0,1 min |
| E2E local (11 specs) | 48 de 52 → **52/52** depois do ajuste abaixo | 4, abaixo | 1,7 min |

**Falhas e classificação:**
- **`test_supabase_gerador_t1::test_10` — mudança intencional (D6).**
  - O teste fixava a regra antiga do T1 ("o Flask paga no perfil migrado").
  - Com o D6, o Flask recusa o pagamento de despesa comum nesse perfil.
  - O teste foi atualizado (`test_10_flask_consulta_e_nao_paga_no_perfil_migrado`): o Flask continua consultando e não paga. Módulo: 29/29.
- **`test_receitas_ux` — preexistente** (falha igual em `9a50410`).
- **`test_contexto_financeiro_escopo::test_conta_cartao_receita_despesa_e_recorrencia_sao_isolados_por_perfil` — preexistente e não relacionado.**
  - É um 500 em `criar_cartao`, no SQLite (`ObjectDeletedError` em `ItemDespesa.to_dict`).
  - Falha igual num worktree limpo do HEAD `86f830a`, sem nenhuma alteração deste MVP.
  - **Causa revista no §9.1:** depende da ordem de execução, não do horário. Não foi corrigido (fora do escopo).
- **E2E — 4 falhas com uma única causa, no spec novo.**
  - `movimentacoes.spec.mjs`, que roda antes de `pagamento.spec.mjs`, deixava a "Conta Perfil B" com saldo 700. O `pagamento.spec` espera 0 e parou antes de inativar o cartão.
  - O cartão ativo mudou as contagens da geração em `pendencia.spec` e `recorrencia.spec` (2 testes).
  - **Ajuste, só no spec novo:** ele também estorna o segundo recebimento, deixando o saldo de partida. E2E local completo depois: **52/52**.

A suíte completa (nível 3) fica para antes da aplicação remota.

## 8. Pendências para a validação real

1. Aplicar `20261101090000` no Supabase de teste, com conferência antes e depois e autorização específica.
2. Cenários reais de despesa, receita e movimentos, no padrão do `supabase_cartoes_pagamento_real.py`, e limpeza específica (recebimentos e movimentos de teste).
3. Atribuir ao novo aplicativo (D6) só os perfis migrados. Lembrar que, a partir daí, o débito automático deixa de ser baixado sozinho.
4. Fora deste MVP: baixa automática de débito automático e recebimento pontual (sem previsão) no novo aplicativo; parcelas de consórcio e de financiamento seguem no Flask.

## 9. Preparação da validação real (FIN-MOVIMENTACOES-REAL-1)

Nada foi escrito no remoto. HEAD `435670b`, com 7 commits locais.

### 9.1 Regressão completa (bateria única, código final)

| Conjunto | Total | Aprovados | Falhas | Ignorados | Duração |
|---|---|---|---|---|---|
| Python (suíte completa) | 1616 | 1611 | 5 | 0 | 17,5 min |
| Web unitário | 15 | 15 | 0 | 0 | < 0,1 min |
| E2E local (11 specs) | 52 | 52 | 0 | 0 | 1,0 min |

- **Falhas preexistentes**, as mesmas de `9a50410`:
  - `test_veiculos_mobilidade_2b`;
  - `test_categorias_sistemicas_mobilidade`;
  - `test_ocr_tools` (2, dependem das ferramentas deste computador);
  - `test_receitas_ux`.
- **Nenhuma falha nova.** Despesas, receitas, estornos e os E2E financeiros passaram.
- **`test_contexto_financeiro_escopo` passou na suíte completa.** A causa foi revista: **depende da ordem de execução, não do horário**.
  - Rodado sozinho, falha sempre (500 em `criar_cartao`, SQLite): 18:20 e 3 vezes às 18:58.
  - Também falha sozinho no HEAD anterior, sem as alterações deste MVP.
  - Dentro da suíte completa passa (15:34 e 18:39).
  - Preexistente, sem relação com este MVP. Fica para observar na validação integrada antes da publicação.

### 9.2 Migration `20261101090000`

- **Versão:** igual à commitada.
- **Objetos:**
  - 13 funções novas: 7 com EXECUTE só para `authenticated` e 6 internas, com EXECUTE revogado de PUBLIC, anon e authenticated;
  - 0 tabelas criadas ou removidas, 0 `ALTER`/`DROP`;
  - a única declaração sobre objeto anterior é o `comment` em `financeiro.pagamento_fatura`.
- **Conferência local:** nada alterado nem removido; dados idênticos.
- **Segurança das funções:** todas `SECURITY DEFINER` com `search_path` vazio. Perfil conferido em todas; identidade por `auth.uid()` nas chaves e nos detalhes.
- **Funcionamento:** transação única, idempotência por chave e ordem de travas (§3).

### 9.3 Cenários reais preparados (não executados no remoto)

**Código:**
- `scripts/supabase_movimentacoes_cenarios.py`, com os cenários;
- `scripts/supabase_movimentacoes_real.py`, para a execução real. Exige o Perfil B atribuído ao novo aplicativo e compara, no cenário 20, os registros fora do Perfil B (contas bancárias, movimentos, contas, receitas e detalhes de pagamento).

**Dados:** despesas e receitas criadas pela API do novo aplicativo, com o marcador `[teste FIN-MOVIMENTACOES-REAL-1]`, em 03/2040, e uma conta inativa criada com o marcador.

**Cenários:**
- **Despesas:** 1 integral; 2 diferença justificada (com o devido original registrado); 3 conta inativa; 4 conta de outro perfil; 5 duplicado; 6 simultâneos; 7 estorno; 8 segundo pagamento e segundo estorno.
- **Receitas:** 9 integral; 10 parcial; 11 complemento até o integral; 12 acima do previsto com justificativa; 13 duplicado; 14 simultâneos; 15 estorno; 16 segundo recebimento e segundo estorno.
- **Integridade geral:**
  - 17 saldo igual aos movimentos;
  - 18 falha intermediária: a conta bancária fica presa até o `lock_timeout`, nada é gravado (nem o recebimento) e as mesmas chaves concluem depois;
  - 19 sem permissão;
  - 20 outro perfil intacto;
  - 22 extrato com origens e estornos ligados.
- **Cenário 21:** coberto por `supabase_cartoes_pagamento_real.py` na mesma execução.

**Ensaio local com o mesmo código: 20/20 + limpeza.** Cluster descartável, PostgREST com o `lock_timeout` de 8 s da Data API e JWT reais.

### 9.4 Limpeza

**`supabase_despesas_real_limpeza.py remover`:**
- só registros acima da marca e fora dos seeds: despesas (itens e contas), recebimentos, previsões, fontes, movimentos e chaves (`operacao_despesa` e `operacao_receita`);
- os detalhes de pagamento saem com os movimentos (cascade), e a conferência informa os restantes;
- a conta inativa sai pelo marcador (lista ampliada para os dois marcadores de teste) e acima da marca;
- os perfis e contas temporários saem pelos removedores dos seeds.

**Ensaio:** nada do teste restou (0 detalhes, contas, movimentos, recebimentos e despesas), e os recebimentos e movimentos anteriores ficaram idênticos (md5).

**Critério da execução real:** `depois` repetido no fim, com conteúdo idêntico ao de antes da migration.

### 9.5 Estado remoto anterior (somente leitura)

- **Identidade do projeto, pela conexão efetiva:** ref do pooler = ref da Data API (`fzjmge…`); login do usuário B = `auth.users`.
- **Histórico:** 12 migrations aplicadas (até `20261031090000`); pendente só `20261101090000`; nada só no remoto. Nenhuma sessão ativa nem trava.
- **Conferência `antes`: OK.**
  - 64 tabelas e 93 funções capturadas e iguais ao esperado.
  - Nenhuma definição salva, porque o alvo não troca função existente.
  - Despesas, receitas, contas bancárias, movimentos, pagamentos e chaves vazias, exceto 1 fonte de receita preexistente.
  - Estado guardado fora do repositório.
- Sem `db push`, nem simulação. Nenhum perfil real teve o responsável alterado.

### 9.6 Pendências para a aplicação

1. Autorização para aplicar só `20261101090000`.
2. `depois` contra a pasta do `antes`.
3. Marca, seeds, E2E real, `supabase_movimentacoes_real.py` e `supabase_cartoes_pagamento_real.py`; depois a limpeza, os removedores dos seeds e o `depois` final.
