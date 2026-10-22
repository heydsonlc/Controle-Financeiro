# FIN-PAGAMENTO-TRAVA-1 — Proteção transacional de pagamentos e operações concorrentes

**Data:** 2026-10-22.

**Situação:** implementado e validado **localmente**:
- cluster PostgreSQL descartável;
- arquivo SQLite temporário;
- processos Flask reais;
- dados fictícios.

**Autorização:** SCRIPT-CONTRATO V5 — FIN-PAGAMENTO-TRAVA-1. Antes de começar, revisei e enviei o `580c3e3`; o check do Supabase ficou `skipped`.

**Não foi feito:**
- migration remota ou Alembic no `gastos.db` (nenhuma migration foi necessária);
- dados reais;
- publicação;
- pagamentos no novo aplicativo.

## 1. Pontos de corrida encontrados (código real)

Todos têm a mesma causa: a rota lia a conta (situação e valor), conferia e só depois gravava, **sem trava**. Uma operação simultânea conferia o mesmo estado antigo.

| # | Fluxo | Onde | Efeito possível |
|---|---|---|---|
| 1 | Pagamento de despesa | `routes/despesas.py` `marcar_como_pago` | Conta paga com valor diferente do movimento (edição simultânea); **dois débitos** (dois pagamentos) |
| 2 | Edição de despesa | `atualizar_despesa` (PUT) | Muda o valor de conta **já paga**, mesmo sem concorrência (pagar e depois editar) |
| 3 | Exclusão de despesa | `deletar_despesa` | Excluir durante um pagamento em andamento |
| 4 | Pagamento de fatura | `CartaoService.pagar_fatura` | Somava as compras sem travar a fatura; compra ou recálculo simultâneos mudavam a fatura durante a liquidação |
| 5 | Recálculo de fatura | `CartaoService.recalcular_fatura` | Lia "não paga" e gravava `valor = planejado` **por cima** de um pagamento recém-confirmado |
| 6 | Compra no cartão | `CartaoService.adicionar_lancamento` | O desvio de fatura paga testava `status_fatura == 'PAGA'`, que ninguém grava: a compra **entrava na fatura paga**, também durante o pagamento |
| 7 | Editar ou excluir compra | `routes/cartoes.py` PUT/DELETE `/lancamentos/<id>` | Alterava compra de fatura paga, sem nenhuma conferência |
| 8 | Parcelas futuras | `atualizar_parcelas_futuras` e `cancelar_parcelas_futuras` | Decidiam "futura (não paga)" sem travar as faturas |
| 9 | Baixa automática | `services/debito_automatico_service.py` | Duas baixas → **dois débitos**; saldo conferido desatualizado; **uma falha desfazia as baixas anteriores do lote, que continuavam informadas como feitas**; um débito já estornado fazia a conta voltar a `Pago` **sem movimento válido** |
| 10 | Estorno de despesa ou fatura | `estornar_pagamento` | Dois estornos → **dois créditos** |
| 11 | Estorno de receita | `routes/receitas.py` `estornar_realizada` | Dois estornos → dois débitos |
| 12 | Saldo da conta bancária | `ContaBancariaService.criar_movimento` e `recalcular_saldo_conta` | Duas transações na mesma conta bancária recalculavam o saldo sem ver o movimento da outra (saldo gravado errado) |
| 13 | Transferência | `gerar_transferencia` | Duas contas bancárias sem ordem de trava |

**SQLite (o banco do Flask local, `gastos.db`):**
- `SELECT … FOR UPDATE` é **ignorado** no SQLite.
- O pysqlite lê **fora** de transação.
- Por isso o duplo clique em "Pagar" também podia gerar dois débitos.

**Fluxos de pagamento que não usam o mesmo serviço** (identificados; fora dos módulos deste contrato):
- financiamentos: pagamento direto e estorno de parcela (`routes/financiamentos.py`);
- consórcios;
- documento financeiro sugerido (`documento_financeiro_sugestao_service`);
- recebimento de receita.

Todos criam movimento pelo `ContaBancariaService.criar_movimento`, que **agora trava a conta bancária**, então o saldo deles também fica correto. A conferência de situação deles, porém, não ganhou trava. É recomendada no FIN-PAGAMENTOS-1 ou num contrato próprio.

## 2. Reprodução antes da correção

