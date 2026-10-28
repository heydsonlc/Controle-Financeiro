-- FIN-PRE-PRODUCAO-1 (2.1) — Indexadores: cadastro e consulta da TR mensal dos financiamentos SAC/TR no novo aplicativo.
--
-- NAO aplicar no Supabase remoto sem autorizacao especifica
-- (scripts/supabase_migrations.py aplicar --versoes 20261129090000).
-- Depende de 20261123090000 (motor de financiamentos: fin_tr le public.indice_tr_mensal) e de 20261023090000
-- (perfil_acesso.pode_gerir). Validada em cluster local descartavel (tests/test_supabase_indexadores.py, comparada com o
-- Flask). Docs: docs/FIN_PRE_PRODUCAO_1.md.
--
-- Reproduz backend/services/indice_tr_service.py (rotas /api/indexadores/tr de routes/indexadores.py): listar (filtro por
-- ano ou intervalo de competencias), cadastrar, editar, importar por texto e competencias faltantes, com as mesmas
-- validacoes e mensagens: competencia YYYY-MM, valor em percentual mensal (0,16 -> 0.0016, 8 casas, arredondamento
-- para cima no meio), entre 0 e 10%, e a TR ja usada em parcela de financiamento SAC/TR nao pode ser alterada.
-- Nenhum valor de TR e criado por esta migration: so o que o usuario informa.
--
-- A TR e uma so para todos os perfis, como no Flask (public.indice_tr_mensal nao tem perfil). Por isso:
-- - consultar exige um perfil autorizado; gravar exige gerir um perfil ativo (pode_gerir);
-- - cada gravacao fica em financeiro.indice_tr_historico (quem, quando, valor anterior e novo);
-- - cadastrar e importar levam chave de idempotencia (reenvio nao duplica).
-- Fora do escopo (docs): a secao generica "Indexadores Mensais" (IPCA, IGP-M...) do Flask, que nao e usada em nenhum
-- calculo e nao tem dados em nenhuma base.
-- Duas tabelas novas (vazias). Nenhum dado existente e alterado.

create table financeiro.operacao_indexador (
    chave     uuid        primary key,
    user_id   uuid        not null references auth.users (id) on delete cascade,
    operacao  text        not null,
    resultado jsonb       not null,
    criado_em timestamptz not null default now()
);
comment on table financeiro.operacao_indexador is
    'FIN-PRE-PRODUCAO-1: resultado de cada cadastro/importacao de TR por chave (reenvio nao duplica).';
alter table financeiro.operacao_indexador enable row level security;
alter table financeiro.operacao_indexador force row level security;
revoke all on financeiro.operacao_indexador from public, anon, authenticated;

create table financeiro.indice_tr_historico (
    id             bigint      generated always as identity primary key,
    competencia    text        not null,
    operacao       text        not null check (operacao in ('CADASTRO', 'EDICAO', 'IMPORTACAO')),
    valor_anterior numeric,
    valor_novo     numeric     not null,
    fonte_anterior text,
    fonte_nova     text,
    user_id        uuid        not null,
    criado_em      timestamptz not null default now()
);
comment on table financeiro.indice_tr_historico is
    'FIN-PRE-PRODUCAO-1: auditoria das gravacoes da TR (indice unico para todos os perfis).';
alter table financeiro.indice_tr_historico enable row level security;
alter table financeiro.indice_tr_historico force row level security;
revoke all on financeiro.indice_tr_historico from public, anon, authenticated;

-- Consulta: qualquer perfil autorizado. Gravacao: gerir um perfil ativo.
create function financeiro.idx_exigir_acesso(p_gravar boolean)
    returns void
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
begin
    if not exists (select 1 from financeiro.perfil_acesso a join public.perfil_financeiro p on p.id = a.perfil_financeiro_id
                    where a.user_id = (select auth.uid()) and (not p_gravar or (a.pode_gerir and p.ativo))) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
end
$$;

