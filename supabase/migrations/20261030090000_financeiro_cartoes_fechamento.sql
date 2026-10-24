-- FIN-CARTOES-FECHAMENTO-1 — competencia sugerida pelo fechamento do cartao, ajuste manual e fatura
-- consolidada so com confirmacao.
--
-- NAO aplicar no Supabase remoto sem autorizacao especifica
-- (scripts/supabase_migrations.py aplicar --versoes 20261030090000).
-- Validada em cluster local descartavel (tests/test_cartoes_fechamento.py). Docs: docs/FIN_CARTOES_FECHAMENTO_1.md.
--
-- 1. config_agregador: compra_no_fechamento ('PROXIMO' padrao | 'ATUAL') e fechamento_confirmado (false para
--    todos os cartoes existentes: nenhum e marcado como confirmado automaticamente).
-- 2. lancamento_agregado.mes_fatura_sugerido (date, nula): competencia que o fechamento sugeria para a parcela
--    no cadastro (auditoria do ajuste manual). Nada e preenchido retroativamente.
-- 3. fatura_consolidada_inclusao: auditoria de cada inclusao confirmada em fatura consolidada (FECHADA).
-- 4. financeiro.competencia_da_compra: regra central (o Flask tem a mesma, CartaoService.competencia_da_compra,
--    comparada numa grade de datas). Competencia = mes do vencimento. Dias 29-31 viram o ultimo dia do mes.
--    Ciclo cujo mes de vencimento foge do padrao do cartao (por causa de dias curtos) e ambiguo: sem sugestao.
-- 5. plano_compra/previa_compra/criar_compra: mes da fatura opcional (sugerido); fatura consolidada exige a
--    confirmacao da operacao ({fatura_id, total_consolidado} vistos na previa), atualiza o total consolidado e
--    registra auditoria; fatura paga continua protegida (desvio). Ordem de travas: cartao -> faturas.
-- 6. editar_compra: mover compra a vista para fatura consolidada exige a mesma confirmacao.
-- 7. Cartoes: regra do dia do fechamento e fechamento confirmado no cadastro, na edicao e na consulta.
-- Nenhuma compra, parcela, fatura ou pagamento existente e alterado.

alter table public.config_agregador add column if not exists compra_no_fechamento varchar(10) not null default 'PROXIMO';
alter table public.config_agregador add column if not exists fechamento_confirmado boolean not null default false;
do $$
begin
    if not exists (select 1 from pg_constraint where conname = 'ck_config_agregador_compra_no_fechamento') then
        alter table public.config_agregador add constraint ck_config_agregador_compra_no_fechamento
            check (compra_no_fechamento in ('ATUAL', 'PROXIMO'));
    end if;
end
$$;
comment on column public.config_agregador.compra_no_fechamento is
    'FIN-CARTOES-FECHAMENTO-1: compra feita no dia do fechamento entra no ciclo ATUAL ou no PROXIMO (padrao).';
comment on column public.config_agregador.fechamento_confirmado is
    'FIN-CARTOES-FECHAMENTO-1: dias de fechamento/vencimento confirmados pelo usuario (sem isso, nenhuma sugestao).';

alter table public.lancamento_agregado add column if not exists mes_fatura_sugerido date;
comment on column public.lancamento_agregado.mes_fatura_sugerido is
    'FIN-CARTOES-FECHAMENTO-1: competencia sugerida pelo fechamento no cadastro (nula = sem sugestao).';

create table if not exists public.fatura_consolidada_inclusao (
    id                         serial primary key,
    fatura_id                  integer       not null references public.conta (id) on delete cascade,
    cartao_id                  integer       not null,
    perfil_financeiro_id       integer,
    competencia                date          not null,
    compra_id                  varchar(36),
    lancamento_id              integer       references public.lancamento_agregado (id) on delete set null,
    valor_incluido             numeric(12,2) not null,
    total_consolidado_anterior numeric(12,2) not null,
    total_consolidado_novo     numeric(12,2) not null,
    operacao                   varchar(20)   not null,
    origem                     varchar(20)   not null,
    user_id                    varchar(36),
    usuario_id                 integer,
    criado_em                  timestamp     not null default (now() at time zone 'utc')
);
comment on table public.fatura_consolidada_inclusao is
    'FIN-CARTOES-FECHAMENTO-1: inclusao confirmada em fatura consolidada (total anterior e novo, origem e autor).';
-- Como as demais tabelas do public no Supabase (SEC-SUPABASE-PUBLIC-1): RLS sem policy, fora da Data API.
alter table public.fatura_consolidada_inclusao enable row level security;
do $$
begin
    if exists (select 1 from pg_roles where rolname = 'anon') then
        revoke all on table public.fatura_consolidada_inclusao from anon;
        revoke all on sequence public.fatura_consolidada_inclusao_id_seq from anon;
    end if;
    if exists (select 1 from pg_roles where rolname = 'authenticated') then
        revoke all on table public.fatura_consolidada_inclusao from authenticated;
        revoke all on sequence public.fatura_consolidada_inclusao_id_seq from authenticated;
    end if;
end
$$;

-- Competencia (mes do vencimento) da fatura que recebe uma compra feita em p_data. Nula se a configuracao
-- for invalida ou se o ciclo desta data for ambiguo. Interna e deterministica.
create function financeiro.competencia_da_compra(p_data date, p_dia_fechamento integer, p_dia_vencimento integer,
                                                 p_regra text)
    returns date
    language plpgsql
    immutable
    set search_path = ''
as $$
declare
    v_mes        date;
    v_fechamento date;
    v_vencimento date;
begin
    if p_data is null or p_dia_fechamento is null or p_dia_vencimento is null
       or p_dia_fechamento not between 1 and 31 or p_dia_vencimento not between 1 and 31
       or coalesce(p_regra, 'PROXIMO') not in ('ATUAL', 'PROXIMO') then
        return null;
    end if;
    -- Ciclo: fecha no dia contratual do mes da compra; depois dele (ou nele, com a regra PROXIMO), no seguinte.
    v_mes := date_trunc('month', p_data::timestamp)::date;
    v_fechamento := financeiro.dia_contratual(v_mes, p_dia_fechamento);
    if p_data > v_fechamento or (p_data = v_fechamento and coalesce(p_regra, 'PROXIMO') = 'PROXIMO') then
        v_mes := (v_mes + interval '1 month')::date;
        v_fechamento := financeiro.dia_contratual(v_mes, p_dia_fechamento);
    end if;
    -- Vencimento: o primeiro dia contratual de vencimento depois do fechamento.
    v_vencimento := financeiro.dia_contratual(v_mes, p_dia_vencimento);
    if v_vencimento <= v_fechamento then
        v_vencimento := financeiro.dia_contratual((v_mes + interval '1 month')::date, p_dia_vencimento);
    end if;
    -- Padrao do cartao: vence no mes do fechamento se o dia do vencimento e maior, senao no seguinte.
    if date_trunc('month', v_vencimento::timestamp)::date
       <> (v_mes + make_interval(months => case when p_dia_vencimento > p_dia_fechamento then 0 else 1 end))::date then
        return null;  -- dias curtos mudaram a ordem fechamento/vencimento neste mes: ciclo ambiguo
    end if;
    return date_trunc('month', v_vencimento::timestamp)::date;
end
$$;

-- Situacao de uma fatura: SEM_FATURA, PAGA, FECHADA (consolidada) ou ABERTA. Interna.
create function financeiro.situacao_fatura(p_conta_id integer)
    returns text
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select case when c.id is null then 'SEM_FATURA'
                when c.status_pagamento = 'Pago' or c.status_fatura = 'PAGA' then 'PAGA'
                when c.status_fatura = 'FECHADA' then 'FECHADA'
                else 'ABERTA' end
      from (select 1) x left join public.conta c on c.id = p_conta_id
$$;

-- Sugestao do cartao para uma data: situacao SUGERIDA | NAO_CONFIRMADO | CICLO_AMBIGUO | SEM_CONFIGURACAO |
-- SEM_DATA, competencia, datas de fechamento e vencimento do ciclo e a configuracao usada. Interna.
create function financeiro.sugestao_competencia(p_cartao_id integer, p_data date)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_cfg      public.config_agregador;
    v_comp     date;
    v_situacao text;
