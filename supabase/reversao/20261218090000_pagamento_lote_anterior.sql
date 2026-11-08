-- Reversao de 20261218090000 (FIN-DESPESAS-PAGAMENTO-LOTE-01): remove a funcao nova. Nenhuma tabela ou valor muda; os
-- pagamentos ja feitos (movimentos e registros) ficam. So com autorizacao, retirando a versao de
-- supabase_migrations.schema_migrations.
drop function financeiro.pagar_despesas_lote(integer, jsonb, uuid);
