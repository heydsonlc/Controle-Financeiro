# FIN-CARTOES-PAGAMENTO-1 — Pagamento e estorno de fatura de cartão no novo aplicativo

**Situação:** concluído e validado localmente — aguardando validação real. A migration `20261031090000` **não** foi aplicada no Supabase remoto (§9).

O novo aplicativo passa a pagar e estornar faturas de cartão com o Supabase como motor financeiro. O Flask foi a referência das regras; não é preciso mantê-lo rodando para isso.

## 1. Decisões

| Código | Decisão | Como ficou |
|---|---|---|
| D1 | Começar pelas faturas, com estrutura reaproveitável | Movimento, saldo, conta bancária, idempotência e escritor único são as estruturas já existentes. Só a tabela de detalhes é específica da fatura |
| D2 | Sem pagamento parcial | Todo pagamento quita a fatura; não existe saldo pendente, mínimo nem rotativo |
| D3 | Valor diferente do executado, se justificado | Classificação obrigatória: `JUROS` (maior), `DESCONTO` (menor) ou `AJUSTE` de quitação integral (qualquer sentido), mais justificativa. O executado e as compras não mudam |
| D4 | Pagamento e estorno no mesmo MVP | Feitos |
| D5 | Um sistema por perfil | Usa a atribuição já existente (`financeiro.gerador_recorrencia`, FIN-RECORRENCIA-T1). Perfil `NOVO`: só o novo aplicativo paga e estorna faturas, e o Flask recusa (409 `SISTEMA_NOVO`). Perfil `FLASK` (padrão): o novo recusa (`SISTEMA_FLASK`) |
| D6 | Cenário 10 remoto só na próxima validação real | Mantido |

## 2. Pagamento

**Tela:** em Cartões, ao abrir a fatura, aparece o botão **Pagar fatura**. O formulário já vem preenchido:
- cartão, competência e total das compras (o total vem do banco);
- valor pago igual ao total;
- data de hoje;
- a primeira conta ativa do perfil, com o saldo.

A classificação e a justificativa só aparecem se o valor for diferente do total. Depois de confirmar, a tela mostra o valor debitado e o novo saldo da conta, e a fatura passa a **Paga**.

**Banco (`financeiro.pagar_fatura`, uma transação):**
1. Exige gestão do perfil e uma chave da operação: a mesma chave devolve o mesmo resultado, sem novo débito.
2. Exige o perfil no novo aplicativo (D5).
3. Trava a fatura do perfil e recusa se ela já estiver paga.
4. Recalcula o executado pelas compras. Se for diferente do total que o usuário viu, recusa (`EXECUTADO_MUDOU`), e a tela mostra o total novo.
5. Confere o valor e a justificativa (D3).
6. Trava a conta bancária e exige que seja do perfil e esteja ativa.
7. Grava o movimento `DEBITO`, origem `FATURA`, e recalcula o `saldo_atual`.
8. Marca a fatura como `Pago`, com valor = pago, executado, data e conta.
9. Registra os detalhes do pagamento.

Qualquer falha desfaz tudo. O fechamento (`status_fatura`) não muda.

## 3. Estorno

**Tela:** numa fatura paga aparece **Estornar pagamento**, com fatura, valor pago, conta e data. O motivo é obrigatório e a data é editável. A fatura volta a **Aberta**, e o histórico mostra o pagamento como estornado.

**Banco (`financeiro.estornar_pagamento_fatura`):**
1. Recebe o movimento de débito do pagamento: sem ele, não há estorno.
2. Exige gestão, chave da operação e o perfil no novo aplicativo.
3. Trava a fatura, a conta bancária e o movimento.
4. Exige que esse débito seja o **pagamento vigente**: o mais recente da fatura sem crédito que o referencie.
5. Grava o `CREDITO`, origem `ESTORNO_FATURA`, com `movimento_original_id`, e recalcula o saldo.
6. Devolve a fatura a `Pendente` e recalcula planejado e executado, como qualquer fatura aberta. O fechamento é preservado.
7. Registra motivo, data e responsável. O débito original fica no histórico.

