-- FIN-RECORRENCIA-T1 — gerador unico de recorrencias por perfil financeiro.
--
-- NAO aplicar no Supabase remoto sem autorizacao especifica
-- (scripts/supabase_migrations.py aplicar --versoes 20261023090000 20261024090000).
-- Depende de 20261023090000 (FIN-RECORRENCIA-1). Validada em cluster local
-- descartavel com o Flask real (tests/test_supabase_gerador_t1.py).
--
-- Regras:
-- - padrao: FLASK (perfil sem linha). Nenhum perfil muda sozinho;
-- - so administrador troca (definir_gerador_recorrencia: sem EXECUTE para anon e
--   authenticated; tabela sem privilegios para eles). Toda alteracao, inclusive SQL
--   direto, fica no historico por gatilho;
-- - NOVO: o Flask nao gera (backend/services/gerador_recorrencia_service.py) e o novo
--   motor gera; FLASK: o inverso. A verificacao e feita no banco a cada geracao;
-- - concorrencia: geracao do novo motor e troca usam a trava consultiva EXCLUSIVA
--   (20261023, perfil); o Flask usa a COMPARTILHADA. Uma troca espera geracoes em
--   andamento; a geracao do novo motor ainda prende a linha (FOR SHARE).
-- Nenhuma conta existente e alterada ou apagada.

create table financeiro.gerador_recorrencia (
    perfil_financeiro_id integer     primary key,
    gerador              text        not null check (gerador in ('FLASK', 'NOVO')),
    alterado_em          timestamptz not null default now(),
    alterado_por         text        not null check (btrim(alterado_por) <> ''),
    motivo               text        not null check (btrim(motivo) <> '')
);

comment on table financeiro.gerador_recorrencia is
    'FIN-RECORRENCIA-T1: qual sistema gera recorrencias e faturas de cada perfil. Sem linha = FLASK. So administrador altera.';

create table financeiro.gerador_recorrencia_historico (
    id                   bigint      generated always as identity primary key,
    perfil_financeiro_id integer     not null,
    gerador_anterior     text,
    gerador_novo         text,
    alterado_por         text,
    motivo               text,
    papel_banco          text        not null default current_user,
    registrado_em        timestamptz not null default now()
);

alter table financeiro.gerador_recorrencia enable row level security;
alter table financeiro.gerador_recorrencia force row level security;
alter table financeiro.gerador_recorrencia_historico enable row level security;
alter table financeiro.gerador_recorrencia_historico force row level security;
revoke all on financeiro.gerador_recorrencia from public, anon, authenticated;
revoke all on financeiro.gerador_recorrencia_historico from public, anon, authenticated;

create function financeiro.auditar_gerador_recorrencia()
    returns trigger
    language plpgsql
    security definer
    set search_path = ''
as $$
begin
    insert into financeiro.gerador_recorrencia_historico
        (perfil_financeiro_id, gerador_anterior, gerador_novo, alterado_por, motivo, papel_banco)
    values (coalesce(new.perfil_financeiro_id, old.perfil_financeiro_id),
            case when tg_op <> 'INSERT' then old.gerador end,
            case when tg_op <> 'DELETE' then new.gerador end,
            case when tg_op <> 'DELETE' then new.alterado_por end,
            case when tg_op <> 'DELETE' then new.motivo else 'Configuracao removida (volta ao padrao FLASK)' end,
            session_user);
    return null;
end
$$;

create trigger gerador_recorrencia_auditoria
    after insert or update or delete on financeiro.gerador_recorrencia
    for each row execute function financeiro.auditar_gerador_recorrencia();

-- Unica forma prevista de trocar o gerador (administrador, SQL Editor/CLI).
create function financeiro.definir_gerador_recorrencia(p_perfil_id integer, p_gerador text,
                                                       p_responsavel text, p_motivo text)
    returns text
    language plpgsql
    security invoker
    set search_path = ''
as $$
declare
    v_anterior text;
begin
    if p_gerador not in ('FLASK', 'NOVO') then
        raise exception 'Gerador invalido: use FLASK ou NOVO' using errcode = '22023';
    end if;
    if nullif(btrim(p_responsavel), '') is null or nullif(btrim(p_motivo), '') is null then
        raise exception 'Responsavel e motivo sao obrigatorios (auditoria)' using errcode = '22023';
    end if;
    if not exists (select 1 from public.perfil_financeiro p where p.id = p_perfil_id) then
        raise exception 'Perfil financeiro inexistente' using errcode = '22023';
    end if;
    -- Espera geracoes em andamento (Flask: trava compartilhada; novo motor: exclusiva).
    perform pg_advisory_xact_lock(20261023, p_perfil_id);
    select g.gerador into v_anterior from financeiro.gerador_recorrencia g
     where g.perfil_financeiro_id = p_perfil_id for update;
    insert into financeiro.gerador_recorrencia (perfil_financeiro_id, gerador, alterado_em, alterado_por, motivo)
    values (p_perfil_id, p_gerador, now(), btrim(p_responsavel), btrim(p_motivo))
    on conflict (perfil_financeiro_id) do update
       set gerador = excluded.gerador, alterado_em = excluded.alterado_em,
           alterado_por = excluded.alterado_por, motivo = excluded.motivo;
    return format('Perfil %s: %s -> %s', p_perfil_id, coalesce(v_anterior, 'FLASK (padrao)'), p_gerador);
