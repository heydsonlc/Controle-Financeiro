-- Reversao de 20261217090000 (FIN-MOB-ABAST-LANCAMENTOS-01): remove as tres funcoes novas. Nenhuma tabela ou valor muda;
-- as despesas e os abastecimentos ja gravados e os seus vinculos ficam. So com autorizacao, retirando a versao de
-- supabase_migrations.schema_migrations.
drop function financeiro.salvar_lancamento_abastecimento(integer, jsonb, uuid);
drop function financeiro.abastecimento_do_lancamento(integer, integer, integer);
drop function financeiro.formulario_abastecimento_lancamento(integer);