begin
    select * into v_cfg from public.config_agregador c where c.item_despesa_id = p_cartao_id;
    if not found or v_cfg.dia_fechamento is null or v_cfg.dia_vencimento is null
       or v_cfg.dia_fechamento not between 1 and 31 or v_cfg.dia_vencimento not between 1 and 31 then
        v_situacao := 'SEM_CONFIGURACAO';
    elsif not coalesce(v_cfg.fechamento_confirmado, false) then
        v_situacao := 'NAO_CONFIRMADO';
    elsif p_data is null then
        v_situacao := 'SEM_DATA';
    else
        v_comp := financeiro.competencia_da_compra(p_data, v_cfg.dia_fechamento, v_cfg.dia_vencimento,
                                                   v_cfg.compra_no_fechamento);
        v_situacao := case when v_comp is null then 'CICLO_AMBIGUO' else 'SUGERIDA' end;
    end if;
    return jsonb_build_object(
        'situacao', v_situacao,
        'competencia', v_comp,
        'fechamento', case when v_comp is not null then financeiro.dia_contratual(
            (v_comp - make_interval(months => case when v_cfg.dia_vencimento > v_cfg.dia_fechamento then 0 else 1 end))::date,
            v_cfg.dia_fechamento) end,
        'vencimento', case when v_comp is not null then financeiro.dia_contratual(v_comp, v_cfg.dia_vencimento) end,
        'dia_fechamento', v_cfg.dia_fechamento,
        'dia_vencimento', v_cfg.dia_vencimento,
        'compra_no_fechamento', coalesce(v_cfg.compra_no_fechamento, 'PROXIMO'),
        'fechamento_confirmado', coalesce(v_cfg.fechamento_confirmado, false));
end
$$;

-- Para o formulario: sugestao para o cartao e a data, com a situacao da fatura sugerida (so leitura).
create function financeiro.sugerir_competencia(p_perfil_id integer, p_cartao_id integer, p_data_compra date)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_sug jsonb;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    perform financeiro.cartao_do_perfil(p_perfil_id, p_cartao_id, true);
    v_sug := financeiro.sugestao_competencia(p_cartao_id, p_data_compra);
    if v_sug ->> 'competencia' is not null then
        v_sug := v_sug || jsonb_build_object('fatura_situacao', financeiro.situacao_fatura(
            financeiro.fatura_do_mes(p_cartao_id, (v_sug ->> 'competencia')::date)));
    end if;
    return v_sug;
end
$$;

-- Plano de uma compra (somente leitura). Mes da fatura opcional: sem ele, vale a sugestao do fechamento.
-- Novas colunas: mes_fatura_sugerido (auditoria), situacao_fatura e total_consolidado (para a confirmacao).
drop function financeiro.plano_compra(integer, jsonb);
create function financeiro.plano_compra(p_perfil_id integer, p_dados jsonb)
    returns table (numero integer, total integer, mes_fatura date, data_compra date, valor numeric,
                   redirecionada boolean, fatura_id integer, categoria_id integer, categoria_cartao_id integer,
                   cartao_id integer, descricao text, observacoes text, mes_fatura_sugerido date,
                   situacao_fatura text, total_consolidado numeric)
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_cartao  public.item_despesa;
    v_valor   numeric;
    v_n       integer;
    v_data    date;
    v_mes     date;
    v_cat     integer;
    v_cc      integer;
    v_desc    text;
    v_cent    bigint;
    v_base    bigint;
    v_resto   bigint;
    v_alvo    date;
    v_fat     integer;
    v_desvio  boolean;
    v_passos  integer;
    v_ant     date;
    v_sug     jsonb;
    v_sugerido date;
begin
    if p_dados is null or jsonb_typeof(p_dados) <> 'object' then
        raise exception 'Dados da compra invalidos' using errcode = '22023';
    end if;
    begin
        v_cartao := financeiro.cartao_do_perfil(p_perfil_id, (p_dados ->> 'cartao_id')::integer, true);
    exception when invalid_text_representation then
        raise exception 'Cartao invalido' using errcode = '22023';
    end;
    if not exists (select 1 from public.config_agregador cfg where cfg.item_despesa_id = v_cartao.id
                    and cfg.dia_vencimento between 1 and 31) then
        raise exception 'Cartao sem dia de vencimento configurado' using errcode = '22023';
    end if;
    v_desc := btrim(coalesce(p_dados ->> 'descricao', ''));
    if v_desc = '' or length(v_desc) > 200 then
        raise exception 'Descricao obrigatoria (ate 200 caracteres)' using errcode = '22023';
    end if;
    begin
        v_valor := (p_dados ->> 'valor')::numeric;
        v_n := coalesce((p_dados ->> 'total_parcelas')::integer, 1);
        v_data := (p_dados ->> 'data_compra')::date;
        v_mes := date_trunc('month', nullif(p_dados ->> 'mes_fatura', '')::date::timestamp)::date;
        v_cat := (p_dados ->> 'categoria_id')::integer;
    exception when others then
        raise exception 'Valor, parcelas, data da compra, mes da fatura ou categoria invalidos' using errcode = '22023';
    end;
    if v_valor is null or v_valor <= 0 or v_valor >= 100000000 or v_valor <> round(v_valor, 2) then
        raise exception 'Valor deve ser positivo, com ate 2 casas decimais' using errcode = '22023';
    end if;
    if v_n is null or v_n not between 1 and 60 or round(v_valor * 100) < v_n then
        raise exception 'Parcelas devem ficar entre 1 e 60 (no minimo R$ 0,01 cada)' using errcode = '22023';
    end if;
    if v_data is null then
        raise exception 'Data da compra obrigatoria' using errcode = '22023';
    end if;
    -- FIN-CARTOES-FECHAMENTO-1: a sugestao e calculada sempre (auditoria); sem mes informado, ela decide.
    v_sug := financeiro.sugestao_competencia(v_cartao.id, v_data);
    v_sugerido := (v_sug ->> 'competencia')::date;
    if v_mes is null then
        if v_sugerido is null then
            raise exception 'Informe o mes da fatura: %', case v_sug ->> 'situacao'
                when 'NAO_CONFIRMADO' then 'o fechamento do cartao ainda nao foi confirmado'
                when 'CICLO_AMBIGUO' then 'o fechamento e o vencimento deste cartao nao definem a fatura desta data'
                else 'o cartao nao tem fechamento configurado' end
                using errcode = '22023', hint = 'SEM_SUGESTAO';
        end if;
        v_mes := v_sugerido;
    end if;
    if v_mes < (date_trunc('month', v_data::timestamp) - interval '12 months')::date
       or v_mes > (date_trunc('month', v_data::timestamp) + interval '12 months')::date then
        raise exception 'Mes da fatura deve ficar a ate 12 meses da data da compra' using errcode = '22023';
    end if;
    if v_cat is null or not exists (select 1 from public.categoria c where c.id = v_cat and coalesce(c.ativo, true)) then
        raise exception 'Categoria inexistente ou inativa' using errcode = '22023';
    end if;
    v_cc := financeiro.resolver_categoria_cartao(p_perfil_id, v_cartao.id, v_cat);

    v_cent := round(v_valor * 100)::bigint;
    v_base := v_cent / v_n;
    v_resto := v_cent % v_n;
    for i in 1..v_n loop
        v_alvo := (v_mes + make_interval(months => i - 1))::date;
        if v_ant is not null and v_alvo <= v_ant then  -- desvio desloca as parcelas seguintes (uma por fatura)
            v_alvo := (v_ant + interval '1 month')::date;
        end if;
        v_desvio := v_alvo <> (v_mes + make_interval(months => i - 1))::date;
        v_passos := 0;
        loop  -- fatura paga nao recebe compra nova: proxima nao paga (fatura consolidada continua elegivel)
            v_fat := financeiro.fatura_do_mes(v_cartao.id, v_alvo);
            exit when v_fat is null or not financeiro.fatura_esta_paga(v_fat);
            v_alvo := (v_alvo + interval '1 month')::date;
            v_desvio := true;
            v_passos := v_passos + 1;
            if v_passos > 24 then
                raise exception 'Nao ha fatura aberta nos proximos 24 meses' using errcode = '22023';
            end if;
        end loop;
        v_ant := v_alvo;
        numero := i;
        total := v_n;
        mes_fatura := v_alvo;
        data_compra := (v_data + make_interval(months => i - 1))::date;
        valor := (v_base + case when i <= v_resto then 1 else 0 end)::numeric / 100;
        redirecionada := v_desvio;
        fatura_id := v_fat;
        categoria_id := v_cat;
        categoria_cartao_id := v_cc;
        cartao_id := v_cartao.id;
        descricao := v_desc;
        observacoes := coalesce(p_dados ->> 'observacoes', '');
        mes_fatura_sugerido := case when v_sugerido is not null then (v_sugerido + make_interval(months => i - 1))::date end;
        situacao_fatura := financeiro.situacao_fatura(v_fat);
        total_consolidado := case when situacao_fatura = 'FECHADA' then
            (select coalesce(c.valor_consolidado, c.valor_executado, 0) from public.conta c where c.id = v_fat) end;
        return next;
    end loop;
end
$$;

