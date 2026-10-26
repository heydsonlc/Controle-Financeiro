# FIN-CONTRATOS-3 — Motor e manutenção de Financiamentos e Consórcios (Flask → Supabase)

**Data:** 26/10/2026.

**Situação:**
- **Fase A (Consórcios):** implementada e testada **localmente**.
- **Fase B (motor de Financiamentos):** diagnosticada e priorizada; implementação na próxima execução (§6).
- Sem commit, push, publicação ou migration aplicada.
- O `gastos.db` foi só lido, por contagens, com `mode=ro&immutable=1`; tamanho e mtime conferidos.

## 1. Fase A — Consórcios: funcionalidades concluídas

Migration `20261121090000_financeiro_consorcios_escrita.sql` (local):

| Operação (rota do Flask) | Função | Regras |
|---|---|---|
| Cadastro (`POST /api/consorcios/`) | `criar_consorcio` | Contrato, parcelas (item `Consorcio` "<nome> - Parcela i/n" + despesa no dia 5) e receita de contemplação, numa transação. Idempotente pela chave |
| Edição (`PUT /<id>`) | `editar_consorcio` | Como o Flask: não regenera parcelas; meio de pagamento nas parcelas; contemplação/prêmio recalculados e receita sincronizada |
| Regeneração (`POST /<id>/regenerar-parcelas`) | `regenerar_parcelas_consorcio` | **Segura** (§3) |
| Exclusão (`DELETE /<id>`) | `excluir_consorcio` | Inativa contrato e parcelas; remove só despesa pendente **sem movimento**; receita de contemplação sem movimento sai, com movimento perde só o marcador |

**Fórmulas e regras do Flask reaproveitadas:**
- `calcular_valor_parcela_consorcio`: reajuste fixo ou percentual por passo; arredondamento meio para cima.
- `normalizar_dados_consorcio` / `normalizar_mes_referencia`:
  - formatos `YYYY-MM-DD`, `YYYY-MM`, `M/AAAA` e só o mês;
  - data inicial como base;
  - contemplação no ano seguinte quando o mês é anterior;
  - mesmas mensagens.
- `calcular_valor_premio`.
- `normalizar_pagamento_consorcio`.
- `gerar_ou_atualizar_receita_contemplacao`: fonte "Contemplação de Consórcio", marcador `consorcio_id=N`, recebimento sem conta.

**Escrita:**
- gestão do perfil;
- escritor único (`exigir_pagamento_novo`: perfil no Flask = `SISTEMA_FLASK`, nada gravado);
- cadastros do perfil em série;
- contrato travado (`FOR UPDATE`) nas edições.
- A guarda do Flask (FIN-CONTRATOS-2) recusa essas rotas em perfil NOVO.

**Tela:**
- A tela original de Recorrências (onde o Flask cadastra consórcios) chama as funções pelo `recorrencias-adaptador.js`.
- O aviso da lista: "Consórcios: cadastro, edição e inativação pelo novo aplicativo. Parcelas pagas nunca são apagadas."

## 2. Pagamento e estorno

As parcelas de consórcio continuam pagas e estornadas pelo motor do FIN-CONTRATOS-2 (Despesas). Nada foi refeito.

## 3. Defeitos do Flask que não foram reproduzidos

| Defeito no Flask | Aqui |
|---|---|
| **Regenerar** manda apagar **todas** as despesas do contrato, inclusive pagas. No PostgreSQL a chave estrangeira do movimento faz a regeneração falhar (500, conferido no próprio Flask). **No `gastos.db` (SQLite sem `PRAGMA foreign_keys`) a despesa paga é apagada e o movimento fica órfão** | Parcela paga ou com qualquer movimento (inclusive estornado) fica **intacta**. Só as pendentes sem movimento são atualizadas, criadas ou removidas. Tudo atômico, com o contrato travado |
| Excluir apaga despesa pendente mesmo com pagamento estornado | Só a pendente sem movimento é removida |
| Trocar o meio de pagamento regrava a conta bancária de despesas já pagas | Só as pendentes mudam |
| A receita de contemplação já confirmada (com movimento) tem valor e data reescritos na edição | Fica como está |
| Renomear o contrato perde o vínculo com as parcelas (o vínculo é pelo nome) | As parcelas são renomeadas junto; nome repetido entre consórcios ativos do perfil é recusado |
| No modal de Recorrências, modo consórcio, a "Data inicial" fica escondida, mas o mês de início é "Calculado automaticamente pela Data inicial": o cadastro falha ("Mes de inicio e obrigatorio") | O campo fica visível nos dois modos (adaptação de CSS; o JS do Flask já o lê) |

**Não executar regeneração sobre contratos reais** (decisão do titular). A proteção está comprovada em banco descartável (§4); a decisão de uso real é do titular.

## 4. Testes

