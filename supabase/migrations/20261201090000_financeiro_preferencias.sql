-- FIN-PRE-PRODUCAO-1 (2.4) — Preferencias no novo aplicativo: financeiras e operacionais por perfil, gerais de interface
-- por usuario (um usuario pode ter varios perfis).
--
-- NAO aplicar no Supabase remoto sem autorizacao especifica
-- (scripts/supabase_migrations.py aplicar --versoes 20261201090000).
-- Depende de 20261021090000 (perfil_acesso) e 20261023090000 (pode_gerir_perfil). Validada em cluster local descartavel
-- (tests/test_supabase_preferencias.py). Docs: docs/FIN_PRE_PRODUCAO_1.md.
--
-- No Flask, public.preferencia e um registro unico e global (routes/preferencias.py) e nenhuma preferencia muda o
-- comportamento do sistema (so e gravada e exibida em Configuracoes). Aqui:
-- - financeiro.preferencia_perfil: renda, mes de inicio do planejamento, dia de fechamento do mes, comportamento de
--   lancamentos (competencia automatica, aviso de vencida, vinculo do pagamento de cartao), cartoes (inicio/corte da
--   fatura, lancamentos agrupados, orcamento por categoria) e automacoes que mexem em dados (classificacao automatica,
--   correcao de categorias, parcelas recorrentes). Altera so quem gere o perfil (pode_gerir);
-- - financeiro.preferencia_usuario: nome, aparencia (tema, cor, icones, abreviar valores), confirmacao de exclusoes,
--   graficos e paineis do Dashboard e modo inteligente / sugestoes de economia. Cada usuario altera as suas.
-- Os valores-padrao sao os do Flask (modelo Preferencia; nome 'Usuário' como o GET do Flask cria). A carga (scripts/carga_supabase.py) copia o registro
-- unico do Flask para o usuario titular e para cada perfil migrado (as configuracoes existentes sao preservadas).
-- Fora do escopo: backup_automatico/ultimo_backup (o novo aplicativo usa o backup do banco), sem efeito no Flask.
-- Leitura e gravacao so pelas funcoes (RLS forcada, sem acesso direto). Validacao de tipos e faixas (o Flask gravava
-- qualquer valor). Duas tabelas novas (vazias). Nenhum dado existente e alterado.

create table financeiro.preferencia_usuario (
    user_id                     uuid        primary key references auth.users (id) on delete cascade,
    nome_usuario                text        default 'Usuário' check (char_length(nome_usuario) <= 100),
    tema_sistema                text        not null default 'escuro' check (tema_sistema in ('claro', 'escuro', 'auto')),
    cor_principal               text        not null default '#3b82f6' check (cor_principal ~ '^#[0-9A-Fa-f]{6}$'),
    mostrar_icones_coloridos    boolean     not null default true,
    abreviar_valores            boolean     not null default false,
    solicitar_confirmacao_exclusao boolean  not null default true,
    graficos_visiveis           text        not null default 'categorias,evolucao,saldo' check (char_length(graficos_visiveis) <= 200),
    insights_inteligentes_ativo boolean     not null default true,
    mostrar_saldo_consolidado   boolean     not null default true,
    mostrar_evolucao_historica  boolean     not null default true,
    modo_inteligente_ativo      boolean     not null default false,
    sugestoes_economia          boolean     not null default false,
    atualizado_em               timestamptz not null default now()
);
comment on table financeiro.preferencia_usuario is
    'FIN-PRE-PRODUCAO-1: preferencias gerais de interface de cada usuario (um usuario, varios perfis).';

create table financeiro.preferencia_perfil (
    perfil_financeiro_id           integer     primary key references public.perfil_financeiro (id) on delete cascade,
    renda_principal                numeric(10, 2) check (renda_principal >= 0),
    mes_inicio_planejamento        integer     not null default 1 check (mes_inicio_planejamento between 1 and 12),
    dia_fechamento_mes             integer     not null default 1 check (dia_fechamento_mes between 1 and 31),
    ajustar_competencia_automatico boolean     not null default true,
    exibir_aviso_despesa_vencida   boolean     not null default true,
    vincular_pagamento_cartao_auto boolean     not null default true,
    dia_inicio_fatura              integer     not null default 1 check (dia_inicio_fatura between 1 and 31),
    dia_corte_fatura               integer     not null default 1 check (dia_corte_fatura between 1 and 31),
    lancamentos_agrupados          boolean     not null default false,
    orcamento_por_categoria        boolean     not null default true,
    classificacao_automatica       boolean     not null default false,
    correcao_categorias            boolean     not null default false,
    parcelas_recorrentes_auto      boolean     not null default false,
    atualizado_em                  timestamptz not null default now(),
    atualizado_por                 uuid
);
comment on table financeiro.preferencia_perfil is
    'FIN-PRE-PRODUCAO-1: preferencias financeiras e operacionais de cada perfil financeiro.';

