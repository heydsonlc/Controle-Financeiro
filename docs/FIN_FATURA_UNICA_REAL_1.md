# FIN-FATURA-UNICA-REAL-1 — Validação no Supabase de teste

**Data:** 2026-10-21. **Alvo:** projeto Supabase de teste **Controle-Financeiro** (`fzjmge…`). A Calculadora Judicial não foi tocada.

**Situação:** **validado**. Os dados fictícios foram removidos e o estado final ficou idêntico ao inicial, exceto pela migration autorizada.

**Autorização:** SCRIPT-CONTRATO V5 — FIN-FATURA-UNICA-REAL-1.

**Não foi feito:**
- executar a migration Alembic `d81f5a2b9c3e` no remoto;
- alterar Pessoal ou Empresa;
- publicar.

## 1. Sequência executada

1. **Push de `42d073b`** após revisão, sem segredos nem arquivos pessoais.
   - O check "Supabase Preview" ficou `completed/skipped`: o deploy automático continua desligado.
   - **Só `20261025090000` ficou pendente.**
2. **Verificação estrutural** (somente leitura) de `public.conta`:
   - `item_despesa_id integer NOT NULL`, `cartao_competencia date`, `is_fatura_cartao boolean`;
   - dono `postgres`;
   - nenhum índice ou restrição de unicidade já existente sobre essas colunas;
   - os índices existentes eram apenas os do Flask (`idx_conta_*`, `ix_conta_perfil_financeiro_id`, `conta_pkey`).
3. **Diagnóstico** (`scripts/diagnostico_faturas_duplicadas.py`, somente leitura): **0 faturas** e 0 em todas as verificações. Nada impedia a aplicação.
4. **Impressão digital inicial**, somente leitura.
5. **Dry-run** e **aplicação exclusiva** de `20261025090000` (`scripts/supabase_migrations.py aplicar --versoes 20261025090000`). Aplicada uma única vez; nada pendente.
6. **Conferência da regra:**
   - existe **um único** índice sobre `(item_despesa_id, cartao_competencia)`;
   - a definição é idêntica à aprovada:
     ```
     CREATE UNIQUE INDEX ux_conta_fatura_cartao_competencia ON public.conta USING btree (item_despesa_id, cartao_competencia) WHERE is_fatura_cartao
     ```
   - `gerar_mes_interno` continua sem EXECUTE para `authenticated` e `anon`.
7. **Dados fictícios** (perfis → contas → recorrência → MVP). O novo gerador ficou só no Perfil B temporário.
8. **E2E real** (Auth e Data API reais): **30/30**, já com a migration aplicada.
9. **Concorrência real** (`scripts/supabase_fatura_concorrencia_real.py`): processos Flask reais apontando para o banco de teste, pausados em barreira, e o novo aplicativo chamado pela Data API com login real. Resultados na §2.
10. **Diagnóstico após os testes:** 18 faturas fictícias e **0 grupos duplicados**.
11. **Limpeza em ordem inversa:**
    - 23 identidades, 5 execuções, 7 compras, 36 contas (inclusive as 18 faturas), 4 itens e a atribuição do gerador com o histórico;
    - depois, os seeds de contas, perfis e MVP.
12. **Impressão digital final:**
    - **conteúdo, contagens de `public`, Auth, Alembic (`c4f7a2d91b3e`) e tabelas novas (vazias) idênticos**;
    - mudou só a lista de migrations (+`20261025090000`);
    - o índice permanece; diagnóstico final com 0 faturas.

## 2. Testes de concorrência real no Supabase de teste

Os processos Flask param **depois** de a consulta responder "não existe" e **antes** do INSERT, ou depois do INSERT e **antes** do COMMIT. Isso garante corrida real, não execução sequencial.

| Cenário | Resultado |
|---|---|
| Flask × Flask (mesma fatura) | **1 fatura**; os dois processos receberam o mesmo id |
| Fatura paga + duas compras simultâneas | Fatura paga intacta (md5); compras redirecionadas para o mês seguinte, com **1 fatura** nele |
| Novo app × novo app (duas gerações ao mesmo tempo, mesmo usuário) | Uma criou 2 faturas e a outra 0; 1 por competência |
| Flask consultou, o novo app criou e gravou primeiro | O Flask recebeu a fatura do novo app |
| Flask inseriu sem commit, o novo app tentou | O novo app **ficou esperando** a trava do índice e, após o commit do Flask, contou a fatura como existente; criou só a do mês seguinte |
| Compras parceladas 2x simultâneas | 1 fatura em cada mês; 4 parcelas; cada compra soma 300,00 |
| Geração de recorrências + compra no mesmo mês | 1 fatura; a compra está nela |
| Chamadas repetidas | A nova geração criou 0; o Flask devolveu a mesma fatura |
| Isolamento | A → Perfil B: `gerar_mes`/`previa_geracao` **403/403**; B → Pessoal: **403**; A → Pessoal (gerador Flask): **400** "ainda é feita pelo sistema atual" |
| Duplicidades | 0 grupos de fatura duplicada; 0 parcelas duplicadas (`compra_id` + parcela) |
| Saldos e movimentos | `movimento_financeiro` = 0 e `conta_bancaria` inalterada durante todo o teste |

**Critério de aceite atendido:**
- aplicada uma vez;
- uma fatura por cartão e competência;
- as demais contas preservadas;
- compatível com o Flask;
- operações concorrentes recebem a fatura existente;
- nenhuma alteração inesperada de dados financeiros.

## 3. Uma única regra, qualquer que seja o mecanismo

A observação do usuário: o banco deve ter um único índice, independentemente do mecanismo de migrations usado.

- O `IF NOT EXISTS` compara só o nome. Por isso a migration Alembic `d81f5a2b9c3e` passou a **conferir a definição** de um índice já existente:
  - igual à aprovada: não faz nada;
  - diferente (mesmo nome, outra regra): **aborta sem alterar nada**.
- **Testes locais:**
  - o `create_all` do model, a migration do Supabase e a Alembic produzem **exatamente** a definição aprovada (a mesma do remoto);
  - em qualquer ordem resta **um** índice;
  - um índice homônimo com outra regra faz a Alembic abortar (PostgreSQL e SQLite).
- A migration do Supabase já aplicada não foi editada.
- No remoto, a Alembic continua em `c4f7a2d91b3e`. Quando ela for aplicada (com autorização), vai encontrar a mesma definição e não fará nada.

## 4. Arquivos desta etapa

- `scripts/supabase_fatura_concorrencia_real.py` (novo): concorrência real no banco de teste, só com dados fictícios.
- `migrations/versions/d81f5a2b9c3e_fatura_unica_cartao_competencia.py`: conferência da definição existente.
- `tests/test_supabase_fatura_unica.py` e `tests/test_fatura_unica_flask.py`: testes de regra única.
- `docs/FIN_FATURA_UNICA_REAL_1.md` e `docs/ROADMAP.md`.

## 5. Suíte completa

**1229 passaram, 19 pulados, 5 falhas** — exatamente as 5 que já falhavam desde `0e04407`. Nenhuma regressão.