Um pagamento feito pelo Flask antes de o perfil migrar também pode ser estornado: o registro do estorno fica com origem `FLASK`.

## 4. Extrato e saldo

- O saldo é `saldo_inicial + créditos − débitos` dos movimentos, a mesma conta do Flask. `saldo_atual` continua sendo esse valor recalculado (o mesmo cache que o Flask grava), não um segundo saldo.
- A tela recebe o saldo calculado pelos movimentos.
- Consulta só do necessário (`financeiro.dados_pagamento_fatura`): a fatura, as contas ativas com saldo, os pagamentos e estornos da fatura e o que o usuário pode fazer. O extrato bancário completo não faz parte deste MVP.

## 5. Objetos (migration `20261031090000`)

| Objeto | Tipo | Acesso |
|---|---|---|
| `financeiro.pagamento_fatura` | Tabela nova: executado no pagamento, ajuste, justificativa, responsável e estorno; um pagamento vigente por fatura (índice único parcial) | RLS forçada, sem privilégios |
| `dados_pagamento_fatura`, `pagar_fatura`, `estornar_pagamento_fatura` | Funções expostas | Só `authenticated`; conferem o perfil |
| `executado_fatura`, `saldo_da_conta`, `atualizar_saldo_conta`, `exigir_pagamento_novo`, `travar_fatura_do_perfil`, `pagamento_vigente` | Funções internas | Sem EXECUTE para PUBLIC, anon e authenticated |

**Por que uma tabela nova:**
- O movimento guarda valor, conta e data, e esses dados não foram duplicados.
- Não havia onde guardar a classificação, a justificativa, o responsável e o motivo do estorno; o Flask só acrescenta texto em `observacoes`, e isso continua.
- Idempotência: reaproveita `financeiro.operacao_cartao`.

Todas as funções são `SECURITY DEFINER` com `search_path` vazio. Nenhuma tabela existente mudou e nenhum privilégio existente foi ampliado.

**Ordem de travas** (FIN-FATURA-INTEGRIDADE-1): chave → perfil (trava consultiva 20261023, a mesma de `criar_compra`) → fatura → conta bancária → movimento.

**Flask** (`backend/routes/despesas.py`): pagar e estornar **fatura** de perfil `NOVO` devolve 409 `SISTEMA_NOVO`. A verificação usa a mesma `flask_pode_gerar` e vem antes de travar a fatura. Despesas comuns continuam sendo pagas pelo Flask.

## 6. Diferenças em relação ao Flask

| Flask | Novo aplicativo | Classificação |
|---|---|---|
| Pagar, estornar, pagar de novo e estornar de novo: o 2º estorno é recusado ("já foi estornado"), porque a busca alternativa por `conta_id + origem` acha o 1º estorno. A fatura fica paga sem saída. **Defeito confirmado** em ensaio local | Cada estorno referencia o seu débito (pagamento vigente) | Correção intencional |
| Estorno mantém `valor` = valor pago | Estorno recalcula a fatura aberta (valor = planejado) | Correção intencional |
| Valor pago diferente do executado sem classificação; um valor menor quita sem registro | Classificação e justificativa obrigatórias (D3) | Regra nova |
| Sem idempotência por solicitação | Chave da operação | Proteção nova |

O defeito do Flask não foi corrigido nele, porque está fora do escopo. Com a D5, perfis migrados não passam mais por ele.

## 7. Testes

Tudo local, em bancos descartáveis e com dados fictícios.