alter table financeiro.preferencia_usuario enable row level security;
alter table financeiro.preferencia_usuario force row level security;
alter table financeiro.preferencia_perfil enable row level security;
alter table financeiro.preferencia_perfil force row level security;
revoke all on financeiro.preferencia_usuario from public, anon, authenticated;
revoke all on financeiro.preferencia_perfil from public, anon, authenticated;

-- Campos de cada escopo (as chaves do to_dict do Flask). Interna.
create function financeiro.pref_campos(p_escopo text)
    returns text[]
    language sql
    immutable
    set search_path = ''
as $$
    select case p_escopo
        when 'USUARIO' then array['nome_usuario', 'tema_sistema', 'cor_principal', 'mostrar_icones_coloridos', 'abreviar_valores',
                                  'solicitar_confirmacao_exclusao', 'graficos_visiveis', 'insights_inteligentes_ativo',
                                  'mostrar_saldo_consolidado', 'mostrar_evolucao_historica', 'modo_inteligente_ativo',
                                  'sugestoes_economia']
        else array['renda_principal', 'mes_inicio_planejamento', 'dia_fechamento_mes', 'ajustar_competencia_automatico',
                   'exibir_aviso_despesa_vencida', 'vincular_pagamento_cartao_auto', 'dia_inicio_fatura', 'dia_corte_fatura',
                   'lancamentos_agrupados', 'orcamento_por_categoria', 'classificacao_automatica', 'correcao_categorias',
                   'parcelas_recorrentes_auto'] end
$$;

-- Valida um campo enviado pela tela e devolve o valor normalizado (jsonb). Interna.
create function financeiro.pref_valor(p_campo text, p_valor jsonb)
    returns jsonb
    language plpgsql
    immutable
    set search_path = ''
