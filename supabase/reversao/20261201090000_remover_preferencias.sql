-- Reversao de 20261201090000_financeiro_preferencias.sql (FIN-PRE-PRODUCAO-1). Recusa se ja houver preferencias
-- gravadas (removeria configuracoes de usuarios e perfis); o Flask nao le estas tabelas.
do $$
begin
    if exists (select 1 from financeiro.preferencia_usuario) or exists (select 1 from financeiro.preferencia_perfil) then
        raise exception 'Reversao recusada: ha preferencias gravadas no novo aplicativo (exporte-as antes)';
    end if;
end
$$;

drop function if exists financeiro.salvar_preferencias(integer, jsonb);
drop function if exists financeiro.preferencias_tela(integer);
drop function if exists financeiro.pref_valor(text, jsonb);
drop function if exists financeiro.pref_campos(text);
drop table if exists financeiro.preferencia_perfil;
drop table if exists financeiro.preferencia_usuario;
