# FIN-DESPESAS-REAL-1 — Validação real do cadastro e edição de despesas

**Data:** 2026-10-21. **Alvo:** projeto Supabase de teste **Controle-Financeiro** (`fzjmge…`). A Calculadora Judicial não foi tocada.

**Situação:** **validado**. Os dados fictícios foram removidos e o estado final ficou idêntico ao inicial, exceto pela migration autorizada.

**Autorização:** SCRIPT-CONTRATO V5 — FIN-DESPESAS-REAL-1.

**Não foi feito:**
- publicar;
- aplicar outras migrations;
- alterar dados reais, os perfis Pessoal ou Empresa, ou os seus vínculos.

## 1. Push

- `2fdca76` foi enviado após a revisão: sem segredos nem dados pessoais.
- O check "Supabase Preview" ficou `completed/skipped`: o deploy automático continua desligado.

## 2. Migration aplicada

**`status` e `simular`:** só `20261026090000` estava pendente; o dry-run listou exatamente ela.

**Conferências da seção 3 do contrato** (somente leitura, `scratchpad/conferir_despesas.py`):
- **Projeto correto** (`fzjmge…`, nunca o proibido).
- **Dependências presentes:**
  - todas as colunas usadas de `conta`, `item_despesa`, `categoria`, `conta_bancaria`, `movimento_financeiro`, `financiamento_parcela` e `financeiro.recorrencia_competencia`;
  - as funções `pode_gerir_perfil`, `pode_acessar_perfil` e `gerador_do_perfil`;
  - a PK usada no `ON CONFLICT`.
  Ou seja, é compatível com FIN-RECORRENCIA-1, T1 e FIN-FATURA-UNICA-1.
- **Sem colisão:** nenhum dos 15 objetos novos já existia.
- **Sem alteração destrutiva:** os únicos `alter table` habilitam RLS na própria tabela nova.
- As funções escrevem **apenas** em `conta`/`item_despesa` (linhas novas ou pendentes), `recorrencia_competencia` e `operacao_despesa`.
- **Autorização, concorrência e erros:** verificação de gestão no banco, versão + `FOR UPDATE`, idempotência por chave e erros financeiros explícitos (`P0001`/`22023`/`42501`).

**Aplicação e verificação:**
- Aplicação exclusiva (`supabase_migrations.py aplicar --versoes 20261026090000`), **uma vez**; nada mais ficou pendente.
- **Privilégios:**
  - nenhuma função com EXECUTE para `anon`;
  - as 7 públicas (`categorias_de_despesa`, `despesa_para_edicao`, `criar_despesa`, `editar_despesa`, `excluir_despesa`, `editar_recorrencia`, `inativar_recorrencia`) só para `authenticated`;
  - as 7 internas sem EXECUTE para o navegador;
  - `financeiro.operacao_despesa` com RLS forçada e sem privilégios.

## 3. Testes reais

**Dados fictícios:**
- seeds de perfis, contas, recorrência e MVP;
- **gestão** só nos vínculos de teste;
- novo gerador só no **Perfil B temporário**;
- A é LEITOR da Empresa.

**E2E real** (Auth e Data API reais, navegador de 390 px): **36/36**. Inclui:
- os 5 testes de `despesas.spec.mjs` (validação, avulsa com competência ≠ vencimento, edição e exclusão, despesa paga sem ações, LEITOR sem ações e 403);
- o fluxo de recorrência pela tela (cadastrar, gerar pelo FIN-RECORRENCIA-1, editar, excluir conta dispensada, inativar).

**API real** (`scripts/supabase_despesas_real.py`, logins reais de A e B): **22/22**.

| # | Teste | Resultado |
|---|---|---|
| 1 | Avulsa | Pendente, R$ 350,40 |
| 2 | Recorrência mensal | Cadastro sem conta; geradas pelo FIN-RECORRENCIA-1 em 31/01, 28/02 e 31/03/2030 |
| 3 | Recorrência anual | Só 15/01/2030 na janela |
| 4 | Competência ≠ vencimento | Vence em 05/07/2030 e aparece em 06/2030 |
| 5 | Categoria e conta bancária | Categoria inexistente, conta da Empresa e débito sem conta: 400 |
| 6 | Débito automático na avulsa | Débito e conta do Perfil B gravados |
| 7 | Edição de pendente | Valor, vencimento e competência (a conta mudou de mês) |
| 8 | Edição de recorrência | Contas de jan–mar intactas; abril gerado com o novo valor |
| 9 | Inativação | 2031 não é oferecido; 2030 mantido |
| 10 | Exclusão segura | Conta e item removidos |
| 11 | Dispensa de competência | Março/2030 excluída, dispensada e **não recriada** em duas gerações |
| 12 | Conta paga | Editar e excluir: 400 ("Despesa paga: correção só por estorno"); valor intacto |
| 13 | Conta com movimento | Exclusão: 400 ("Possui movimento financeiro vinculado") |
| 14 | Fatura e outros módulos | Fatura: 403; parcela de consórcio bloqueada |
| 15 | Concorrência e versão desatualizada | Duas edições paralelas da mesma versão: **[200, 400]**; versão velha: 400 |
| 16 | Idempotência | Repetição devolve o mesmo resultado; **3 criações simultâneas com a mesma chave → 1 item** |
| 17 | Usuário com gestão | Todas as escritas feitas pelo B (gestor do Perfil B) |
| 18 | Somente leitura | A vê a Empresa, mas criar e excluir: 403 |
| 19 | Outro perfil | A no Perfil B, B com conta do Pessoal e B no Pessoal: 403 |
| 20 | Anônimo | 401 nas três funções testadas |
| 21 | Saldos e movimentos | Contas bancárias idênticas; único movimento novo é o inserido de propósito no item 13 |
| 22 | FIN-RECORRENCIA/T1/FATURA-UNICA | Com o perfil no gerador do Flask: excluir conta recorrente e mudar o calendário dão 400; 0 faturas duplicadas |