create or replace function financeiro.previa_compra(p_perfil_id integer, p_dados jsonb)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    return (select jsonb_build_object(
                'parcelas', jsonb_agg(jsonb_build_object('numero', p.numero, 'total', p.total, 'mes_fatura', p.mes_fatura,
                                                         'data_compra', p.data_compra, 'valor', p.valor,
                                                         'redirecionada', p.redirecionada,
                                                         'mes_fatura_sugerido', p.mes_fatura_sugerido,
                                                         'situacao_fatura', p.situacao_fatura,
                                                         'fatura_id', p.fatura_id) order by p.numero),
                'soma', sum(p.valor),
                'sugestao', financeiro.sugestao_competencia((p_dados ->> 'cartao_id')::integer,
                                                            (p_dados ->> 'data_compra')::date),
                -- D6: cada fatura consolidada recebe confirmacao propria, com o total que o usuario viu.
                'consolidadas', coalesce((select jsonb_agg(jsonb_build_object(
                                            'fatura_id', c.fatura_id, 'competencia', c.mes_fatura,
                                            'total_consolidado', c.total_consolidado, 'valor_incluido', c.incluido,
                                            'total_novo', c.total_consolidado + c.incluido) order by c.mes_fatura)
                                            from (select q.fatura_id, q.mes_fatura, q.total_consolidado, sum(q.valor) as incluido
                                                    from financeiro.plano_compra(p_perfil_id, p_dados) q
                                                   where q.situacao_fatura = 'FECHADA'
                                                   group by 1, 2, 3) c), '[]'::jsonb))
              from financeiro.plano_compra(p_perfil_id, p_dados) p);
end
$$;

-- Confere a confirmacao de inclusao numa fatura consolidada (travada pelo chamador): a operacao precisa
-- trazer {fatura_id, total_consolidado} iguais aos atuais. Devolve o total atual. Interna.
create function financeiro.exigir_confirmacao_consolidada(p_fatura_id integer, p_confirmacoes jsonb, p_incluido numeric)
    returns numeric
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_total numeric;
    v_comp  date;
begin
    select coalesce(c.valor_consolidado, c.valor_executado, 0), c.cartao_competencia into v_total, v_comp
      from public.conta c where c.id = p_fatura_id;
    if p_confirmacoes is null or jsonb_typeof(p_confirmacoes) <> 'array' or not exists (
        select 1 from jsonb_array_elements(p_confirmacoes) e
         where jsonb_typeof(e) = 'object' and (e ->> 'fatura_id') ~ '^[0-9]+$' and (e ->> 'fatura_id')::integer = p_fatura_id
           and (e ->> 'total_consolidado') ~ '^-?[0-9]+(\.[0-9]+)?$' and (e ->> 'total_consolidado')::numeric = v_total) then
        raise exception 'A fatura de % esta consolidada (total R$ %): confirme a inclusao de R$ % (o total passa a R$ %).',
            to_char(v_comp, 'MM/YYYY'), to_char(v_total, 'FM999999990.00'), to_char(p_incluido, 'FM999999990.00'),
            to_char(v_total + p_incluido, 'FM999999990.00')
            using errcode = 'P0001', hint = 'CONSOLIDADA',
                  detail = jsonb_build_object('fatura_id', p_fatura_id, 'competencia', v_comp, 'total_consolidado', v_total,
                                              'valor_incluido', p_incluido, 'total_novo', v_total + p_incluido)::text;
    end if;
    return v_total;
end
$$;