as $$
declare
    v_texto text := case when jsonb_typeof(p_valor) = 'string' then btrim(p_valor #>> '{}') end;
    v_num   numeric;
begin
    if p_campo in ('mostrar_icones_coloridos', 'abreviar_valores', 'solicitar_confirmacao_exclusao', 'insights_inteligentes_ativo',
                   'mostrar_saldo_consolidado', 'mostrar_evolucao_historica', 'modo_inteligente_ativo', 'sugestoes_economia',
                   'ajustar_competencia_automatico', 'exibir_aviso_despesa_vencida', 'vincular_pagamento_cartao_auto',
                   'lancamentos_agrupados', 'orcamento_por_categoria', 'classificacao_automatica', 'correcao_categorias',
                   'parcelas_recorrentes_auto') then
        if p_valor is null or jsonb_typeof(p_valor) is distinct from 'boolean' then
            raise exception 'Preferencia %: use verdadeiro ou falso', p_campo using errcode = '22023';
        end if;
        return p_valor;
    end if;
    if p_campo = 'nome_usuario' then
        if p_valor is null or jsonb_typeof(p_valor) = 'null' or v_texto = '' then
            return 'null'::jsonb;
        end if;
        if v_texto is null or char_length(v_texto) > 100 then
            raise exception 'Nome do usuario: texto de ate 100 caracteres' using errcode = '22023';
        end if;
        return to_jsonb(v_texto);
    end if;
    if p_campo = 'tema_sistema' then
        if v_texto is null or v_texto not in ('claro', 'escuro', 'auto') then
            raise exception 'Tema do sistema: claro, escuro ou auto' using errcode = '22023';
        end if;
        return to_jsonb(v_texto);
    end if;
    if p_campo = 'cor_principal' then
        if v_texto is null or v_texto !~ '^#[0-9A-Fa-f]{6}$' then
            raise exception 'Cor principal: use o formato #RRGGBB' using errcode = '22023';
        end if;
        return to_jsonb(lower(v_texto));
    end if;
    if p_campo = 'graficos_visiveis' then
        if v_texto is null or char_length(v_texto) > 200 then
            raise exception 'Graficos visiveis: lista de ate 200 caracteres' using errcode = '22023';
        end if;
        return to_jsonb(v_texto);
    end if;
    -- Numeros: renda (>= 0, vazio = sem renda), mes (1-12) e dias (1-31).
    if p_valor is null or jsonb_typeof(p_valor) = 'null' or v_texto = '' then
        if p_campo = 'renda_principal' then
            return 'null'::jsonb;
        end if;
        raise exception 'Preferencia %: informe um numero', p_campo using errcode = '22023';
    end if;
    begin
        v_num := coalesce(v_texto, p_valor #>> '{}')::numeric;
    exception when others then
        raise exception 'Preferencia %: informe um numero', p_campo using errcode = '22023';
    end;
    if p_campo = 'renda_principal' then
        if v_num < 0 or v_num >= 100000000 then
            raise exception 'Renda principal: valor entre 0 e 99.999.999,99' using errcode = '22023';
        end if;
        return to_jsonb(round(v_num, 2));
    end if;
    if v_num <> trunc(v_num) or v_num < 1 or v_num > (case when p_campo = 'mes_inicio_planejamento' then 12 else 31 end) then
        raise exception 'Preferencia %: fora da faixa permitida', p_campo using errcode = '22023';
    end if;
    return to_jsonb(v_num::integer);
end
$$;

-- GET /api/preferencias (formato do to_dict do Flask) + escopo de cada campo e se o usuario gere o perfil.
create function financeiro.preferencias_tela(p_perfil_id integer)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_usuario jsonb;
    v_perfil  jsonb;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    select to_jsonb(u) - 'user_id' - 'atualizado_em' into v_usuario from financeiro.preferencia_usuario u where u.user_id = (select auth.uid());
    if v_usuario is null then
        v_usuario := jsonb_build_object(
            'nome_usuario', 'Usuário', 'tema_sistema', 'escuro', 'cor_principal', '#3b82f6', 'mostrar_icones_coloridos', true,
            'abreviar_valores', false, 'solicitar_confirmacao_exclusao', true, 'graficos_visiveis', 'categorias,evolucao,saldo',
            'insights_inteligentes_ativo', true, 'mostrar_saldo_consolidado', true, 'mostrar_evolucao_historica', true,
            'modo_inteligente_ativo', false, 'sugestoes_economia', false);
    end if;
    select to_jsonb(p) - 'perfil_financeiro_id' - 'atualizado_em' - 'atualizado_por' into v_perfil
      from financeiro.preferencia_perfil p where p.perfil_financeiro_id = p_perfil_id;
    if v_perfil is null then
        v_perfil := jsonb_build_object(
            'renda_principal', null, 'mes_inicio_planejamento', 1, 'dia_fechamento_mes', 1, 'ajustar_competencia_automatico', true,
            'exibir_aviso_despesa_vencida', true, 'vincular_pagamento_cartao_auto', true, 'dia_inicio_fatura', 1,
            'dia_corte_fatura', 1, 'lancamentos_agrupados', false, 'orcamento_por_categoria', true,
            'classificacao_automatica', false, 'correcao_categorias', false, 'parcelas_recorrentes_auto', false);
    end if;
    -- Como o to_dict do Flask: renda sem valor = 0.
    v_perfil := v_perfil || jsonb_build_object('renda_principal', coalesce((v_perfil ->> 'renda_principal')::numeric, 0));
    return jsonb_build_object(
        'data', v_usuario || v_perfil,
        'escopo', (select jsonb_object_agg(c, 'USUARIO') from unnest(financeiro.pref_campos('USUARIO')) c)
                  || (select jsonb_object_agg(c, 'PERFIL') from unnest(financeiro.pref_campos('PERFIL')) c),
        'pode_gerir_perfil', financeiro.pode_gerir_perfil(p_perfil_id));
end
$$;

-- PUT /api/preferencias: cada campo vai para o seu escopo; campos desconhecidos sao ignorados (como o Flask). As do
-- perfil exigem gerir o perfil; nada e gravado se algum campo for invalido ou nao autorizado.
create function financeiro.salvar_preferencias(p_perfil_id integer, p_dados jsonb)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_usuario jsonb := '{}'::jsonb;
    v_perfil  jsonb := '{}'::jsonb;
    v_campo   text;
    v_valor   jsonb;
    v_atual   jsonb;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    if p_dados is null or jsonb_typeof(p_dados) <> 'object' then
        raise exception 'Preferencias: envie os campos a alterar' using errcode = '22023';
    end if;
    for v_campo, v_valor in select e.key, e.value from jsonb_each(p_dados) e loop
        if v_campo = any(financeiro.pref_campos('USUARIO')) then
            v_usuario := v_usuario || jsonb_build_object(v_campo, financeiro.pref_valor(v_campo, v_valor));
        elsif v_campo = any(financeiro.pref_campos('PERFIL')) then
            v_perfil := v_perfil || jsonb_build_object(v_campo, financeiro.pref_valor(v_campo, v_valor));
        end if;
    end loop;
    if v_perfil <> '{}'::jsonb and not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Somente quem gere o perfil altera as preferencias financeiras dele. Nada foi gravado.' using errcode = '42501';
    end if;
    if v_usuario <> '{}'::jsonb then
        insert into financeiro.preferencia_usuario (user_id) values ((select auth.uid())) on conflict (user_id) do nothing;
        select to_jsonb(u) into v_atual from financeiro.preferencia_usuario u where u.user_id = (select auth.uid()) for update;
        update financeiro.preferencia_usuario u
           set (nome_usuario, tema_sistema, cor_principal, mostrar_icones_coloridos, abreviar_valores, solicitar_confirmacao_exclusao,
                graficos_visiveis, insights_inteligentes_ativo, mostrar_saldo_consolidado, mostrar_evolucao_historica,
                modo_inteligente_ativo, sugestoes_economia, atualizado_em)
             = (select r.nome_usuario, r.tema_sistema, r.cor_principal, r.mostrar_icones_coloridos, r.abreviar_valores,
                       r.solicitar_confirmacao_exclusao, r.graficos_visiveis, r.insights_inteligentes_ativo, r.mostrar_saldo_consolidado,
                       r.mostrar_evolucao_historica, r.modo_inteligente_ativo, r.sugestoes_economia, now()
                  from jsonb_populate_record(null::financeiro.preferencia_usuario, v_atual || v_usuario) r)
         where u.user_id = (select auth.uid());
    end if;
    if v_perfil <> '{}'::jsonb then
        insert into financeiro.preferencia_perfil (perfil_financeiro_id) values (p_perfil_id) on conflict (perfil_financeiro_id) do nothing;
        select to_jsonb(p) into v_atual from financeiro.preferencia_perfil p where p.perfil_financeiro_id = p_perfil_id for update;
        update financeiro.preferencia_perfil p
           set (renda_principal, mes_inicio_planejamento, dia_fechamento_mes, ajustar_competencia_automatico, exibir_aviso_despesa_vencida,
                vincular_pagamento_cartao_auto, dia_inicio_fatura, dia_corte_fatura, lancamentos_agrupados, orcamento_por_categoria,
                classificacao_automatica, correcao_categorias, parcelas_recorrentes_auto, atualizado_em, atualizado_por)
             = (select r.renda_principal, r.mes_inicio_planejamento, r.dia_fechamento_mes, r.ajustar_competencia_automatico,
                       r.exibir_aviso_despesa_vencida, r.vincular_pagamento_cartao_auto, r.dia_inicio_fatura, r.dia_corte_fatura,
                       r.lancamentos_agrupados, r.orcamento_por_categoria, r.classificacao_automatica, r.correcao_categorias,
                       r.parcelas_recorrentes_auto, now(), (select auth.uid())
                  from jsonb_populate_record(null::financeiro.preferencia_perfil, v_atual || v_perfil) r)
         where p.perfil_financeiro_id = p_perfil_id;
    end if;
    return financeiro.preferencias_tela(p_perfil_id);
end
$$;

revoke execute on function financeiro.pref_campos(text) from public, anon, authenticated;
revoke execute on function financeiro.pref_valor(text, jsonb) from public, anon, authenticated;
revoke execute on function financeiro.preferencias_tela(integer) from public, anon;
revoke execute on function financeiro.salvar_preferencias(integer, jsonb) from public, anon;
grant execute on function financeiro.preferencias_tela(integer) to authenticated;
grant execute on function financeiro.salvar_preferencias(integer, jsonb) to authenticated;