| Conjunto | Resultado |
|---|---|
| `tests/test_supabase_consorcios_escrita.py` (novo) | **6 passaram**. Detalhes abaixo |
| `tests/test_supabase_receitas_categorias_tela.py` | 12 passaram (o executor de roteiros do Flask passou a usar um usuário por execução) |
| E2E `recorrencias_tela.spec.mjs` | **7 passaram**, inclusive o novo: consórcio cadastrado pelo modal original no Perfil B, parcelas em Despesas, inativação (pendentes saem) |
| Unitários do `web/` (auditoria de RPC por arquivo) | 30 passaram |
| Regressão completa (banco, Flask, E2E) | 717 de banco/Flask e 90 de E2E: 0 falhas (§7) |

**Banco (`test_supabase_consorcios_escrita.py`):**
- **Cadastro:** 3 contratos, igual ao Flask campo a campo: contrato, itens, despesas e receita de contemplação.
  - Contratos com reajuste percentual e fixo, contemplação, débito automático e formatos de mês diferentes.
- **Edição:** igual ao Flask; renomeia as parcelas.
- **Regeneração segura:**
  - parcela paga e parcela estornada (pendente, com movimento) intactas;
  - pendentes recalculadas; acima de n, removidas;
  - de volta a n: criadas sem duplicar;
  - nenhum movimento tocado.
- **Defeito do Flask** demonstrado no próprio Flask (500 com parcela paga).
- **Exclusão segura.**
- **Escritor único, quem só lê, isolamento, idempotência, nome repetido, validações** (mensagens do Flask).

## 5. Migrations

- `20261121090000_financeiro_consorcios_escrita.sql`:
  - **só funções novas**, nenhuma substituída;
  - nenhuma tabela e nenhum dado;
  - reversão = remover as funções.
- **Pendentes de aplicação:** só esta (as anteriores já estão no Supabase de teste).

## 6. Fase B — Motor de Financiamentos: diagnóstico e plano

**Tamanho:**
- `services/financiamento_service.py` tem 3033 linhas e 68 métodos;
- `routes/financiamentos.py` tem 1591 linhas.

**O que os dados reais usam** (`gastos.db`, só contagem):
- 1 contrato **SAC com TR** (motor Caixa SAC/TR), seguro **fixo** por vigência (9 vigências), 1 amortização extraordinária;
- 22 parcelas pagas e 398 pendentes;
- tabela de TR (`indexador_mensal`) vazia;
- sem faixas MIP, sem ajuste de saldo, sem conferências de caixa e sem documentos.

**Ordem do porte** (fidelidade numérica primeiro, sempre comparada ao próprio Flask em banco descartável):
1. **Geração de parcelas SAC/TR Caixa** (`_gerar_parcelas_caixa_sac_tr`, `_atualizar_parcelas_caixa_sac_tr`), com seguro fixo por vigência e taxa administrativa. Despesas ligadas (`_criar_conta_da_parcela`) e idempotência.
2. **Cadastro e edição** (`criar_financiamento`, `atualizar_financiamento`):
   - campos estruturais só sem execução financeira (`financiamento_possui_execucao_financeira`);
   - vigência inicial;
   - sincronização das despesas pendentes.
3. **Amortização extraordinária** (reduzir prazo/prestação), `recalcular_parcelas_futuras` e seguro das futuras. Parcelas pagas e amortizações históricas intactas.
4. **Ajuste auditável do saldo devedor**, exclusão segura (`pode_excluir_financiamento`), regeneração controlada (`validar_cronograma_regeneravel`).
5. **SAC e PRICE simples**, MIP por faixa etária e indexadores (com dados de TR), para os contratos que vierem.
6. **Quitação:** a simulação já existe no Flask e só calcula.

**Critério de aceite de cada passo:** o mesmo contrato fictício no Flask e no novo aplicativo gera as mesmas parcelas (valores ao centavo, saldo devedor parcela a parcela, seguro, taxa) e a mesma resposta de `GET /api/financiamentos/<id>`. Toda diferença acumulada é demonstrada e investigada antes de seguir. Depois de cada passo, rodar a regressão de pagamentos e estornos do FIN-CONTRATOS-2.

**Risco que segue valendo:** até o motor existir, perfil NOVO não cadastra nem mantém financiamentos em nenhum dos dois aplicativos. Nenhum perfil real vai para o NOVO.

## 7. Arquivos alterados

- **Novos:**
  - `supabase/migrations/20261121090000_financeiro_consorcios_escrita.sql`;
  - `tests/test_supabase_consorcios_escrita.py`;
  - este documento.
- **Alterados:**
  - `web/src/js/recorrencias-adaptador.js` (escrita de consórcios);
  - `web/src/paginas/recorrencias.html` (aviso);
  - `web/src/css/recorrencias-adaptacoes.css` (Data inicial visível no modo consórcio);
  - `web/tests/e2e/recorrencias_tela.spec.mjs`;
  - `web/tests/unit/build.test.mjs` (RPCs liberadas por arquivo);
  - `tests/test_supabase_receitas_categorias_tela.py` (usuário por execução).

**Regressão completa:**
- **Banco do Supabase e Flask** (todos os `test_supabase_*`, movimentações, consórcio/recorrências, consórcio/receita, trava de pagamento, faturas): **717 passaram, 0 falhas**, 18 pulados.
- **E2E completo:** **90 passaram, 0 falhas.**
- **Unitários do `web/`:** 30 passaram.