| Conjunto | Resultado |
|---|---|
| `tests/test_cartoes_pagamento.py` (novo, cenários 1 a 14, D5 e estorno de pagamento do Flask) | 15/15 |
| Contraprova: duas mutações da migration (sem o bloqueio de fatura paga; pagamento vigente = 1º débito, como o fallback do Flask) | Os testes correspondentes falharam, como esperado |
| E2E `web/tests/e2e/pagamento.spec.mjs` (novo, cenário 15: pagar com juros, estornar, pagar de novo, histórico e saldo na tela) | Aprovado |
| Regressão por impacto (TESTES-IMPACTO-1) | §7.1 |
| Conferência local da migration (`supabase_conferencia_migration.py --alvo 20261031090000 local`) | OK: 9 funções novas (3 só `authenticated`, 6 internas), 1 tabela com RLS forçada e sem privilégios, nada alterado, dados idênticos |

### 7.1 Regressão por impacto

38 de 109 arquivos Python, web unitário e as 10 specs E2E (todas, porque `app.css` é usada por todas as telas).

| Conjunto | Aprovados | Falhas | Duração |
|---|---|---|---|
| Python (seleção) | 806 de 807 | 1, abaixo | 13,6 min |
| Web unitário | 15 | 0 | < 0,1 min |
| E2E local (10 specs) | 50 | 0 | 0,9 min |

**A falha era uma mudança esperada de comportamento, não um defeito.**
- O teste: `test_pagamento_trava::test_compra_do_novo_aplicativo_espera_o_pagamento_do_flask`.
- O pagamento de fatura do Flask passou a conferir o sistema do perfil (D5) com a trava consultiva do perfil. `criar_compra` toma a mesma trava em modo exclusivo.
- Com isso, a compra do novo aplicativo feita durante um pagamento do Flask espera **antes de planejar**. Depois do pagamento ela vai para a fatura seguinte, com `mes_fatura_original` registrado.
- Antes, ela era recusada com "foi paga durante o cadastro". A fatura paga continua intacta.
- O teste foi atualizado para o comportamento novo, com o motivo no código: 17/17 no módulo.
- Só o arquivo de teste mudou depois da bateria, então ela não foi repetida.

A suíte completa (nível 3) fica para antes da aplicação remota.

## 8. Pendências para a validação real

1. Aplicar `20261031090000` no Supabase de teste, com conferência antes e depois e autorização específica.
2. Cenários reais de pagamento e estorno, mais o cenário 10 (D6), na mesma validação.
3. Atribuir ao novo aplicativo (D5) só os perfis que forem migrados.

## 9. Preparação da validação real (FIN-CARTOES-PAGAMENTO-REAL-1)

Nada foi escrito no remoto.

### 9.1 Verificações

- **`tests/test_pagamento_trava.py` na versão final: 17/17.**
  - A falha anterior (`test_compra_do_novo_aplicativo_espera_o_pagamento_do_flask`) ficou resolvida pela atualização da expectativa (§7.1).
  - Comportamento conferido: o pagamento é do Flask; a compra concorrente do novo aplicativo espera, vai para a fatura seguinte com a competência original registrada, e a fatura paga não muda.
- **Fatura consolidada paga e estornada** (`test_fatura_consolidada_paga_e_estornada_mantem_a_consolidacao`, consolidação pela rota real do Flask): aprovado, sem divergência.

| Informação | Após pagamento | Após estorno |
|---|---|---|
| Situação financeira | Pago | Pendente |
| Consolidação (`status_fatura`, total e data) | Preservada | Preservada |
| Movimento bancário | Débito | Débito + crédito ligado a ele |
| Histórico | Pagamento vigente | Pagamento com estorno |
| D6 | — | Compra sem confirmação ainda recusada (`CONSOLIDADA`) |

- **Migration:** 1 tabela e 9 funções; nenhum objeto existente alterado. Na conferência local, privilégios como previstos, RLS forçada e dados idênticos.

### 9.2 Regressão final (bateria única, versão final)