## 4. Comparação com as regras válidas do Flask

- **Equivalência comprovada localmente contra o Flask real** (`tests/test_supabase_despesas.py`):
  - cadastro de avulsa e de recorrente com campos de item e conta idênticos;
  - edição e exclusão de pendentes com o mesmo resultado.
- **No remoto**, as regras válidas coincidentes ficaram confirmadas:
  - competência padrão no mês do vencimento;
  - débito automático exige conta ativa do perfil;
  - paga e com movimento não são excluídas;
  - inativação mantém o histórico.
- **As 8 diferenças intencionais** de `docs/FIN_DESPESAS_1.md` §4 se comportaram como documentado (itens 2, 4, 6, 11 e 12 acima).

## 5. Pendência de concorrência com pagamentos (confirmada no banco real)

**Cenário reproduzido como evidência, sem correção:**
1. O Flask (processo real apontando para o banco de teste) começou a pagar uma conta fictícia de R$ 350,40.
2. Enquanto isso, a conta foi editada para R$ 500,00 pelo novo aplicativo.
3. Resultado: **conta com R$ 500,00, "Pago"; movimento bancário de R$ 350,40.**

**Funções envolvidas (Flask):**
- `backend/routes/despesas.py::marcar_como_pago`:
  - lê a conta com `_query_contas().filter(Conta.id == id).first()`, **sem trava**;
  - confere `status_pagamento == 'Pago'` só em memória;
  - cria o movimento com o `conta.valor` lido no início;
  - grava status e data numa transação posterior à leitura.
- Mesma leitura sem trava em:
  - `estornar_pagamento` (mesmo arquivo);
  - `CartaoService.pagar_fatura`;
  - `debito_automatico_service.executar_baixa_debito_automatico` (baixa automática).
- **Segunda corrida do mesmo padrão:** dois pagamentos simultâneos da mesma conta passam pela conferência "não está paga" e criam **dois movimentos**.

**Menor alteração transacional necessária**, a fazer no FIN-PAGAMENTOS-1 com testes de concorrência real:
- ler a conta com **`SELECT … FOR UPDATE`** (`.with_for_update()` na consulta) **antes** das conferências;
- só então conferir o status e calcular o valor do movimento a partir da linha travada.

Efeitos:
- a edição do novo aplicativo, que já usa `FOR UPDATE`, e os pagamentos passam a se serializar;
- o segundo pagamento simultâneo encontra "Pago" e é recusado.

A mesma mudança vale para estorno, `pagar_fatura` e a baixa automática. Ela não altera nenhuma regra de cálculo.

## 6. Comprovação da limpeza

**Ordem:**
1. `scripts/supabase_despesas_real_limpeza.py remover` (o que os testes criaram além dos seeds): 2 movimentos, 9 identidades, 15 contas, 11 itens e 12 chaves de idempotência.
2. Removedores dos seeds: MVP, recorrência (inclusive as 4 linhas de histórico do gerador geradas pelas trocas FLASK/NOVO do teste), contas e perfis.

**Impressão digital final idêntica à inicial em:**
- **conteúdo** de `perfil_financeiro`, `conta`, `item_despesa`, `lancamento_agregado`, `cartao_categoria_limite`, `categoria`, `categoria_cartao`, `conta_bancaria`, `movimento_financeiro` e `usuario`;
- `financeiro.perfil_acesso` (nenhuma permissão de gestão temporária restou) e `financeiro.categorias`;
- contagens das 52 tabelas `public`, Auth e Alembic (`c4f7a2d91b3e`).

**Diferenças, só as esperadas:**
- migrations (+`20261026090000`);
- as 5 tabelas do schema `financeiro` existem e estão **vazias**: `gerador_recorrencia` 0 (nenhum perfil migrado), `recorrencia_competencia` 0 (nenhuma dispensa fictícia), `operacao_despesa` 0;
- sequências avançadas, o que é normal.

## 7. Arquivos desta etapa

- `scripts/supabase_despesas_real.py` (novo): 22 testes reais pela API e a evidência da corrida de pagamento.
- `scripts/supabase_despesas_real_limpeza.py` (novo): marca e remoção do que os testes criaram.
- `docs/FIN_DESPESAS_REAL_1.md` e `docs/ROADMAP.md`.