-- IndiceTRService.validar_competencia.
create function financeiro.idx_competencia(p_competencia text)
    returns text
    language plpgsql
    immutable
    set search_path = ''
as $$
declare
    v text := btrim(coalesce(p_competencia, ''));
begin
    if v !~ '^\d{4}-\d{2}$' then
        raise exception 'Competência deve estar no formato YYYY-MM' using errcode = '22023';
    end if;
    if substr(v, 6, 2)::integer not between 1 and 12 then
        raise exception 'Mês da competência deve estar entre 1 e 12' using errcode = '22023';
    end if;
    return v;
end
$$;

-- IndiceTRService.valor_percentual_para_decimal (texto: sem %, sem espacos, virgula decimal).
create function financeiro.idx_decimal(p_valor text)
    returns numeric
    language plpgsql
    immutable
    set search_path = ''
as $$
declare
    v_texto text;
    v_pct   numeric;
begin
    if p_valor is null or p_valor = '' then
        raise exception 'valor_percentual é obrigatório' using errcode = '22023';
    end if;
    v_texto := replace(replace(replace(btrim(p_valor), '%', ''), ' ', ''), ',', '.');
    if v_texto !~ '^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$' then
        raise exception 'valor_percentual deve ser numérico' using errcode = '22023';
    end if;
    v_pct := v_texto::numeric;
    if v_pct < 0 then
        raise exception 'valor_percentual não pode ser negativo' using errcode = '22023';
    end if;
    if v_pct > 10 then
        raise exception 'valor_percentual não pode ser maior que 10%% ao mês' using errcode = '22023';
    end if;
    return round(v_pct / 100, 8);
end
$$;

-- IndiceTRService.tr_usada_em_financiamento: parcela vencendo na competencia de um financiamento SAC/TR (qualquer perfil).
create function financeiro.idx_tr_usada(p_competencia text)
    returns boolean
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select exists (
        select 1 from public.financiamento_parcela fp join public.financiamento f on f.id = fp.financiamento_id
         where fp.data_vencimento >= to_date(p_competencia || '-01', 'YYYY-MM-DD')
           and fp.data_vencimento < to_date(p_competencia || '-01', 'YYYY-MM-DD') + interval '1 month'
           and ((upper(f.sistema_amortizacao) = 'SAC' and upper(f.indexador_saldo) = 'TR')
                or f.modo_calculo_financiamento = 'caixa_sac_tr'))
$$;

-- IndiceTRService._to_dict.
create function financeiro.idx_tr_json(p_i public.indice_tr_mensal)
    returns jsonb
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select jsonb_build_object(
        'id', p_i.id, 'ano', p_i.ano, 'mes', p_i.mes, 'competencia', p_i.competencia,
        'valor_decimal', coalesce(p_i.valor_decimal, 0), 'fonte', p_i.fonte,
        'criado_em', to_char(p_i.criado_em, 'YYYY-MM-DD HH24:MI:SS'),
        'atualizado_em', to_char(p_i.atualizado_em, 'YYYY-MM-DD HH24:MI:SS'),
        'valor_percentual', round(coalesce(p_i.valor_decimal, 0) * 100, 4),
        'usada_em_financiamento', financeiro.idx_tr_usada(p_i.competencia))
$$;

create function financeiro.idx_auditar(p_competencia text, p_operacao text, p_anterior numeric, p_novo numeric,
                                       p_fonte_anterior text, p_fonte_nova text)
    returns void
    language sql
    volatile
    security definer
    set search_path = ''
as $$
    insert into financeiro.indice_tr_historico (competencia, operacao, valor_anterior, valor_novo, fonte_anterior, fonte_nova, user_id)
    values (p_competencia, p_operacao, p_anterior, p_novo, p_fonte_anterior, p_fonte_nova, (select auth.uid()))
$$;