| Conjunto | Total | Aprovados | Falhas | Ignorados | Duração |
|---|---|---|---|---|---|
| Python (suíte completa) | 1602 | 1597 | 5 | 0 | 16,5 min |
| Web unitário | 15 | 15 | 0 | 0 | < 0,1 min |
| E2E local (10 specs) | 50 | 50 | 0 | 0 | 0,9 min |

As 5 falhas são as **preexistentes** conhecidas, que falham igualmente em `9a50410` (§13 do FIN-CARTOES-FECHAMENTO-1):
- veículos (2);
- OCR (2), que dependem das ferramentas deste computador;
- `test_receitas_ux` (1).

Nenhuma falha nova.

### 9.3 Cenários reais preparados (não executados no remoto)

- **Código:**
  - `scripts/supabase_cartoes_pagamento_cenarios.py` (cenários) e `scripts/supabase_cartoes_pagamento_real.py` (execução real);
  - o executor exige o Perfil B atribuído ao novo aplicativo e confere os registros fora do Perfil B (cenário 16).
- **Ensaio local com o mesmo código: 15/15 + limpeza.** Cluster descartável, PostgREST com o `lock_timeout` de 8 s da Data API, JWT reais e Flask real.
- **Cenários:**
  1. pagamento integral;
  2. juros (sem justificativa recusado);
  3. desconto;
  4. conta inativa;
  5. conta de outro perfil;
  6. pagamento duplicado;
  7. pagamentos simultâneos;
  8. falha com rollback: a conta bancária fica presa até o `lock_timeout`, nada é gravado e a mesma chave conclui depois;
  9. estorno;
  10. estorno duplicado;
  11. pagar, estornar, pagar e estornar;
  12. compra concorrente: uma compra do Flask em andamento faz o pagamento esperar, recusar o total antigo (`EXECUTADO_MUDOU`) e pagar o novo;
  13. fatura consolidada paga e estornada;
  14. isolamento (outro usuário, anônimo, funções internas);
  15. saldos e movimentos, conferidos depois de cada operação por diferença em relação ao saldo de partida.
- **Na mesma execução:** `scripts/supabase_cartoes_real.py`, que inclui o cenário 10 corrigido do FIN-CARTOES-FECHAMENTO-REAL-1.
- **Limpeza** (`supabase_despesas_real_limpeza.py remover`):
  - a marca passa a incluir `conta_bancaria`;
  - remove a conta inativa pelo marcador `[teste FIN-CARTOES-PAGAMENTO-REAL-1]` e acima da marca;
  - os detalhes de pagamento saem junto com os movimentos (cascade), e a conferência informa os restantes (esperado: 0);
  - cartão, compras, faturas, movimentos e chaves, como antes.

### 9.4 Estado remoto anterior (somente leitura)

- **Identidade do projeto, pela conexão efetiva:** o ref do pooler é igual ao da Data API (`fzjmge…`), e o login do usuário B na Data API tem o mesmo id em `auth.users`.
- **Histórico:** `20261029090000` e `20261030090000` aplicadas; pendente só `20261031090000`; nada só no remoto. Nenhuma sessão ativa nem trava.
- **Conferência `antes`: OK.**
  - 63 tabelas e 84 funções capturadas e iguais ao esperado.
  - Nenhuma definição salva, porque o alvo não troca nenhuma função existente.
  - Conta bancária, movimentos, contas e chaves estão vazias.
  - Estado guardado fora do repositório.
- Sem `db push`, nem simulação.

### 9.5 Pendências para a aplicação remota

1. Autorização específica para aplicar só `20261031090000` (`scripts/supabase_migrations.py aplicar --versoes 20261031090000`).
2. Conferência `depois` contra a pasta do `antes`.
3. Marca, seeds, E2E real, `supabase_cartoes_pagamento_real.py` e `supabase_cartoes_real.py`; depois a limpeza e os removedores dos seeds.
4. `depois` de novo no fim, para confirmar o conteúdo idêntico ao de antes da migration.