Rodei os 17 testes novos contra o código **anterior** (worktree temporário do `HEAD`, já removido): **13 falharam**. Foi reproduzido localmente o cenário encontrado no Supabase de teste:

| Cenário (código anterior) | Resultado |
|---|---|
| Conta de R$ 350,40: pagamento × edição para R$ 500,00 | Pagamento 200, edição 200. **Conta `Pago` com valor 500,00 e movimento de 350,40** |
| Dois pagamentos simultâneos | 200 e 200: **dois débitos** |
| Dois estornos simultâneos | 200 e 200: dois créditos |
| Duas baixas automáticas | As duas debitaram |
| Pagamentos de contas diferentes na mesma conta bancária | Saldo gravado 880,00 (o calculado era 529,60) |
| Recálculo durante o pagamento | O recálculo não esperava (corrida silenciosa) |
| SQLite, edição durante pagamento | Divergência igual |

Os 4 que passavam no código anterior:
- rollback por falha;
- a edição e a compra do **novo aplicativo** esperando o pagamento do Flask (o novo aplicativo já travava);
- dois pagamentos no SQLite.

## 3. Alterações

**`backend/services/trava_financeira.py` (novo):**
- `travar(modelo, ids)` trava as linhas em ordem de id e as **relê do banco** (`populate_existing`). Nada lido antes da trava é usado.
- PostgreSQL: `SELECT … FOR UPDATE OF <tabela>` com `SET LOCAL lock_timeout = '10s'`.
- SQLite: um `UPDATE <tabela> SET id = id` (SQL literal, sem `onupdate`) toma a trava de escrita do banco **antes** da releitura.
- `eh_conflito(exc)` reconhece trava não obtida (55P03), deadlock (40P01), falha de serialização (40001) e "database is locked".
- `ConflitoConcorrente` e `MENSAGEM_CONFLITO` dão o erro controlado.

**Rotas e serviços:**

| Arquivo | Mudança |
|---|---|
| `routes/despesas.py` | Pagar, estornar, editar e excluir travam a conta e releem antes de conferir. Editar o **valor** de conta paga → 409 (campos descritivos continuam editáveis). Fatura já paga → 409 (antes, erro 500). Parcela de financiamento confirmada no mesmo commit do pagamento. Conflito → 409 controlado |
| `services/cartao_service.py` | `fatura_esta_paga` (`status_pagamento='Pago'` ou `status_fatura='PAGA'`), `travar_faturas`, `_fatura_travada`. `pagar_fatura` e `recalcular_fatura` travam a fatura. `adicionar_lancamento` trava cada fatura e **desvia de fatura paga de fato**; as parcelas seguintes andam junto, como no novo aplicativo. As parcelas são confirmadas antes dos recálculos (ver §4). Parcelas futuras: faturas travadas e estado relido antes de decidir |
| `routes/cartoes.py` | Editar ou excluir compra trava a fatura (atual e de destino). Compra de fatura paga → 409. Rollback e 409 em conflito nas rotas de compra |
| `services/conta_bancaria_service.py` | `criar_movimento` trava a conta bancária; a transferência trava as duas em ordem de id e reconfere se estão ativas |
| `services/debito_automatico_service.py` | **Cada baixa é uma transação própria** (conta, movimento e saldo juntos ou nada), com conta e conta bancária travadas e relidas. Débito já estornado não marca a conta como paga nem debita de novo: ela fica Pendente e o usuário decide |
| `routes/receitas.py` | Estorno de receita trava o recebimento |

**Nenhuma migration** (nem Supabase nem Alembic). O novo aplicativo não mudou: as funções dele já travavam a conta e a fatura com `FOR UPDATE`.

## 4. Ordem de travas

**Ordem adotada:**
1. conta financeira (despesa ou fatura; várias em ordem crescente de id);
2. compras do cartão (sempre pela fatura já travada);
3. conta bancária (em `criar_movimento`; transferência: as duas em ordem de id);
4. movimento (inserção).

**Deadlock encontrado e corrigido nos testes de concorrência da FIN-FATURA-UNICA-1:**
- **Causa:** uma compra parcelada segurava a trava da última fatura e voltava para travar a primeira no recálculo. Outra compra segurava a primeira e esperava as seguintes.
- **Correção:** as parcelas são confirmadas antes dos recálculos. Cada recálculo trava **uma** fatura e confirma, sem voltar na ordem.

