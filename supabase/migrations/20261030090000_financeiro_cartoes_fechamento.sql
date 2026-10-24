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