-- Cadastro da compra (FIN-FATURA-INTEGRIDADE-1 + FIN-CARTOES-FECHAMENTO-1): parcelas, faturas, recalculos,
-- competencia sugerida e, em fatura consolidada, confirmacao, total consolidado e auditoria; idempotente.
create or replace function financeiro.criar_compra(p_perfil_id integer, p_dados jsonb, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_anterior  financeiro.operacao_cartao;
    v_linhas    record;
    v_linha     record;
    v_compra    text := gen_random_uuid()::text;
    v_ids       integer[] := '{}';
    v_meses     date[] := '{}';
    v_fatura    integer;
    v_id        integer;
    v_cartao    integer;
    v_resultado jsonb;
    v_conf      jsonb;
    v_incluir   jsonb := '{}'::jsonb;  -- fatura consolidada -> {incluido, primeiro lancamento, competencia}
    v_fechadas  jsonb := '[]'::jsonb;
    v_total     numeric;
    v_chave     text;
begin
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    if p_chave is null then
        raise exception 'Chave da operacao obrigatoria' using errcode = '22023';
    end if;
    perform pg_advisory_xact_lock(hashtextextended(p_chave::text, 20261028));
    select * into v_anterior from financeiro.operacao_cartao o where o.chave = p_chave;
    if found then
        if v_anterior.user_id is distinct from (select auth.uid()) or v_anterior.perfil_financeiro_id <> p_perfil_id then
            raise exception 'Chave da operacao ja usada' using errcode = '22023';
        end if;
        return v_anterior.resultado || jsonb_build_object('repetida', true);
    end if;
    perform pg_advisory_xact_lock(20261023, p_perfil_id);  -- mesma trava da geracao (recorrencias do cartao)
    v_conf := p_dados -> 'confirmar_consolidadas';

    for v_linha in select * from financeiro.plano_compra(p_perfil_id, p_dados) order by numero loop
        if v_cartao is null then
            -- FIN-FATURA-INTEGRIDADE-1: ordem global de travas: o cartao antes das faturas.
            perform 1 from public.item_despesa where id = v_linha.cartao_id for update;
        end if;
        v_cartao := v_linha.cartao_id;
        v_fatura := financeiro.garantir_fatura(p_perfil_id, v_linha.cartao_id, v_linha.mes_fatura);
        perform 1 from public.conta where id = v_fatura for update;  -- o pagamento (se vier) espera
        if financeiro.fatura_esta_paga(v_fatura) then
            raise exception 'A fatura de % foi paga durante o cadastro. Revise e tente de novo.',
                to_char(v_linha.mes_fatura, 'MM/YYYY') using errcode = 'P0001';
        end if;
        insert into public.lancamento_agregado (perfil_financeiro_id, cartao_id, item_agregado_id, categoria_cartao_id,
                                                categoria_id, descricao, valor, data_compra, mes_fatura, numero_parcela,
                                                total_parcelas, observacoes, is_recorrente, compra_id, is_importado,
                                                criado_em, mes_fatura_original, mes_fatura_sugerido)
        values (coalesce((select c.perfil_financeiro_id from public.conta c where c.id = v_fatura), p_perfil_id),
                v_linha.cartao_id, null, v_linha.categoria_cartao_id, v_linha.categoria_id, v_linha.descricao,
                v_linha.valor, v_linha.data_compra, v_linha.mes_fatura, v_linha.numero, v_linha.total,
                v_linha.observacoes, false, v_compra, false, now() at time zone 'utc',
                -- desviada de fatura paga: guarda a competencia em que entraria
                case when v_linha.redirecionada
                     then (date_trunc('month', coalesce(nullif(p_dados ->> 'mes_fatura', '')::date,
                                                        v_linha.mes_fatura_sugerido - make_interval(months => v_linha.numero - 1))
                                       ::timestamp)
                           + make_interval(months => v_linha.numero - 1))::date end,
                v_linha.mes_fatura_sugerido)
        returning id into v_id;
        v_ids := v_ids || v_id;
        if not v_linha.mes_fatura = any(v_meses) then
            v_meses := v_meses || v_linha.mes_fatura;
        end if;
        -- D6: fatura consolidada (relida com a trava) so com a confirmacao desta operacao.
        if exists (select 1 from public.conta c where c.id = v_fatura and c.status_fatura = 'FECHADA') then
            v_chave := v_fatura::text;
            v_incluir := jsonb_set(v_incluir, array[v_chave], jsonb_build_object(
                'incluido', coalesce((v_incluir #>> array[v_chave, 'incluido'])::numeric, 0) + v_linha.valor,
                'lancamento', coalesce((v_incluir #>> array[v_chave, 'lancamento'])::integer, v_id),
                'competencia', v_linha.mes_fatura));
        end if;
    end loop;

    for v_linhas in select key::integer as fatura, value from jsonb_each(v_incluir) order by key::integer loop
        v_total := financeiro.exigir_confirmacao_consolidada(v_linhas.fatura, v_conf, (v_linhas.value ->> 'incluido')::numeric);
        update public.conta set valor_consolidado = v_total + (v_linhas.value ->> 'incluido')::numeric
         where id = v_linhas.fatura;
        insert into public.fatura_consolidada_inclusao (fatura_id, cartao_id, perfil_financeiro_id, competencia, compra_id,
                                                        lancamento_id, valor_incluido, total_consolidado_anterior,
                                                        total_consolidado_novo, operacao, origem, user_id, criado_em)
        values (v_linhas.fatura, v_cartao, p_perfil_id, (v_linhas.value ->> 'competencia')::date, v_compra,
                (v_linhas.value ->> 'lancamento')::integer, (v_linhas.value ->> 'incluido')::numeric, v_total,
                v_total + (v_linhas.value ->> 'incluido')::numeric, 'COMPRA', 'NOVO_APP', (select auth.uid())::text,
                now() at time zone 'utc');
        v_fechadas := v_fechadas || jsonb_build_object('fatura_id', v_linhas.fatura,
                                                       'total_consolidado', v_total + (v_linhas.value ->> 'incluido')::numeric);
    end loop;
    for i in 1..cardinality(v_meses) loop
        perform financeiro.recalcular_fatura(p_perfil_id, v_cartao, v_meses[i]);
    end loop;
    v_resultado := jsonb_build_object('compra_id', v_compra, 'lancamentos', to_jsonb(v_ids), 'faturas', to_jsonb(v_meses),
                                      'consolidadas', v_fechadas);
    insert into financeiro.operacao_cartao (chave, user_id, perfil_financeiro_id, operacao, resultado)
    values (p_chave, (select auth.uid()), p_perfil_id, 'criar_compra', v_resultado);
    return v_resultado;
end
$$;

-- Edicao (FIN-CARTOES-1): mover compra a vista para fatura consolidada exige a mesma confirmacao (D6), atualiza
-- o total consolidado e registra auditoria. Nova data da compra: a competencia sugerida (auditoria) e refeita;
-- o mes da fatura so muda se o usuario muda-lo.
create or replace function financeiro.editar_compra(p_perfil_id integer, p_lancamento_id integer, p_versao text, p_dados jsonb)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_abertas integer[];
    v_l       public.lancamento_agregado;
    v_desc    text;
    v_cat     integer;
    v_cc      integer;
    v_valor   numeric;
    v_data    date;
    v_mes     date;
    v_meses   date[];
    v_fatura  integer;
    v_total   numeric;
    v_sugerido date;
begin
    v_abertas := financeiro.travar_compra(p_perfil_id, p_lancamento_id, p_versao);
    select * into v_l from public.lancamento_agregado where id = p_lancamento_id;
    if p_dados is null or jsonb_typeof(p_dados) <> 'object' then
        raise exception 'Dados da compra invalidos' using errcode = '22023';
    end if;
    if p_dados ? 'descricao' then
        v_desc := btrim(coalesce(p_dados ->> 'descricao', ''));
        if v_desc = '' or length(v_desc) > 200 then
            raise exception 'Descricao obrigatoria (ate 200 caracteres)' using errcode = '22023';
        end if;
    end if;
    if p_dados ? 'categoria_id' then
        v_cat := (p_dados ->> 'categoria_id')::integer;
        if not exists (select 1 from public.categoria c where c.id = v_cat and coalesce(c.ativo, true)) then
            raise exception 'Categoria inexistente ou inativa' using errcode = '22023';
        end if;
        v_cc := financeiro.resolver_categoria_cartao(p_perfil_id, v_l.cartao_id, v_cat);
    end if;
    if p_dados ?| array['valor', 'data_compra', 'mes_fatura'] then
        if coalesce(v_l.total_parcelas, 1) > 1 then
            raise exception 'Compra parcelada: valor e datas nao mudam aqui (exclua as parcelas abertas e lance de novo)'
                using errcode = '22023';
        end if;
        v_valor := coalesce((p_dados ->> 'valor')::numeric, v_l.valor);
        if v_valor <= 0 or v_valor >= 100000000 or v_valor <> round(v_valor, 2) then
            raise exception 'Valor deve ser positivo, com ate 2 casas decimais' using errcode = '22023';
        end if;
        v_data := coalesce((p_dados ->> 'data_compra')::date, v_l.data_compra);
        v_mes := coalesce(date_trunc('month', (p_dados ->> 'mes_fatura')::date::timestamp)::date, v_l.mes_fatura);
        if v_mes <> v_l.mes_fatura then
            v_fatura := financeiro.garantir_fatura(p_perfil_id, v_l.cartao_id, v_mes);
            perform 1 from public.conta where id = v_fatura for update;
            if financeiro.fatura_esta_paga(v_fatura) then
                raise exception 'A fatura de destino ja esta paga' using errcode = '22023';
            end if;
            if exists (select 1 from public.conta c where c.id = v_fatura and c.status_fatura = 'FECHADA') then
                v_total := financeiro.exigir_confirmacao_consolidada(v_fatura, p_dados -> 'confirmar_consolidadas', v_valor);
            end if;
        end if;
        if v_data is distinct from v_l.data_compra then
            v_sugerido := (financeiro.sugestao_competencia(v_l.cartao_id, v_data) ->> 'competencia')::date;
        end if;
    end if;
    select array_agg(distinct l.mes_fatura) into v_meses from public.lancamento_agregado l where l.id = any(v_abertas);
    update public.lancamento_agregado l
       set descricao = coalesce(v_desc, l.descricao),
           categoria_id = coalesce(v_cat, l.categoria_id),
           categoria_cartao_id = case when p_dados ? 'categoria_id' then v_cc else l.categoria_cartao_id end,
           observacoes = case when p_dados ? 'observacoes' then coalesce(p_dados ->> 'observacoes', '') else l.observacoes end,
           valor = coalesce(v_valor, l.valor),
           data_compra = coalesce(v_data, l.data_compra),
           mes_fatura = coalesce(v_mes, l.mes_fatura),
           mes_fatura_sugerido = case when v_data is distinct from l.data_compra and v_data is not null
                                      then v_sugerido else l.mes_fatura_sugerido end
     where l.id = any(v_abertas);
    if v_total is not null then
        update public.conta set valor_consolidado = v_total + v_valor where id = v_fatura;
        insert into public.fatura_consolidada_inclusao (fatura_id, cartao_id, perfil_financeiro_id, competencia, compra_id,
                                                        lancamento_id, valor_incluido, total_consolidado_anterior,
                                                        total_consolidado_novo, operacao, origem, user_id, criado_em)
        values (v_fatura, v_l.cartao_id, p_perfil_id, v_mes, v_l.compra_id, p_lancamento_id, v_valor, v_total,
                v_total + v_valor, 'EDICAO', 'NOVO_APP', (select auth.uid())::text, now() at time zone 'utc');
    end if;
    if v_mes is not null and not v_mes = any(v_meses) then
        v_meses := v_meses || v_mes;
    end if;
    for i in 1..cardinality(v_meses) loop
        perform financeiro.recalcular_fatura(p_perfil_id, v_l.cartao_id, v_meses[i]);
    end loop;
    return jsonb_build_object('lancamentos', to_jsonb(v_abertas), 'versao', financeiro.versao_compra(p_lancamento_id));
end
$$;

-- Cartoes: dados validados, agora com a regra do dia do fechamento e a confirmacao do fechamento.
create or replace function financeiro.ler_dados_cartao(p_dados jsonb, p_parcial boolean)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_saida jsonb := '{}'::jsonb;
    v_texto text;
    v_int   integer;
    v_valor numeric;
begin
    if p_dados is null or jsonb_typeof(p_dados) <> 'object' then
        raise exception 'Dados do cartao invalidos' using errcode = '22023';
    end if;
    if p_dados ?| array['numero_cartao', 'codigo_seguranca', 'data_validade'] then
        raise exception 'Numero, validade e codigo de seguranca nao sao tratados no novo aplicativo' using errcode = '22023';
    end if;
    if p_dados ? 'nome' or not p_parcial then
        v_texto := btrim(coalesce(p_dados ->> 'nome', ''));
        if v_texto = '' or length(v_texto) > 100 then
            raise exception 'Nome do cartao obrigatorio (ate 100 caracteres)' using errcode = '22023';
        end if;
        v_saida := v_saida || jsonb_build_object('nome', v_texto);
    end if;
    foreach v_texto in array array['dia_fechamento', 'dia_vencimento'] loop
        if p_dados ? v_texto or not p_parcial then
            begin
                v_int := (p_dados ->> v_texto)::integer;
            exception when others then
                v_int := null;
            end;
            if v_int is null or v_int not between 1 and 31 then
                raise exception 'Dias de fechamento e vencimento devem ficar entre 1 e 31' using errcode = '22023';
            end if;
            v_saida := v_saida || jsonb_build_object(v_texto, v_int);
        end if;
    end loop;
    if p_dados ? 'compra_no_fechamento' then
        if coalesce(p_dados ->> 'compra_no_fechamento', '') not in ('ATUAL', 'PROXIMO') then
            raise exception 'Regra da compra no dia do fechamento invalida (ATUAL ou PROXIMO)' using errcode = '22023';
        end if;
        v_saida := v_saida || jsonb_build_object('compra_no_fechamento', p_dados ->> 'compra_no_fechamento');
    end if;
    if p_dados ? 'fechamento_confirmado' then
        if jsonb_typeof(p_dados -> 'fechamento_confirmado') <> 'boolean' then
            raise exception 'Confirmacao do fechamento invalida' using errcode = '22023';
        end if;
        v_saida := v_saida || jsonb_build_object('fechamento_confirmado', (p_dados ->> 'fechamento_confirmado')::boolean);
    end if;
    if p_dados ? 'limite_credito' then
        if nullif(p_dados ->> 'limite_credito', '') is null then
            v_saida := v_saida || jsonb_build_object('limite_credito', null);
        else
            begin
                v_valor := (p_dados ->> 'limite_credito')::numeric;
            exception when others then
                v_valor := null;
            end;
            if v_valor is null or v_valor < 0 or v_valor >= 100000000 or v_valor <> round(v_valor, 2) then
                raise exception 'Limite de credito invalido' using errcode = '22023';
            end if;
            v_saida := v_saida || jsonb_build_object('limite_credito', v_valor);
        end if;
    end if;
    if p_dados ? 'observacoes' then
        v_saida := v_saida || jsonb_build_object('observacoes', left(coalesce(p_dados ->> 'observacoes', ''), 1000));
    end if;
    return v_saida;
end
$$;

create or replace function financeiro.criar_cartao(p_perfil_id integer, p_dados jsonb, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_anterior financeiro.operacao_cartao;
    v_d        jsonb;
    v_cat      integer;
    v_id       integer;
    v_res      jsonb;
begin
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    if p_chave is null then
        raise exception 'Chave da operacao obrigatoria' using errcode = '22023';
    end if;
    perform pg_advisory_xact_lock(hashtextextended(p_chave::text, 20261028));
    select * into v_anterior from financeiro.operacao_cartao o where o.chave = p_chave;
    if found then
        if v_anterior.user_id is distinct from (select auth.uid()) or v_anterior.perfil_financeiro_id <> p_perfil_id then
            raise exception 'Chave da operacao ja usada' using errcode = '22023';
        end if;
        return v_anterior.resultado || jsonb_build_object('repetida', true);
    end if;
    v_d := financeiro.ler_dados_cartao(p_dados, false);
    select c.id into v_cat from public.categoria c where c.nome = 'Cartoes de Credito' order by c.id limit 1;  -- como o Flask
    insert into public.item_despesa (perfil_financeiro_id, categoria_id, nome, tipo, descricao, ativo, recorrente,
                                     tipo_recorrencia, pago, criado_em)
    values (p_perfil_id, v_cat, v_d ->> 'nome', 'Agregador', '', true, true, 'mensal', false, now() at time zone 'utc')
    returning id into v_id;
    insert into public.config_agregador (item_despesa_id, dia_fechamento, dia_vencimento, limite_credito, tem_codigo,
                                         observacoes, criado_em, compra_no_fechamento, fechamento_confirmado)
    values (v_id, (v_d ->> 'dia_fechamento')::integer, (v_d ->> 'dia_vencimento')::integer,
            (v_d ->> 'limite_credito')::numeric, true, coalesce(v_d ->> 'observacoes', ''), now() at time zone 'utc',
            coalesce(v_d ->> 'compra_no_fechamento', 'PROXIMO'), coalesce((v_d ->> 'fechamento_confirmado')::boolean, false));
    v_res := jsonb_build_object('cartao_id', v_id);
    insert into financeiro.operacao_cartao (chave, user_id, perfil_financeiro_id, operacao, resultado)
    values (p_chave, (select auth.uid()), p_perfil_id, 'criar_cartao', v_res);
    return v_res;
end
$$;

-- Cartoes do perfil: agora com a regra do dia do fechamento e a confirmacao. Nunca numero completo nem CVV.
drop function financeiro.cartoes_do_perfil(integer);
create function financeiro.cartoes_do_perfil(p_perfil_id integer)
    returns table (id integer, nome text, ativo boolean, dia_fechamento integer, dia_vencimento integer,
                   limite_credito numeric, final_numero text, observacoes text, versao text,
                   compra_no_fechamento text, fechamento_confirmado boolean)
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    return query
        select i.id, i.nome::text, coalesce(i.ativo, true), cfg.dia_fechamento, cfg.dia_vencimento, cfg.limite_credito,
               nullif(right(regexp_replace(coalesce(cfg.numero_cartao, ''), '[^0-9]', '', 'g'), 4), '')::text,
               cfg.observacoes::text, md5(i::text || '|' || coalesce(cfg::text, '')),
               coalesce(cfg.compra_no_fechamento, 'PROXIMO')::text, coalesce(cfg.fechamento_confirmado, false)
          from public.item_despesa i
          left join public.config_agregador cfg on cfg.item_despesa_id = i.id
         where i.tipo = 'Agregador' and financeiro.pertence_ao_perfil(i.perfil_financeiro_id, p_perfil_id)
         order by coalesce(i.ativo, true) desc, i.nome;
end
$$;

-- Edicao do cartao: dias, regra e confirmacao independentes; valor ausente fica como esta. Mudar um dia ou a
-- regra sem reconfirmar desfaz a confirmacao (a sugestao so vale para dados confirmados).
create or replace function financeiro.editar_cartao(p_perfil_id integer, p_cartao_id integer, p_versao text, p_dados jsonb)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_d jsonb;
begin
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    perform financeiro.cartao_do_perfil(p_perfil_id, p_cartao_id, false);
    perform 1 from public.item_despesa where id = p_cartao_id for update;
    perform 1 from public.config_agregador where item_despesa_id = p_cartao_id for update;
    if p_versao is distinct from (select c.versao from financeiro.cartoes_do_perfil(p_perfil_id) c where c.id = p_cartao_id) then
        raise exception 'O cartao foi alterado por outra operacao. Recarregue e tente de novo.' using errcode = 'P0001';
    end if;
    v_d := financeiro.ler_dados_cartao(p_dados, true);
    update public.item_despesa set nome = coalesce(v_d ->> 'nome', nome) where id = p_cartao_id;
    -- Faturas ja criadas mantem o vencimento gravado; o novo dia vale para as proximas. Compras ja lancadas
    -- nao mudam de fatura por causa da nova configuracao.
    update public.config_agregador cfg
       set dia_fechamento = coalesce((v_d ->> 'dia_fechamento')::integer, cfg.dia_fechamento),
           dia_vencimento = coalesce((v_d ->> 'dia_vencimento')::integer, cfg.dia_vencimento),
           limite_credito = case when v_d ? 'limite_credito' then (v_d ->> 'limite_credito')::numeric else cfg.limite_credito end,
           observacoes = case when v_d ? 'observacoes' then v_d ->> 'observacoes' else cfg.observacoes end,
           compra_no_fechamento = coalesce(v_d ->> 'compra_no_fechamento', cfg.compra_no_fechamento),
           fechamento_confirmado = case
               when v_d ? 'fechamento_confirmado' then (v_d ->> 'fechamento_confirmado')::boolean
               when (v_d ? 'dia_fechamento' and (v_d ->> 'dia_fechamento')::integer <> cfg.dia_fechamento)
                    or (v_d ? 'dia_vencimento' and (v_d ->> 'dia_vencimento')::integer <> cfg.dia_vencimento)
                    or (v_d ? 'compra_no_fechamento' and v_d ->> 'compra_no_fechamento' <> cfg.compra_no_fechamento)
                    then false
               else cfg.fechamento_confirmado end
     where cfg.item_despesa_id = p_cartao_id;
    return jsonb_build_object('cartao_id', p_cartao_id);
end
$$;

revoke execute on function financeiro.competencia_da_compra(date, integer, integer, text) from public, anon, authenticated;
revoke execute on function financeiro.situacao_fatura(integer) from public, anon, authenticated;
revoke execute on function financeiro.sugestao_competencia(integer, date) from public, anon, authenticated;
revoke execute on function financeiro.exigir_confirmacao_consolidada(integer, jsonb, numeric) from public, anon, authenticated;
revoke execute on function financeiro.plano_compra(integer, jsonb) from public, anon, authenticated;
revoke execute on function financeiro.ler_dados_cartao(jsonb, boolean) from public, anon, authenticated;
revoke execute on function financeiro.sugerir_competencia(integer, integer, date) from public, anon;
revoke execute on function financeiro.cartoes_do_perfil(integer) from public, anon;
revoke execute on function financeiro.previa_compra(integer, jsonb) from public, anon;
revoke execute on function financeiro.criar_compra(integer, jsonb, uuid) from public, anon;
revoke execute on function financeiro.editar_compra(integer, integer, text, jsonb) from public, anon;
revoke execute on function financeiro.criar_cartao(integer, jsonb, uuid) from public, anon;
revoke execute on function financeiro.editar_cartao(integer, integer, text, jsonb) from public, anon;
grant execute on function financeiro.sugerir_competencia(integer, integer, date) to authenticated;
grant execute on function financeiro.cartoes_do_perfil(integer) to authenticated;
grant execute on function financeiro.previa_compra(integer, jsonb) to authenticated;
grant execute on function financeiro.criar_compra(integer, jsonb, uuid) to authenticated;
grant execute on function financeiro.editar_compra(integer, integer, text, jsonb) to authenticated;
grant execute on function financeiro.criar_cartao(integer, jsonb, uuid) to authenticated;
grant execute on function financeiro.editar_cartao(integer, integer, text, jsonb) to authenticated;

-- ===========================================================================================================
-- FIN-CARTOES-D6-INTEGRIDADE-1 — D6 tambem na geracao de recorrencias do novo motor (D5 preservada).
-- A geracao automatica nao e confirmacao do usuario: compra recorrente com destino em fatura consolidada
-- (FECHADA, nao paga) nao e gravada, nem em outro mes. plano_recorrencia a marca REJEITADA com o motivo;
-- gerar_mes_interno, sob a trava, recusa (P0001, hint CONSOLIDADA) se a fatura foi consolidada depois da
-- previa. Competencia, identidade (recorrencia_competencia/compra_id) e demais itens nao mudam.
-- ===========================================================================================================

-- Mes de destino da compra (primeiro sem fatura paga) quando a fatura dele esta consolidada; NULL se nao.
-- Somente leitura (a geracao trava o cartao e a fatura antes de gravar). Interna.
create function financeiro.fatura_consolidada_no_destino(p_cartao_id integer, p_competencia date)
    returns date
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_mes date := date_trunc('month', p_competencia::timestamp)::date;
    v_fat integer;
begin
    for i in 0..24 loop
        v_fat := financeiro.fatura_do_mes(p_cartao_id, v_mes);
        if v_fat is null then
            return null;
        end if;
        if not financeiro.fatura_esta_paga(v_fat) then
            return case when exists (select 1 from public.conta c where c.id = v_fat and c.status_fatura = 'FECHADA')
                        then v_mes end;
        end if;
        v_mes := (v_mes + interval '1 month')::date;
    end loop;
    return null;
end
$$;
revoke execute on function financeiro.fatura_consolidada_no_destino(integer, date) from public, anon, authenticated;

create or replace function financeiro.plano_recorrencia(p_perfil_id integer, p_mes date)
    returns setof financeiro.linha_plano
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_mes     date := date_trunc('month', p_mes::timestamp)::date;
    v_limite  date := (date_trunc('month', p_mes::timestamp) + interval '1 month')::date;
    v_ns      constant uuid := '7f3a1b2c-4d5e-6f7a-8b9c-0d1e2f3a4b5c';  -- namespace do Flask
    v_pessoal boolean;
    v_consolidada date;  -- FIN-CARTOES-D6-INTEGRIDADE-1
    v_item    record;
    v_cartao  record;
    v_reg     record;
    v_linha   financeiro.linha_plano;
    v_comp    date;
    v_passo   interval;
    v_dia     integer;
    v_motivo  text;
    v_ccs     integer[];
    v_qtd     integer;
    v_id      integer;
begin
    v_pessoal := exists (select 1 from public.perfil_financeiro p where p.id = p_perfil_id and p.nome = 'Pessoal');

    -- 1) Recorrencias: conta (boleto, debito, pix...) ou compra no cartao.
    for v_item in
        select i.*
          from public.item_despesa i
         where (i.perfil_financeiro_id = p_perfil_id or (i.perfil_financeiro_id is null and v_pessoal))
           and coalesce(i.recorrente, false)
         order by i.id
    loop
        v_linha := null;
        v_linha.natureza := case when v_item.meio_pagamento = 'cartao' then 'LANCAMENTO_CARTAO' else 'CONTA' end;
        v_linha.item_despesa_id := v_item.id;
        v_linha.nome := v_item.nome;
        v_linha.valor := v_item.valor;
        v_linha.perfil_destino := v_item.perfil_financeiro_id;
        v_linha.observacoes := coalesce(v_item.descricao, '');
        v_motivo := null;

        if not coalesce(v_item.ativo, true) then
            v_linha.situacao := 'INATIVA';
            v_linha.motivo := 'Recorrencia inativa: nao gera novos lancamentos';
            return next v_linha;
            continue;
        end if;

        if v_item.tipo = 'Agregador' then
            v_motivo := 'Cartao marcado como recorrencia';
        elsif v_item.data_vencimento is null then
            v_motivo := 'Sem data de vencimento';
        elsif coalesce(v_item.tipo_recorrencia, 'mensal') not in ('mensal', 'anual') then
            v_motivo := 'Tipo de recorrencia fora do escopo: ' || v_item.tipo_recorrencia;
        elsif v_item.valor is null or v_item.valor < 0 then
            v_motivo := 'Sem valor valido';
        elsif v_linha.natureza = 'LANCAMENTO_CARTAO' then
            if v_item.cartao_id is null then
                v_motivo := 'Sem cartao';
            elsif v_item.categoria_id is null then
                v_motivo := 'Sem categoria';
            else
                select c.* into v_cartao
                  from public.item_despesa c
                 where c.id = v_item.cartao_id
                   and c.tipo = 'Agregador'
                   and coalesce(c.ativo, true)
                   and (c.perfil_financeiro_id = p_perfil_id or (c.perfil_financeiro_id is null and v_pessoal));
                if not found then
                    v_motivo := 'Cartao inexistente, inativo ou de outro perfil';
                end if;
            end if;

            -- Categoria do cartao como CategoriaCartaoService.resolver_categoria_cartao_para_lancamento.
            if v_motivo is null then
                v_linha.cartao_id := v_item.cartao_id;
                v_linha.categoria_id := v_item.categoria_id;
                if v_item.categoria_cartao_id is not null then
                    if exists (select 1 from public.categoria_cartao cc
                                where cc.id = v_item.categoria_cartao_id
                                  and (cc.perfil_financeiro_id = p_perfil_id or (cc.perfil_financeiro_id is null and v_pessoal))) then
                        v_linha.categoria_cartao_id := v_item.categoria_cartao_id;
                    else
                        v_motivo := 'Categoria do cartao nao encontrada';
                    end if;
                else
                    select array_agg(v.categoria_cartao_id order by v.id) into v_ccs
                      from public.categoria_cartao_despesa v
                      join public.categoria_cartao cc on cc.id = v.categoria_cartao_id
                     where v.categoria_id = v_item.categoria_id
                       and v.ativo and cc.ativo
                       and (v.perfil_financeiro_id = p_perfil_id or (v.perfil_financeiro_id is null and v_pessoal))
                       and (cc.perfil_financeiro_id = p_perfil_id or (cc.perfil_financeiro_id is null and v_pessoal));
                    if cardinality(v_ccs) > 1 then
                        v_motivo := 'Categoria de despesa com mais de uma categoria do cartao ativa';
                    elsif cardinality(v_ccs) = 1 and exists (
                        select 1 from public.cartao_categoria_limite lim
                          join public.categoria_cartao cc on cc.id = lim.categoria_cartao_id
                         where lim.cartao_id = v_item.cartao_id
                           and lim.categoria_cartao_id = v_ccs[1]
                           and lim.ativo and cc.ativo
                           and (lim.perfil_financeiro_id = p_perfil_id or (lim.perfil_financeiro_id is null and v_pessoal))
                           and (cc.perfil_financeiro_id = p_perfil_id or (cc.perfil_financeiro_id is null and v_pessoal))) then
                        v_linha.categoria_cartao_id := v_ccs[1];
                    end if;
                end if;
            end if;
        else
            v_linha.conta_bancaria_id := v_item.conta_bancaria_id;
            v_linha.debito_automatico := coalesce(v_item.meio_pagamento = 'debito_automatico', false);
        end if;

        if v_motivo is not null then
            v_linha.situacao := 'REJEITADA';
            v_linha.motivo := v_motivo;
            v_linha.cartao_id := null;
            v_linha.categoria_id := null;
            v_linha.categoria_cartao_id := null;
            return next v_linha;
            continue;
        end if;

        v_dia := extract(day from v_item.data_vencimento)::integer;
        v_passo := case when coalesce(v_item.tipo_recorrencia, 'mensal') = 'anual' then interval '1 year' else interval '1 month' end;
        v_comp := date_trunc('month', v_item.data_vencimento::timestamp)::date;
        while v_comp <= v_limite loop
            v_linha.competencia := v_comp;
            v_linha.data_vencimento := financeiro.dia_contratual(v_comp, v_dia);
            v_linha.registro_id := null;
            v_linha.motivo := null;
            v_linha.compra_id := case when v_linha.natureza = 'LANCAMENTO_CARTAO' then
                extensions.uuid_generate_v5(v_ns, format('%s-%s', v_item.id, to_char(v_comp, 'YYYY-MM-DD')))::text end;

            select r.* into v_reg
              from financeiro.recorrencia_competencia r
             where r.item_despesa_id = v_item.id and r.natureza = v_linha.natureza and r.competencia = v_comp;
            if found then
                if v_reg.situacao = 'GERADA' and (
                       exists (select 1 from public.conta c where c.id = v_reg.conta_id)
                    or exists (select 1 from public.lancamento_agregado l where l.id = v_reg.lancamento_id)) then
                    v_linha.situacao := 'EXISTENTE';
                    v_linha.registro_id := coalesce(v_reg.conta_id, v_reg.lancamento_id);
                else
                    v_linha.situacao := 'DISPENSADA';
                    v_linha.motivo := case when v_reg.situacao = 'DISPENSADA'
                                           then coalesce(v_reg.motivo, 'Competencia dispensada')
                                           else 'Registro gerado foi removido; nao sera recriado' end;
                end if;
            else
                -- Reconhece o que o Flask (ou outro caminho) ja gravou, sem depender da data.
                if v_linha.natureza = 'CONTA' then
                    select c.id into v_id
                      from public.conta c
                     where c.item_despesa_id = v_item.id
                       and coalesce(c.is_fatura_cartao, false) = false
                       and (date_trunc('month', c.mes_referencia) = v_comp or date_trunc('month', c.data_vencimento) = v_comp)
                     order by c.id
                     limit 1;
                else
                    select l.id into v_id
                      from public.lancamento_agregado l
                     where l.compra_id = v_linha.compra_id
                        -- FIN-FATURA-INTEGRIDADE-1: pelo mes so os antigos, sem compra_id (uma compra de outra
                        -- competencia desviada para este mes por fatura paga nao e a deste mes).
                        or (l.item_despesa_id = v_item.id and l.mes_fatura = v_comp and l.is_recorrente
                            and l.compra_id is null)
                     order by l.id
                     limit 1;
                end if;
                v_linha.situacao := case when v_id is null then 'A_GERAR' else 'EXISTENTE' end;
                -- FIN-CARTOES-D6-INTEGRIDADE-1: a geracao automatica nao e confirmacao do usuario (D6) e nao muda a
                -- competencia (D5): compra recorrente cujo destino e fatura consolidada nao e gerada (nem em silencio,
                -- nem em outro mes). Fica REJEITADA, com o motivo na previa, ate o usuario lancar pela compra, com a
                -- confirmacao. Nada e gravado; a proxima previa reavalia (idempotente).
                if v_linha.natureza = 'LANCAMENTO_CARTAO' and v_linha.situacao = 'A_GERAR' then
                    v_consolidada := financeiro.fatura_consolidada_no_destino(v_linha.cartao_id, v_comp);
                    if v_consolidada is not null then
                        v_linha.situacao := 'REJEITADA';
                        v_linha.motivo := 'Fatura de ' || to_char(v_consolidada, 'MM/YYYY')
                            || ' consolidada: a compra recorrente nao entra sem confirmacao (lance-a pela compra no cartao)';
                    end if;
                end if;
                v_linha.registro_id := v_id;
            end if;
            return next v_linha;
            v_comp := (v_comp + v_passo)::date;
        end loop;
    end loop;

    -- 2) Faturas do mes e do seguinte para cada cartao ativo do perfil.
    for v_cartao in
        select c.id, c.nome, c.perfil_financeiro_id, cfg.dia_vencimento
          from public.item_despesa c
          left join public.config_agregador cfg on cfg.item_despesa_id = c.id
         where (c.perfil_financeiro_id = p_perfil_id or (c.perfil_financeiro_id is null and v_pessoal))
           and c.tipo = 'Agregador'
           and coalesce(c.ativo, true)
         order by c.id
    loop
        foreach v_comp in array array[v_mes, v_limite] loop
            v_linha := null;
            v_linha.natureza := 'FATURA';
            v_linha.item_despesa_id := v_cartao.id;
            v_linha.nome := v_cartao.nome;
            v_linha.competencia := v_comp;
            v_linha.perfil_destino := v_cartao.perfil_financeiro_id;
            v_linha.cartao_id := v_cartao.id;

            select c.id into v_id
              from public.conta c
             where c.item_despesa_id = v_cartao.id
               and c.is_fatura_cartao
               and date_trunc('month', c.cartao_competencia) = v_comp
             order by c.id
             limit 1;
            if v_id is not null then
                v_linha.situacao := 'EXISTENTE';
                v_linha.registro_id := v_id;
            elsif v_cartao.dia_vencimento is null or v_cartao.dia_vencimento not between 1 and 31 then
                v_linha.situacao := 'REJEITADA';
                v_linha.motivo := 'Cartao sem dia de vencimento configurado';
            else
                -- Planejado como CartaoService.calcular_planejado: limites ativos do cartao
                -- no perfil; sem limites, orcamento legado vigente por item agregado.
                select count(*), coalesce(sum(lim.limite_mensal), 0) into v_qtd, v_linha.valor
                  from public.cartao_categoria_limite lim
                 where lim.cartao_id = v_cartao.id and lim.perfil_financeiro_id = p_perfil_id and lim.ativo;
                if v_qtd = 0 then
                    select coalesce(sum(o.valor_teto), 0) into v_linha.valor
                      from public.item_agregado ia
                      cross join lateral (
                          select oa.valor_teto
                            from public.orcamento_agregado oa
                           where oa.item_agregado_id = ia.id
                             and oa.ativo
                             and oa.vigencia_inicio <= v_comp
                             and (oa.vigencia_fim is null or oa.vigencia_fim >= v_comp)
                           order by oa.id
                           limit 1
                      ) o
                     where ia.item_despesa_id = v_cartao.id;
                end if;
                v_linha.situacao := 'A_GERAR';
                v_linha.data_vencimento := financeiro.dia_contratual(v_comp, v_cartao.dia_vencimento);
            end if;
            return next v_linha;
        end loop;
    end loop;
end
$$;

create or replace function financeiro.gerar_mes_interno(p_perfil_id integer, p_mes date, p_total_previsto integer,
                                                        p_dispensar jsonb default '[]'::jsonb)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_mes        date;
    v_linhas     financeiro.linha_plano[];
    v_linha      financeiro.linha_plano;
    v_disp       record;
    v_a_gerar    integer;
    v_exec       bigint;
    v_id         integer;
    v_contas     integer := 0;
    v_lancs      integer := 0;
    v_faturas    integer := 0;
    v_dispensas  integer := 0;
    v_destino    date;  -- FIN-FATURA-INTEGRIDADE-1: mes da compra recorrente (desvia de fatura paga)
    v_corrida    integer := 0;  -- faturas criadas ao mesmo tempo por outro caminho
    v_registros  jsonb := '[]'::jsonb;
    v_resumo     jsonb;
begin
    if not financeiro.pode_gerir_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    if p_mes is null or p_total_previsto is null or p_total_previsto < 0 then
        raise exception 'Mes e total previsto sao obrigatorios' using errcode = '22023';
    end if;
    p_dispensar := coalesce(p_dispensar, '[]'::jsonb);
    if jsonb_typeof(p_dispensar) <> 'array' then
        raise exception 'Dispensas devem ser uma lista' using errcode = '22023';
    end if;
    v_mes := date_trunc('month', p_mes::timestamp)::date;

    -- Uma geracao por perfil de cada vez (abas ou cliques concorrentes).
    perform pg_advisory_xact_lock(20261023, p_perfil_id);

    select coalesce(array_agg(p order by p.competencia, p.natureza, p.item_despesa_id), '{}')
      into v_linhas
      from financeiro.plano_recorrencia(p_perfil_id, v_mes) p;
    select count(*) into v_a_gerar from unnest(v_linhas) l where l.situacao = 'A_GERAR';

    if v_a_gerar = 0 and jsonb_array_length(p_dispensar) = 0 then
        return jsonb_build_object('execucao_id', null, 'mes', v_mes,
            'criadas', jsonb_build_object('contas', 0, 'lancamentos', 0, 'faturas', 0, 'total', 0),
            'existentes', (select count(*) from unnest(v_linhas) l where l.situacao = 'EXISTENTE'),
            'dispensadas', (select count(*) from unnest(v_linhas) l where l.situacao = 'DISPENSADA'),
            'dispensadas_agora', 0,
            'rejeitadas', (select count(*) from unnest(v_linhas) l where l.situacao = 'REJEITADA'),
            'registros', '[]'::jsonb);
    end if;
    if v_a_gerar <> p_total_previsto then
        raise exception 'A previa mudou desde a confirmacao (previstos %, agora %). Revise e confirme de novo.',
            p_total_previsto, v_a_gerar;
    end if;
    if v_a_gerar > 500 then
        raise exception 'Geracao excede o limite de 500 registros (%).', v_a_gerar;
    end if;

    -- FIN-FATURA-INTEGRIDADE-1: ordem global de travas (cartao -> faturas): os cartoes das linhas a
    -- gerar ficam travados, em ordem de id, antes de qualquer fatura.
    perform 1 from public.item_despesa i
     where i.id in (select l.cartao_id from unnest(v_linhas) l where l.situacao = 'A_GERAR' and l.cartao_id is not null)
     order by i.id
       for update;

    insert into financeiro.geracao_execucao (perfil_financeiro_id, mes, user_id, resumo)
    values (p_perfil_id, v_mes, (select auth.uid()), '{}'::jsonb)
    returning id into v_exec;

    for v_disp in
        select d.natureza, d.item_id, date_trunc('month', d.competencia::timestamp)::date as competencia, d.motivo
          from jsonb_to_recordset(p_dispensar) as d(natureza text, item_id integer, competencia date, motivo text)
    loop
        if not exists (select 1 from unnest(v_linhas) l
                        where l.situacao = 'A_GERAR' and l.natureza in ('CONTA', 'LANCAMENTO_CARTAO')
                          and l.natureza = v_disp.natureza and l.item_despesa_id = v_disp.item_id
                          and l.competencia = v_disp.competencia) then
            raise exception 'Dispensa invalida: so competencias a gerar de recorrencias podem ser dispensadas'
                using errcode = '22023';
        end if;
        insert into financeiro.recorrencia_competencia
            (item_despesa_id, natureza, competencia, situacao, execucao_id, motivo, user_id)
        values (v_disp.item_id, v_disp.natureza, v_disp.competencia, 'DISPENSADA', v_exec,
                coalesce(left(nullif(btrim(v_disp.motivo), ''), 200), 'Dispensada pelo usuario'), (select auth.uid()));
        v_dispensas := v_dispensas + 1;
    end loop;

    foreach v_linha in array v_linhas loop
        continue when v_linha.situacao <> 'A_GERAR';
        continue when exists (select 1 from financeiro.recorrencia_competencia r
                               where r.item_despesa_id = v_linha.item_despesa_id and r.natureza = v_linha.natureza
                                 and r.competencia = v_linha.competencia and r.situacao = 'DISPENSADA');
        if v_linha.natureza = 'CONTA' then
            insert into public.conta (perfil_financeiro_id, item_despesa_id, mes_referencia, descricao, valor,
                                      data_vencimento, status_pagamento, debito_automatico, conta_bancaria_id,
                                      observacoes, is_fatura_cartao, estouro_orcamento, status_fatura, criado_em)
            values (v_linha.perfil_destino, v_linha.item_despesa_id, v_linha.competencia, v_linha.nome, v_linha.valor,
                    v_linha.data_vencimento, 'Pendente', v_linha.debito_automatico, v_linha.conta_bancaria_id,
                    v_linha.observacoes, false, false, 'ABERTA', now() at time zone 'utc')
            returning id into v_id;
            insert into financeiro.recorrencia_competencia
                (item_despesa_id, natureza, competencia, situacao, conta_id, execucao_id, user_id)
            values (v_linha.item_despesa_id, 'CONTA', v_linha.competencia, 'GERADA', v_id, v_exec, (select auth.uid()));
            v_contas := v_contas + 1;
        elsif v_linha.natureza = 'LANCAMENTO_CARTAO' then
            -- FIN-FATURA-INTEGRIDADE-1: fatura paga nao recebe a compra recorrente; ela vai para a
            -- proxima fatura nao paga, com a competencia original registrada. A identidade continua a
            -- da competencia (recorrencia_competencia e compra_id), entao ela nao e gerada de novo.
            v_destino := financeiro.fatura_elegivel_existente(v_linha.cartao_id, v_linha.competencia);
            -- FIN-CARTOES-D6-INTEGRIDADE-1: a fatura de destino (travada acima) foi consolidada depois da previa:
            -- nada entra em silencio. Erro controlado; a geracao inteira e desfeita e a nova previa mostra o motivo.
            if exists (select 1 from public.conta c
                        where c.id = financeiro.fatura_do_mes(v_linha.cartao_id, v_destino) and c.status_fatura = 'FECHADA') then
                raise exception 'A fatura de % foi consolidada depois da previa: a compra recorrente "%" nao entra sem confirmacao. Revise e confirme de novo.',
                    to_char(v_destino, 'MM/YYYY'), v_linha.nome using errcode = 'P0001', hint = 'CONSOLIDADA';
            end if;
            insert into public.lancamento_agregado (perfil_financeiro_id, cartao_id, item_agregado_id, categoria_cartao_id,
                                                    categoria_id, descricao, valor, data_compra, mes_fatura,
                                                    numero_parcela, total_parcelas, observacoes, is_recorrente,
                                                    item_despesa_id, compra_id, is_importado, criado_em,
                                                    mes_fatura_original)
            values (v_linha.perfil_destino, v_linha.cartao_id, null, v_linha.categoria_cartao_id,
                    v_linha.categoria_id, v_linha.nome, v_linha.valor, v_linha.data_vencimento, v_destino,
                    1, 1, v_linha.observacoes, true,
                    v_linha.item_despesa_id, v_linha.compra_id, false, now() at time zone 'utc',
                    nullif(v_linha.competencia, v_destino))
            returning id into v_id;
            insert into financeiro.recorrencia_competencia
                (item_despesa_id, natureza, competencia, situacao, lancamento_id, execucao_id, user_id)
            values (v_linha.item_despesa_id, 'LANCAMENTO_CARTAO', v_linha.competencia, 'GERADA', v_id, v_exec,
                    (select auth.uid()));
            v_lancs := v_lancs + 1;
        else
            insert into public.conta (perfil_financeiro_id, item_despesa_id, mes_referencia, descricao, valor,
                                      valor_planejado, valor_executado, data_vencimento, status_pagamento,
                                      is_fatura_cartao, cartao_competencia, estouro_orcamento, debito_automatico,
                                      status_fatura, criado_em)
            values (v_linha.perfil_destino, v_linha.item_despesa_id, v_linha.competencia,
                    'Fatura ' || v_linha.nome || ' - ' || to_char(v_linha.competencia, 'MM/YYYY'),
                    v_linha.valor, v_linha.valor, 0, v_linha.data_vencimento, 'Pendente',
                    true, v_linha.competencia, false, false, 'ABERTA', now() at time zone 'utc')
            on conflict (item_despesa_id, cartao_competencia) where is_fatura_cartao do nothing
            returning id into v_id;
            -- FIN-FATURA-UNICA-1: outra transacao (ex.: compra no Flask) criou a mesma fatura
            -- depois do plano; o indice unico decidiu e a existente e reconhecida.
            if v_id is null then
                v_corrida := v_corrida + 1;
                continue;
            end if;
            v_faturas := v_faturas + 1;
        end if;
        v_registros := v_registros || jsonb_build_object('natureza', v_linha.natureza, 'item_id', v_linha.item_despesa_id,
                                                         'competencia', v_linha.competencia, 'registro_id', v_id);
    end loop;

    v_resumo := jsonb_build_object(
        'execucao_id', v_exec,
        'mes', v_mes,
        'criadas', jsonb_build_object('contas', v_contas, 'lancamentos', v_lancs, 'faturas', v_faturas,
                                      'total', v_contas + v_lancs + v_faturas),
        'existentes', (select count(*) from unnest(v_linhas) l where l.situacao = 'EXISTENTE') + v_corrida,
        'dispensadas', (select count(*) from unnest(v_linhas) l where l.situacao = 'DISPENSADA') + v_dispensas,
        'dispensadas_agora', v_dispensas,
        'rejeitadas', (select count(*) from unnest(v_linhas) l where l.situacao = 'REJEITADA'),
        'rejeicoes', coalesce((select jsonb_agg(jsonb_build_object('item_id', l.item_despesa_id, 'nome', l.nome,
                                                                    'natureza', l.natureza, 'competencia', l.competencia,
                                                                    'motivo', l.motivo))
                                 from unnest(v_linhas) l where l.situacao = 'REJEITADA'), '[]'::jsonb),
        'registros', v_registros);
    update financeiro.geracao_execucao set resumo = v_resumo where id = v_exec;
    return v_resumo;
end
$$;

-- create or replace preserva os privilegios (internas: sem EXECUTE para o navegador). Reafirmado:
revoke execute on function financeiro.plano_recorrencia(integer, date) from public, anon, authenticated;
revoke execute on function financeiro.gerar_mes_interno(integer, date, integer, jsonb) from public, anon, authenticated;