create function financeiro.idx_repeticao(p_chave uuid, p_operacao text)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_anterior financeiro.operacao_indexador;
begin
    if p_chave is null then
        raise exception 'Chave da operacao obrigatoria' using errcode = '22023';
    end if;
    perform pg_advisory_xact_lock(hashtextextended(p_chave::text, 20261129));
    select * into v_anterior from financeiro.operacao_indexador o where o.chave = p_chave;
    if not found then
        return null;
    end if;
    if v_anterior.user_id is distinct from (select auth.uid()) or v_anterior.operacao <> p_operacao then
        raise exception 'Chave da operacao ja usada' using errcode = '22023';
    end if;
    return v_anterior.resultado || jsonb_build_object('repetida', true);
end
$$;

-- Uma gravacao de TR por vez (cadastro, edicao e importacao concorrentes da mesma competencia).
create function financeiro.idx_travar()
    returns void
    language sql
    volatile
    security definer
    set search_path = ''
as $$
    select pg_advisory_xact_lock(20261129, 1)
$$;

-- GET /api/indexadores/tr (?ano, ?inicio, ?fim): mais recentes primeiro.
create function financeiro.tr_oficial_tela(p_ano integer default null, p_inicio text default null, p_fim text default null)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_inicio text := case when coalesce(p_inicio, '') <> '' then financeiro.idx_competencia(p_inicio) end;
    v_fim    text := case when coalesce(p_fim, '') <> '' then financeiro.idx_competencia(p_fim) end;
begin
    perform financeiro.idx_exigir_acesso(false);
    return coalesce((
        select jsonb_agg(financeiro.idx_tr_json(i) order by i.competencia desc)
          from public.indice_tr_mensal i
         where (p_ano is null or i.ano = p_ano)
           and (v_inicio is null or i.competencia >= v_inicio)
           and (v_fim is null or i.competencia <= v_fim)), '[]'::jsonb);
end
$$;

-- GET /api/indexadores/tr/faltantes?inicio&fim.
create function financeiro.tr_faltantes(p_inicio text, p_fim text)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_inicio text := financeiro.idx_competencia(p_inicio);
    v_fim    text := financeiro.idx_competencia(p_fim);
begin
    perform financeiro.idx_exigir_acesso(false);
    if v_inicio > v_fim then
        raise exception 'Competência inicial deve ser menor ou igual à final' using errcode = '22023';
    end if;
    return coalesce((
        select jsonb_agg(to_char(m, 'YYYY-MM') order by m)
          from generate_series(to_date(v_inicio || '-01', 'YYYY-MM-DD'), to_date(v_fim || '-01', 'YYYY-MM-DD'),
                               interval '1 month') m
         where not exists (select 1 from public.indice_tr_mensal i where i.competencia = to_char(m, 'YYYY-MM'))), '[]'::jsonb);
end
$$;