**Sem espera indefinida.** Uma trava não obtida em 10 s (PostgreSQL) ou no timeout do driver (SQLite) gera rollback e **409 "Outra operação financeira está em andamento… tente novamente"**, sem gravar nada (testado). Uma nova tentativa repete a transação inteira; o pagamento repetido é idempotente pela situação (o segundo recebe 409 "já foi paga" e não debita).

**Limite conhecido:**
- As funções do novo aplicativo travam as faturas de uma compra em ordem de **id**; as compras do Flask e do novo aplicativo, em ordem de **mês**.
- Os dois só se cruzam se ids e meses estiverem em ordens opostas, o que é raro.
- Nesse caso o PostgreSQL detecta o deadlock e uma das operações recebe erro controlado.
- Mudar a função do novo aplicativo exigiria nova migration remota (não autorizada).

## 5. Testes

**`tests/test_pagamento_trava.py`: 17 testes, todos passando.**
- Cada operação roda num **processo Flask real**, com conexão e transação próprias.
- O primeiro processo para numa barreira **imediatamente antes do commit**, com tudo já gravado na transação.
- O segundo é iniciado e o teste **confere que ele está parado na trava** (`pg_stat_activity`) antes de liberar o primeiro.
- A conferência `coerente()` exige: situação, valor e movimentos contam a mesma história (débitos − estornos = valor pago, ou zero se pendente).
- O saldo gravado é sempre igual ao calculado a partir dos movimentos.

| # | Item do contrato | Resultado |
|---|---|---|
| 1 | Edição durante pagamento (350,40 × 500,00) | Pagamento 200; edição **esperou** e recebeu 409; conta 350,40 = movimento 350,40; saldo 649,60 |
| 2 | Pagamento durante edição | Edição 200; pagamento esperou e pagou **500,00**; movimento 500,00 |
| 3 | Dois pagamentos simultâneos | 200 e 409; **1 débito** |
| 4 | Pagamento repetido após conclusão | 409; continua 1 débito |
| 5 | Falha no meio (depois de gravar o movimento) | 500; conta Pendente, **nenhum movimento**, saldo igual; a nova tentativa paga normalmente |
| 6 | Fatura em paralelo com compra (Flask) | A compra esperou o pagamento e foi para a fatura **seguinte**; fatura paga = executado = movimento (250,00); compras da fatura paga intactas (md5) |
| 6b | Fatura × compra do **novo aplicativo** | Esperou e recusou ("foi paga durante o cadastro") |
| 7 | Fatura em paralelo com recálculo | O recálculo esperou e não sobrescreveu: fatura paga com 250,00 (não o planejado) |
| 8 | Duas baixas automáticas | Uma baixou e a outra não; **1 débito**; saldo 920,00 |
| 8b | Baixa após estorno | Não volta a `Pago` sem movimento; fica Pendente |
| 9 | Dois estornos do mesmo movimento | 200 e 409; débito + 1 crédito com `movimento_original_id`; saldo de volta a 1000,00 |
| 10 | Estorno concorrente com novo pagamento | Ordem válida: débito → crédito → débito; conta paga e coerente |
| 11 | Saldos | Duas contas pagas na mesma conta bancária em paralelo: saldo gravado = calculado = 529,60 |
| 12 | Movimentos duplicados | Nenhum em todos os cenários |
| 13 | Parcelas e faturas preservadas | Fatura paga e compras dela intactas; compra de fatura paga não muda pelo Flask (409/409) |
| 14 | FIN-DESPESAS-1 e FIN-CARTOES-1 | A edição e a compra do novo aplicativo esperam o pagamento do Flask e são bloqueadas depois |
| 15 | Bancos suportados | SQLite (arquivo temporário, processos reais): edição × pagamento sem divergência; dois pagamentos → 1 débito |
| — | Sem espera indefinida | Conta presa por outra transação: 409 "tente novamente", nada gravado |

**Testes ajustados porque documentavam o defeito do Flask** (agora exigem a correção):
- `test_supabase_despesas`: o Flask recusa mudar o valor de conta paga (409) e aceita observação (200).
- `test_supabase_cartoes`: o Flask recusa editar ou excluir compra de fatura paga (409/409).
- `test_supabase_fatura_unica` (fatura paga + compras simultâneas): com a trava, a segunda compra **espera** a primeira e não chega à barreira. O teste agora confere essa espera.