end
$$;

-- Gerador efetivo (sem linha = FLASK). Interna.
create function financeiro.gerador_do_perfil(p_perfil_id integer)
    returns text
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select coalesce((select g.gerador from financeiro.gerador_recorrencia g
                      where g.perfil_financeiro_id = p_perfil_id), 'FLASK')
$$;

-- O novo motor so escreve em perfil atribuido a ele. As funcoes do FIN-RECORRENCIA-1
-- passam a ser internas; as publicas validam gestao, gerador e travam a troca.
alter function financeiro.gerar_mes(integer, date, integer, jsonb) rename to gerar_mes_interno;
alter function financeiro.reativar_competencia(integer, text, integer, date) rename to reativar_competencia_interno;
alter function financeiro.previa_geracao(integer, date) rename to previa_geracao_interna;
revoke execute on function financeiro.gerar_mes_interno(integer, date, integer, jsonb) from public, anon, authenticated;
revoke execute on function financeiro.reativar_competencia_interno(integer, text, integer, date) from public, anon, authenticated;
revoke execute on function financeiro.previa_geracao_interna(integer, date) from public, anon, authenticated;

create function financeiro.exigir_gerador_novo(p_perfil_id integer)
    returns void
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_gerador text;
begin
    -- Mesma ordem da troca: trava consultiva, depois a linha (FOR SHARE ate o commit).
    perform pg_advisory_xact_lock(20261023, p_perfil_id);
    select g.gerador into v_gerador from financeiro.gerador_recorrencia g
     where g.perfil_financeiro_id = p_perfil_id for share;
    if v_gerador is distinct from 'NOVO' then
        raise exception 'A geracao deste perfil ainda e feita pelo sistema atual (Flask)'
            using errcode = 'P0001', hint = 'GERADOR_FLASK';
    end if;
end
$$;

create function financeiro.gerar_mes(p_perfil_id integer, p_mes date, p_total_previsto integer,
                                     p_dispensar jsonb default '[]'::jsonb)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
begin
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    perform financeiro.exigir_gerador_novo(p_perfil_id);
    return financeiro.gerar_mes_interno(p_perfil_id, p_mes, p_total_previsto, p_dispensar);
end
$$;

create function financeiro.reativar_competencia(p_perfil_id integer, p_natureza text, p_item_id integer,
                                                p_competencia date)
    returns boolean
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
begin
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    perform financeiro.exigir_gerador_novo(p_perfil_id);
    return financeiro.reativar_competencia_interno(p_perfil_id, p_natureza, p_item_id, p_competencia);
end
$$;

create function financeiro.previa_geracao(p_perfil_id integer, p_mes date)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_previa  jsonb;
    v_gerador text;
begin
    v_previa := financeiro.previa_geracao_interna(p_perfil_id, p_mes);  -- autoriza (42501)
    v_gerador := financeiro.gerador_do_perfil(p_perfil_id);
    return v_previa || jsonb_build_object(
        'gerador', v_gerador,
        'pode_gerir', (v_previa ->> 'pode_gerar')::boolean,
        'pode_gerar', (v_previa ->> 'pode_gerar')::boolean and v_gerador = 'NOVO');
end
$$;

revoke execute on function financeiro.auditar_gerador_recorrencia() from public, anon, authenticated;
revoke execute on function financeiro.definir_gerador_recorrencia(integer, text, text, text) from public, anon, authenticated;
revoke execute on function financeiro.gerador_do_perfil(integer) from public, anon, authenticated;
revoke execute on function financeiro.exigir_gerador_novo(integer) from public, anon, authenticated;
revoke execute on function financeiro.gerar_mes(integer, date, integer, jsonb) from public, anon;
revoke execute on function financeiro.reativar_competencia(integer, text, integer, date) from public, anon;
revoke execute on function financeiro.previa_geracao(integer, date) from public, anon;
grant execute on function financeiro.gerar_mes(integer, date, integer, jsonb) to authenticated;
grant execute on function financeiro.reativar_competencia(integer, text, integer, date) to authenticated;
grant execute on function financeiro.previa_geracao(integer, date) to authenticated;