-- POST /api/indexadores/tr {competencia, valor_percentual, fonte}.
create function financeiro.criar_tr(p_dados jsonb, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_rep   jsonb;
    v_comp  text;
    v_valor numeric;
    v_fonte text := coalesce(nullif(p_dados ->> 'fonte', ''), 'BACEN');
    v_i     public.indice_tr_mensal;
    v_agora timestamp := (now() at time zone 'utc')::timestamp;
begin
    perform financeiro.idx_exigir_acesso(true);
    v_rep := financeiro.idx_repeticao(p_chave, 'CRIAR_TR');
    if v_rep is not null then
        return v_rep;
    end if;
    perform financeiro.idx_travar();
    v_comp := financeiro.idx_competencia(p_dados ->> 'competencia');
    if exists (select 1 from public.indice_tr_mensal i where i.competencia = v_comp) then
        raise exception 'TR da competência % já cadastrada', v_comp using errcode = '22023';
    end if;
    v_valor := financeiro.idx_decimal(p_dados ->> 'valor_percentual');
    insert into public.indice_tr_mensal (ano, mes, competencia, valor_decimal, fonte, criado_em, atualizado_em)
    values (substr(v_comp, 1, 4)::integer, substr(v_comp, 6, 2)::integer, v_comp, v_valor, v_fonte, v_agora, v_agora)
    returning * into v_i;
    perform financeiro.idx_auditar(v_comp, 'CADASTRO', null, v_valor, null, v_fonte);
    insert into financeiro.operacao_indexador (chave, user_id, operacao, resultado)
    values (p_chave, (select auth.uid()), 'CRIAR_TR', jsonb_build_object('data', financeiro.idx_tr_json(v_i)));
    return jsonb_build_object('data', financeiro.idx_tr_json(v_i));
end
$$;

-- PUT /api/indexadores/tr/<competencia> {valor_percentual, fonte}: so TR ainda nao usada em financiamento SAC/TR.
create function financeiro.editar_tr(p_competencia text, p_dados jsonb)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_comp  text;
    v_i     public.indice_tr_mensal;
    v_valor numeric;
    v_fonte text;
begin
    perform financeiro.idx_exigir_acesso(true);
    perform financeiro.idx_travar();
    v_comp := financeiro.idx_competencia(p_competencia);
    select * into v_i from public.indice_tr_mensal i where i.competencia = v_comp for update;
    if not found then
        raise exception 'TR da competência % não encontrada', v_comp using errcode = '22023';
    end if;
    if financeiro.idx_tr_usada(v_comp) then
        raise exception 'Esta TR já é usada em parcelas de financiamento SAC/TR. Para alterar, será necessário revisar ou recalcular os cronogramas afetados em uma etapa própria.'
            using errcode = '22023';
    end if;
    v_valor := financeiro.idx_decimal(p_dados ->> 'valor_percentual');
    v_fonte := case when p_dados ? 'fonte' and p_dados -> 'fonte' <> 'null'::jsonb
                    then coalesce(nullif(p_dados ->> 'fonte', ''), 'BACEN') else v_i.fonte end;
    perform financeiro.idx_auditar(v_comp, 'EDICAO', v_i.valor_decimal, v_valor, v_i.fonte, v_fonte);
    update public.indice_tr_mensal i
       set valor_decimal = v_valor, fonte = v_fonte, atualizado_em = (now() at time zone 'utc')::timestamp
     where i.id = v_i.id
    returning * into strict v_i;
    return jsonb_build_object('data', financeiro.idx_tr_json(v_i));
end
$$;

-- POST /api/indexadores/tr/importar {texto, fonte, sobrescrever}: linhas "YYYY-MM;valor"; erros por linha nao
-- impedem as demais (como o Flask, que grava as validas no fim).
create function financeiro.importar_tr(p_dados jsonb, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_rep       jsonb;
    v_texto     text := p_dados ->> 'texto';
    v_fonte     text := coalesce(nullif(p_dados ->> 'fonte', ''), 'BACEN');
    v_sobre     boolean := coalesce((p_dados ->> 'sobrescrever')::boolean, false);
    v_linha     record;
    v_conteudo  text;
    v_partes    text[];
    v_comp      text;
    v_valor     numeric;
    v_i         public.indice_tr_mensal;
    v_criados   integer := 0;
    v_atual     integer := 0;
    v_ignorados integer := 0;
    v_erros     jsonb := '[]'::jsonb;
    v_agora     timestamp := (now() at time zone 'utc')::timestamp;
    v_resultado jsonb;
begin
    perform financeiro.idx_exigir_acesso(true);
    v_rep := financeiro.idx_repeticao(p_chave, 'IMPORTAR_TR');
    if v_rep is not null then
        return v_rep;
    end if;
    if v_texto is null or btrim(v_texto) = '' then
        raise exception 'texto é obrigatório' using errcode = '22023';
    end if;
    perform financeiro.idx_travar();
    for v_linha in select t.conteudo, t.numero
                     from regexp_split_to_table(v_texto, E'\r\n|\n|\r') with ordinality as t(conteudo, numero) loop
        v_conteudo := btrim(v_linha.conteudo, E' \t\f\v');
        continue when v_conteudo = '' or lower(v_conteudo) like 'competencia%';
        v_partes := regexp_match(v_conteudo, '^(\d{4}-\d{2})\s*[;,]\s*(.+)$');
        if v_partes is null then
            v_erros := v_erros || jsonb_build_object('linha', v_linha.numero, 'conteudo', v_conteudo,
                                                     'erro', 'Linha deve estar no formato YYYY-MM;valor_percentual');
            continue;
        end if;
        begin
            v_comp := financeiro.idx_competencia(v_partes[1]);
            v_valor := financeiro.idx_decimal(btrim(v_partes[2]));
            select * into v_i from public.indice_tr_mensal i where i.competencia = v_comp for update;
            if found then
                if not v_sobre then
                    v_ignorados := v_ignorados + 1;
                    continue;
                end if;
                if financeiro.idx_tr_usada(v_comp) then
                    raise exception 'Esta TR já é usada em parcelas de financiamento SAC/TR. Para alterar, será necessário revisar ou recalcular os cronogramas afetados em uma etapa própria.'
                        using errcode = '22023';
                end if;
                update public.indice_tr_mensal i set valor_decimal = v_valor, fonte = v_fonte, atualizado_em = v_agora
                 where i.id = v_i.id;
                perform financeiro.idx_auditar(v_comp, 'IMPORTACAO', v_i.valor_decimal, v_valor, v_i.fonte, v_fonte);
                v_atual := v_atual + 1;
                continue;
            end if;
            insert into public.indice_tr_mensal (ano, mes, competencia, valor_decimal, fonte, criado_em, atualizado_em)
            values (substr(v_comp, 1, 4)::integer, substr(v_comp, 6, 2)::integer, v_comp, v_valor, v_fonte, v_agora, v_agora);
            perform financeiro.idx_auditar(v_comp, 'IMPORTACAO', null, v_valor, null, v_fonte);
            v_criados := v_criados + 1;
        exception when sqlstate '22023' then
            v_erros := v_erros || jsonb_build_object('linha', v_linha.numero, 'conteudo', v_conteudo, 'erro', sqlerrm);
        end;
    end loop;
    v_resultado := jsonb_build_object('criados', v_criados, 'atualizados', v_atual, 'ignorados', v_ignorados, 'erros', v_erros);
    insert into financeiro.operacao_indexador (chave, user_id, operacao, resultado)
    values (p_chave, (select auth.uid()), 'IMPORTAR_TR', v_resultado);
    return v_resultado;
end
$$;

revoke execute on function financeiro.idx_exigir_acesso(boolean) from public, anon, authenticated;
revoke execute on function financeiro.idx_competencia(text) from public, anon, authenticated;
revoke execute on function financeiro.idx_decimal(text) from public, anon, authenticated;
revoke execute on function financeiro.idx_tr_usada(text) from public, anon, authenticated;
revoke execute on function financeiro.idx_tr_json(public.indice_tr_mensal) from public, anon, authenticated;
revoke execute on function financeiro.idx_auditar(text, text, numeric, numeric, text, text) from public, anon, authenticated;
revoke execute on function financeiro.idx_repeticao(uuid, text) from public, anon, authenticated;
revoke execute on function financeiro.idx_travar() from public, anon, authenticated;
revoke execute on function financeiro.tr_oficial_tela(integer, text, text) from public, anon;
revoke execute on function financeiro.tr_faltantes(text, text) from public, anon;
revoke execute on function financeiro.criar_tr(jsonb, uuid) from public, anon;
revoke execute on function financeiro.editar_tr(text, jsonb) from public, anon;
revoke execute on function financeiro.importar_tr(jsonb, uuid) from public, anon;
grant execute on function financeiro.tr_oficial_tela(integer, text, text) to authenticated;
grant execute on function financeiro.tr_faltantes(text, text) to authenticated;
grant execute on function financeiro.criar_tr(jsonb, uuid) to authenticated;
grant execute on function financeiro.editar_tr(text, jsonb) to authenticated;
grant execute on function financeiro.importar_tr(jsonb, uuid) to authenticated;
