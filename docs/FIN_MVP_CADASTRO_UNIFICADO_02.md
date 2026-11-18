# FIN-MVP-CADASTRO-UNIFICADO-02 — Cadastro com pagamento imediato

**Situação: PUBLICADO em 17/11/2026** (seção 9): migration `20261230090000` aplicada (70), `main` em `35d4d25`, deploy
`b410bb33`. Reversão do frontend: deploy `ce683825` (commit `040c3f1`). Falta a homologação do titular com a conta real.

## 1. O que muda

A decisão do FIN-MVP-CADASTRO-UNIFICADO-01 separava sempre cadastro e pagamento. Para a despesa que já foi paga (Pix, débito,
dinheiro) isso criava uma etapa a mais: cadastrar e depois entrar de novo nela só para pagar. Agora, **na despesa direta**, o
modal único tem, ao final, a opção:

> **Registrar esta despesa como paga** (desmarcada por padrão)

- Desmarcada: tudo como antes. A despesa nasce pendente; o botão é **Salvar despesa pendente**.
- Marcada: aparecem **Conta bancária** e **Data do pagamento** (hoje, editável); o botão passa a **Salvar como paga**. A
  despesa é cadastrada e paga na mesma operação, pelo valor integral.

Vale no modal aberto por **Despesas** e por **Lançamentos**, no desktop e no celular (é o mesmo componente).

## 2. Regras por tipo

| Tipo | Pagamento no cadastro |
|---|---|
| Despesa direta | **Sim**, opcional |
| Compra no cartão | Não: o pagamento é o da fatura |
| Despesa recorrente | Não: cada ocorrência é paga separadamente |
| Consórcio | Não: fluxo próprio, sem mudança |
| Abastecimento | Não implementado; avaliação na seção 6 |

A opção só existe na seção de despesa direta: trocar o tipo reconstrói os campos e nada de pagamento viaja para outro tipo. O
serviço e o banco recusam pagamento no cadastro de recorrência.

## 3. Regra financeira: a mesma operação do botão Pagar, numa transação

Não se altera a situação da despesa por conta própria. A migration `20261230090000` cria uma única função,
`financeiro.criar_despesa_paga(perfil, dados, pagamento, chave)`, que chama **na mesma transação**:

1. `criar_despesa` — o cadastro oficial (permissão, escritor do perfil, validações, competência);
2. `pagar_despesa` — o pagamento oficial, o mesmo do botão Pagar: movimento de débito na conta escolhida, saldo da conta
   recalculado, registro do pagamento, despesa marcada como paga com data e conta.

Consequências:

- **Tudo ou nada:** se o pagamento for recusado (conta inválida ou de outro perfil, data inválida, pagamento não habilitado no
  perfil), o cadastro também é desfeito. Não existe despesa "paga" sem registro financeiro, nem despesa pendente criada pela
  metade. A tela diz "Nada foi gravado".
- **Sem duplicar:** a chave de idempotência é a do cadastro e a do pagamento deriva dela. Toque duplo ou reenvio devolvem o
  mesmo resultado: uma despesa, um pagamento, um débito.
- **Indicadores e saldos:** como os registros são os de sempre, Dashboard, listas, extrato da conta e saldos reagem como em
  qualquer pagamento.
- **Estorno e edição:** os de sempre. A despesa paga no cadastro é estornada pela ação Estornar. O antigo campo "Despesa já
  foi paga" **não voltou**: nem na edição, nem como campo solto (o serviço continua recusando `pago` sem conta e data).
- Sem tabela nova e sem alteração de dados existentes. Pagamento sempre integral (juros, desconto e valor diferente continuam
  só na ação Pagar).

## 4. Arquivos

| Arquivo | Mudança |
|---|---|
| `supabase/migrations/20261230090000_financeiro_despesa_paga_no_cadastro.sql` | função `criar_despesa_paga` (só ela) |
| `supabase/reversao/20261230090000_despesa_paga_no_cadastro_anterior.sql` | retira a função |
| `web/src/js/despesas-servico.js` | `POST /api/despesas` com `pagamento: { conta_bancaria_id, data_pagamento }` chama a função nova; `pago` solto continua recusado |
| `web/src/js/cadastro-despesa.js` | a opção, os dois campos, o rótulo do botão e a confirmação "cadastrada e paga" |
| `web/src/css/cadastro-despesa.css` | bloco do pagamento; no celular o botão principal ganha largura para o rótulo |
| `tests/test_supabase_despesa_paga_no_cadastro.py` | 15 testes de banco |
| `web/tests/e2e/cadastro_pagamento_imediato.spec.mjs` | 3 cenários de tela (Despesas, Lançamentos, celular) |
| `web/tests/unit/build.test.mjs` | regras do build atualizadas |

## 5. Testes

| Verificação | Resultado |
|---|---|
| Banco (`test_supabase_despesa_paga_no_cadastro.py`) | 15/15 |
| Regressão de banco dos módulos afetados | 144 aprovados, 0 falhas (7 arquivos: a função nova, despesas, cancelamento, pagamento em lote e identidade, contratos e leitura do Dashboard) |
| Unitários do frontend | 131/131 |
| Suíte e2e completa | **287/287** (3 cenários novos) |

