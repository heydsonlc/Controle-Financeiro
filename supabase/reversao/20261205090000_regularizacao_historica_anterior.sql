-- Reversao de 20261205090000 (regularizacao historica): remove as funcoes e a tabela de auditoria. Recusada enquanto
-- houver lote nao revertido (reverter antes com financeiro.reverter_regularizacao_historica), para nao perder o estado
-- anterior dos itens. So com autorizacao, retirando a versao de supabase_migrations.schema_migrations.

do $$
begin
    if exists (select 1 from financeiro.regularizacao_historica where revertido_em is null) then
        raise exception 'Ha regularizacao historica vigente: reverta os lotes antes de remover a migration 20261205090000';
    end if;
end
$$;

drop function if exists financeiro.reverter_regularizacao_historica(integer, uuid, uuid);
drop function if exists financeiro.regularizar_historico(integer, jsonb, uuid);
drop function if exists financeiro.plano_regularizacao_historica(integer, date);
drop table if exists financeiro.regularizacao_historica;