**Regressão:**
- Suítes de despesas, cartões, fatura única, recorrência e receitas passam.
- E2E local: **47/47**.
- Suíte completa: 1434 passaram; só as 5 falhas que já existiam (§9).

## 6. PostgreSQL × SQLite

| | PostgreSQL | SQLite |
|---|---|---|
| Trava de linha | `FOR UPDATE OF <tabela>` | Não existe; o `UPDATE … SET id = id` trava o **banco inteiro** para escrita até o commit |
| Granularidade | Linha (operações em contas diferentes andam em paralelo) | Banco (escritas serializadas; leituras continuam) |
| Espera máxima | `lock_timeout` 10 s → 409 | Timeout do driver (5 s) → "database is locked" → 409 |
| Deadlock | Detectado pelo banco → 409 | Não ocorre (uma trava só) |
| Garantia | Sem divergência nem duplicidade nos fluxos cobertos | Igual, entre processos e threads do Flask; o custo é a serialização das escritas |

## 7. Diferenças de comportamento do Flask (intencionais)

1. **Editar o valor de despesa paga:** 409 (antes 200 e divergência com o movimento). Descrição e observações continuam editáveis.
2. **Editar ou excluir compra de fatura paga:** 409 (antes 200, sem conferência).
3. **Compra em fatura paga** vai para a próxima fatura aberta (antes o desvio nunca disparava). As parcelas seguintes andam junto, como no novo aplicativo.
4. **Pagar fatura já paga:** 409 com a mensagem do serviço (antes 500).
5. **Baixa automática:**
   - cada conta é atômica;
   - débito estornado não volta sozinho a `Pago`.
6. **Operação concorrente sem trava em 10 s:** 409 controlado.

Valores, competências, cálculos de fatura, vínculos e movimentos anteriores não mudam. Nenhum contrato de API mudou além dos códigos acima.

## 8. Riscos residuais

- **Fluxos fora do escopo** (financiamentos, consórcios, documento sugerido, recebimento de receita): o saldo ficou protegido pela trava da conta bancária, mas falta a trava na conferência de situação de cada um.
- **Geração de recorrências e importação de cartão** gravam compras sem travar a fatura e podem pôr uma compra recorrente ou importada numa fatura paga. Isso **não altera** os valores pagos (o recálculo ignora fatura paga), mas a lista de compras daquela fatura passa a ter um item a mais.
- **Consolidação (FECHADA)** recalcula sob trava e grava `status_fatura` e `valor_consolidado` depois. Não mexe em valor pago nem em situação de pagamento.
- **Estorno de despesa:** a checagem legada "existe estorno com o mesmo `conta_id`" impede um segundo estorno depois de um novo pagamento. É regra anterior e não foi alterada.

## 9. Suíte completa

Comando original (`venv\Scripts\python.exe -m pytest`; o `pytest.ini` já tem `-q`). Resumo real impresso pelo pytest: **`5 failed, 1434 passed, 19 skipped, 1140 warnings in 718.15s`** (1417 anteriores + 17 novos). O código de saída 1 vem só das 5 falhas que já existiam:
- `test_categorias_sistemicas_mobilidade::test_projecoes_veiculo_usam_categorias_sistemicas_granulares`
- `test_ocr_tools::test_status_sem_ferramentas_retorna_estrutura_valida`
- `test_ocr_tools::test_poppler_ausente_retorna_aviso`
- `test_receitas_ux::test_cards_resumo_calculam_previsto_realizado_diferenca_confiabilidade`
- `test_veiculos_mobilidade_2b::test_suprimir_despesas_previstas_futuras`

## 10. Arquivos

- `backend/services/trava_financeira.py` (novo)
- `backend/routes/despesas.py`, `backend/routes/cartoes.py`, `backend/routes/receitas.py`
- `backend/services/cartao_service.py`, `backend/services/conta_bancaria_service.py`, `backend/services/debito_automatico_service.py`
- `tests/test_pagamento_trava.py` (novo)
- `tests/test_supabase_despesas.py`, `tests/test_supabase_cartoes.py`, `tests/test_supabase_fatura_unica.py`
- `docs/FIN_PAGAMENTO_TRAVA_1.md` e `docs/ROADMAP.md`