O que os testes de banco provam: o resultado é **idêntico** ao de cadastrar e depois pagar (conta, movimento e registro de
pagamento comparados campo a campo); sete formas de pagamento recusado não deixam despesa, movimento nem saldo alterado; dados
inválidos da despesa e usuário sem permissão não gravam nada; mesma chave repetida e três envios simultâneos resultam numa
despesa e num pagamento; a chave de um cadastro pendente não paga a despesa que já existia; o estorno devolve o saldo; a função
não é executável sem sessão.

O que os testes de tela provam: opção desmarcada por padrão e ausente nos outros tipos; validação de conta e data; toque duplo;
confirmação com valor, conta e competência; a despesa aparece paga na lista sem ser reaberta; saldo da conta menor no valor
exato e as outras contas iguais; recusa do banco não deixa despesa; no celular nada estoura a largura e o rótulo cabe no botão.

## 6. Abastecimento (avaliação pedida, não implementado)

O formulário especializado grava a despesa (ou a compra) e o abastecimento numa transação, por
`salvar_lancamento_abastecimento`. A mesma opção é viável **só quando o abastecimento é pago como despesa direta** (no cartão o
pagamento é o da fatura), com o mesmo desenho: uma função que chama a gravação atual e, em seguida, `pagar_despesa`, na mesma
transação. Não foi feito aqui porque mexe no formulário especializado e nas regras de vínculo com a Mobilidade, que têm testes
e homologação próprios; fica como decisão do titular (sugestão: FIN-MVP-CADASTRO-UNIFICADO-03).

## 7. Reversão

Frontend: voltar ao deploy anterior. Banco: `supabase/reversao/20261230090000_despesa_paga_no_cadastro_anterior.sql` (só retira
a função; as despesas pagas por ela continuam válidas, com os registros de sempre). Ordem: primeiro o frontend.

## 8. Plano de publicação (não executado)

1. Conferir a `main` e avançar o ramo.
2. Backup `PRE_MIGRATION` (`scripts/backup_rotina.py executar --tipo PRE_MIGRATION --migration 20261230090000`).
3. Migration `20261230090000` (69 → 70): só uma função, nenhum dado.
4. Push e deploy do frontend, **depois** da migration (sem a função, a opção marcada é recusada com "Nada foi gravado"; a
   desmarcada funciona igual).
5. Conferências em produção sem login; a conferência com pagamento real fica com o titular, numa despesa verdadeira.

**Nada disso é executado sem autorização expressa do titular.**

## 9. Publicação — 17/11/2026

Autorizada pelo titular (contrato de execução, Etapa 1), na sequência definida.

| Passo | Resultado |
|---|---|
| Verificações anteriores | `main` igual à remota e ramo sobre ela; produção com 69 migrations e só a `20261230090000` pendente; funções oficiais de cadastro e pagamento com a assinatura esperada; validação da conta bancária e da habilitação de pagamento internas ao banco; perfil com conta bancária ativa |
| Meios de pagamento | nenhum meio novo: o pagamento debita uma **conta bancária** do perfil, como a ação Pagar. O texto de ajuda deixou de citar Pix, débito e dinheiro (commit `35d4d25`); testes reexecutados depois da mudança (unitários 131/131; 47/47 nos sete arquivos do cadastro) |
| Conta de outro usuário ou perfil | recusada sem gravar nada (testes de banco: conta de outro perfil, conta inexistente, usuário sem permissão no perfil) |
| Backup | `cf-fzjmgekasjrgvmfdkdog-20261117_221643` (PRE_MIGRATION), íntegro, duas cópias verificadas |
| Migration | só a `20261230090000`; 69 → 70; função única, executável só por usuário autenticado, `security definer` com `search_path` vazio; nenhuma tabela de dados, saldo ou contagem alterados; funções oficiais inalteradas |
| Código | push `b8c9709..35d4d25` na `main` (avanço rápido) |
| Deploy | Cloudflare `b410bb33`; 248/248 arquivos servidos iguais ao build |
| Produção, sem login | 32 verificações do modal (telas levam ao login, módulo carrega sob a CSP real no desktop e no celular, sem sessão não há formulário, sem erros) + 5 desta entrega (função recusada sem sessão, HTTP 401; modal servido com a opção e os dois rótulos; serviço servido chama a função única) |

Nenhuma despesa, pagamento ou movimento foi criado em produção para testar.

**Reversão**

1. Frontend: voltar ao deploy `ce683825` (commit `040c3f1`).
2. Antes de retirar a função, verificar se houve pagamentos reais por ela desde a publicação (operações `pagar_despesa` gravadas no
   mesmo instante do `criar_despesa` da mesma despesa, em `financeiro.operacao_despesa`). **Esses registros são legítimos e não
   são excluídos:** despesa, movimento e pagamento são os de sempre e continuam válidos sem a função; o estorno é o de sempre.
3. Banco: `supabase/reversao/20261230090000_despesa_paga_no_cadastro_anterior.sql` (só retira a função).
4. Último recurso: restauração assistida do backup acima.

**Pendente de homologação com a conta real:** abrir o modal por Despesas e por Lançamentos, no desktop e no celular; conferir a
opção desmarcada por padrão, a lista de contas e os rótulos do botão; registrar a primeira despesa paga verdadeira e conferir a
despesa paga na lista, o movimento na conta e o saldo.

