# Rascunho — pagamento e estorno de parcela de financiamento (FIN-FIDELIDADE-CONTRATOS-1, fase 2)

**Não é migration.** Fica fora de `supabase/migrations/` para que nem `scripts/supabase_migrations.py` nem o
cluster de testes (`tests/supabase_local.py`, que aplica `supabase/migrations/*.sql`) o leiam.

- `20261111090000_financeiro_financiamentos_pagamento.sql`: funções `pagar_parcela_financiamento` e
  `estornar_parcela_financiamento`, regras e correções descritas no cabeçalho.
- `rascunho_test_financiamentos_pagamento.py`: comparação com o próprio Flask em cluster descartável. O nome não
  começa com `test_` e o arquivo está fora de `tests/`: o pytest não o coleta.

**Bloqueio:** escritor único. O Flask grava parcelas sem guarda (`backend/routes/financiamentos.py`), mesmo em perfil
atribuído ao novo aplicativo (`docs/FIN_FIDELIDADE_CONTRATOS_1.md` §6, `docs/FIN_AUDITORIA_GERAL_1.md` item 3).

**Para retomar**, só depois da guarda no Flask: mover o `.sql` para `supabase/migrations/` (renomear para uma versão
posterior à última aplicada) e o teste para `tests/test_supabase_financiamentos_pagamento.py`, revisar contra o
estado atual e rodar o teste.
