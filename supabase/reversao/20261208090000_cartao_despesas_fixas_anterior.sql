-- Reversao de 20261208090000 (FIN-CARTAO-DESPESAS-FIXAS-01): volta as leituras e a importacao ao texto anterior e remove os objetos
-- novos. Recusada enquanto houver ocorrencia reconciliada vigente (reverter antes com
-- financeiro.reverter_ocorrencia_recorrencia, para nao perder o previsto e as compras absorvidas) ou apelido ativo. So com
-- autorizacao, retirando a versao de supabase_migrations.schema_migrations.

do $$
begin
    if exists (select 1 from financeiro.ocorrencia_recorrencia_cartao where revertida_em is null) then
        raise exception 'Ha ocorrencia reconciliada vigente: reverta-as antes de remover a migration 20261208090000';
    end if;
    if exists (select 1 from financeiro.recorrencia_apelido where ativo) then
        raise exception 'Ha apelido de cobranca ativo: remova-os antes de remover a migration 20261208090000';
    end if;
end
$$;

-- gasto_categoria_fatura: texto de 20261104090000.
create or replace function financeiro.gasto_categoria_fatura(p_perfil_id integer, p_cartao_id integer, p_categoria_cartao_id integer,
                                                  p_mes date)
    returns numeric
    language sql
    stable
    security definer
    set search_path = ''
as $$
    select coalesce(sum(l.valor), 0) from public.lancamento_agregado l
     where l.cartao_id = p_cartao_id and l.categoria_cartao_id = p_categoria_cartao_id and l.mes_fatura = p_mes
       and financeiro.pertence_ao_perfil(l.perfil_financeiro_id, p_perfil_id)
$$;

-- fatura_por_categoria: texto de 20261104090000.
create or replace function financeiro.fatura_por_categoria(p_perfil_id integer, p_cartao_id integer, p_mes date)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_mes        date := date_trunc('month', p_mes::timestamp)::date;
    v_grupos     jsonb;
    v_total      numeric;
    v_com        numeric;
    v_sem        numeric;
    v_limite     numeric;
    v_vinculadas numeric;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    perform financeiro.cartao_do_perfil(p_perfil_id, p_cartao_id, false);
    with lanc as (
        select l.valor, l.categoria_cartao_id from public.lancamento_agregado l
         where l.cartao_id = p_cartao_id and l.mes_fatura = v_mes
           and financeiro.pertence_ao_perfil(l.perfil_financeiro_id, p_perfil_id)
    ),
    limites as (
        select lim.id, lim.categoria_cartao_id, lim.limite_mensal from public.cartao_categoria_limite lim
         where lim.cartao_id = p_cartao_id and lim.perfil_financeiro_id = p_perfil_id and lim.ativo
    ),
    grupos as (
        -- 1. limites ativos (na ordem do vinculo)
        select 1 as ordem, lim.id as ordem2, lim.categoria_cartao_id, lim.limite_mensal,
               coalesce((select sum(x.valor) from lanc x where x.categoria_cartao_id = lim.categoria_cartao_id), 0) as gasto,
               (select count(*) from lanc x where x.categoria_cartao_id = lim.categoria_cartao_id) as qtd,
               'categoria_cartao' as tipo
          from limites lim
        union all
        -- 2. categorias com lancamento mas sem limite ativo neste cartao
        select 2, min(cc.id), x.categoria_cartao_id, 0, sum(x.valor), count(*), 'categoria_sem_limite'
          from lanc x join public.categoria_cartao cc on cc.id = x.categoria_cartao_id
         where x.categoria_cartao_id is not null
           and x.categoria_cartao_id not in (select l2.categoria_cartao_id from limites l2)
         group by x.categoria_cartao_id
        union all
        -- 3. sem Categoria do Cartao
        select 3, 0, null, null, sum(x.valor), count(*), 'sem_categoria'
          from lanc x where x.categoria_cartao_id is null having count(*) > 0
    )
    select coalesce(jsonb_agg(jsonb_build_object(
               'categoria_cartao_id', g.categoria_cartao_id,
               'categoria_cartao_nome', case when g.tipo = 'sem_categoria' then 'Sem Categoria do Cartao'
                                             else coalesce(cc.nome, 'Categoria do Cartao') end,
               'categoria_cartao_cor', cc.cor,
               'categoria_cartao_icone', cc.icone,
               'limite_mensal', g.limite_mensal,
               'gasto_atual', g.gasto,
               'disponivel', case when g.tipo = 'categoria_cartao' then g.limite_mensal - g.gasto end,
               'percentual', case when g.tipo = 'categoria_cartao' then
                   case when g.limite_mensal > 0 then round(g.gasto / g.limite_mensal * 100, 2) else 0 end end,
               'percentual_utilizado', case when g.tipo = 'categoria_cartao' then
                   case when g.limite_mensal > 0 then round(g.gasto / g.limite_mensal * 100, 2) else 0 end end,
               'status', case when g.tipo = 'categoria_cartao' then financeiro.status_consumo(g.gasto, g.limite_mensal)
                              else 'Revisar' end,
               'quantidade_lancamentos', g.qtd,
               'vinculada_ao_cartao', g.tipo = 'categoria_cartao',
               'sem_categoria', g.tipo = 'sem_categoria',
               'categoria_sem_limite', g.tipo = 'categoria_sem_limite',
               'avisos', case g.tipo when 'sem_categoria' then '["Lancamentos sem Categoria do Cartao devem ser revisados."]'::jsonb
                                     when 'categoria_sem_limite' then '["Categoria sem limite neste cartao."]'::jsonb
                                     else '[]'::jsonb end,
               'tipo_grupo', g.tipo) order by g.ordem, g.ordem2), '[]'::jsonb)
      into v_grupos
      from grupos g left join public.categoria_cartao cc on cc.id = g.categoria_cartao_id;

    select coalesce(sum(l.valor), 0),
           coalesce(sum(l.valor) filter (where l.categoria_cartao_id is not null), 0),
           coalesce(sum(l.valor) filter (where l.categoria_cartao_id is null), 0),
           coalesce(sum(l.valor) filter (where l.categoria_cartao_id in (
               select lim.categoria_cartao_id from public.cartao_categoria_limite lim
                where lim.cartao_id = p_cartao_id and lim.perfil_financeiro_id = p_perfil_id and lim.ativo)), 0)
      into v_total, v_com, v_sem, v_vinculadas
      from public.lancamento_agregado l
     where l.cartao_id = p_cartao_id and l.mes_fatura = v_mes
       and financeiro.pertence_ao_perfil(l.perfil_financeiro_id, p_perfil_id);
    select coalesce(sum(lim.limite_mensal), 0) into v_limite from public.cartao_categoria_limite lim
     where lim.cartao_id = p_cartao_id and lim.perfil_financeiro_id = p_perfil_id and lim.ativo;

    return jsonb_build_object(
        'cartao_id', p_cartao_id,
        'mes_referencia', to_char(v_mes, 'YYYY-MM'),
        'total_fatura', v_total,
        'total_com_categoria', v_com,
        'total_sem_categoria_cartao', v_sem,
        'limite_total', v_limite,
        'disponivel_total', v_limite - v_vinculadas,
        'percentual_total', case when v_limite > 0 then round(v_vinculadas / v_limite * 100, 2) else 0 end,
        'status_total', financeiro.status_consumo(v_vinculadas, v_limite),
        'situacao_fatura', financeiro.situacao_fatura(financeiro.fatura_do_mes(p_cartao_id, v_mes)),
        'categorias', v_grupos);
end
$$;

-- lancamentos_fatura_por_categoria: texto de 20261104090000.
create or replace function financeiro.lancamentos_fatura_por_categoria(p_perfil_id integer, p_cartao_id integer, p_mes date,
                                                            p_filtro text)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_mes    date := date_trunc('month', p_mes::timestamp)::date;
    v_filtro text := coalesce(nullif(btrim(p_filtro), ''), 'todos');
    v_cc     integer;
    v_gerir  boolean;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    perform financeiro.cartao_do_perfil(p_perfil_id, p_cartao_id, false);
    if v_filtro not in ('todos', 'sem_categoria') then
        if v_filtro !~ '^[0-9]{1,9}$' then
            raise exception 'categoria_cartao_id invalido' using errcode = '22023';
        end if;
        v_cc := v_filtro::integer;
    end if;
    v_gerir := financeiro.pode_gerir_perfil(p_perfil_id);
    return jsonb_build_object(
        'cartao_id', p_cartao_id,
        'mes_referencia', to_char(v_mes, 'YYYY-MM'),
        'categoria_cartao_id', v_filtro,
        'lancamentos', coalesce((
            select jsonb_agg(jsonb_build_object(
                       'id', l.id,
                       'data', l.data_compra,
                       'descricao', coalesce(nullif(l.descricao_exibida, ''), l.descricao),
                       'descricao_original', coalesce(l.descricao_original, l.descricao),
                       'valor', l.valor,
                       'categoria_id', l.categoria_id,
                       'categoria_nome', cat.nome,
                       'categoria_cartao_id', l.categoria_cartao_id,
                       'categoria_cartao_nome', cc.nome,
                       'origem', coalesce(l.origem_importacao, case when coalesce(l.is_recorrente, false) then 'recorrencia'
                                                                    else 'manual' end),
                       'parcela_atual', l.numero_parcela,
                       'parcelas_total', l.total_parcelas,
                       'compra_id', l.compra_id,
                       'status_classificacao', case
                           when l.categoria_cartao_id is null then 'sem_categoria_cartao'
                           when not exists (select 1 from public.cartao_categoria_limite lim
                                             where lim.cartao_id = p_cartao_id and lim.perfil_financeiro_id = p_perfil_id
                                               and lim.ativo and lim.categoria_cartao_id = l.categoria_cartao_id)
                               then 'categoria_sem_limite'
                           else 'classificado' end,
                       'bloqueio', financeiro.bloqueio_da_parcela(l.id),
                       'pode_editar', v_gerir and financeiro.bloqueio_da_parcela(l.id) is null,
                       'versao', financeiro.versao_compra(l.id))
                   order by l.data_compra, l.id)
              from public.lancamento_agregado l
              left join public.categoria cat on cat.id = l.categoria_id
              left join public.categoria_cartao cc on cc.id = l.categoria_cartao_id
             where l.cartao_id = p_cartao_id and l.mes_fatura = v_mes
               and financeiro.pertence_ao_perfil(l.perfil_financeiro_id, p_perfil_id)
               and (v_filtro = 'todos' or (v_filtro = 'sem_categoria' and l.categoria_cartao_id is null)
                    or l.categoria_cartao_id = v_cc)), '[]'::jsonb));
end
$$;

-- contas_do_mes: texto de 20261022090000.
create or replace function financeiro.contas_do_mes(p_perfil_id integer, p_mes date)
    returns table (
        id integer, grupo text, nome text, valor numeric, valor_previsto numeric, valor_executado numeric,
        data_vencimento date, data_pagamento date, situacao text, status_pagamento text,
        categoria_nome text, categoria_cor text, cartao_id integer, cartao_nome text,
        numero_parcela integer, total_parcelas integer, debito_automatico boolean
    )
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_mes date;
    v_hoje date := (now() at time zone 'America/Sao_Paulo')::date;
    v_pessoal boolean;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    if p_mes is null then
        raise exception 'Mes de competencia obrigatorio' using errcode = '22023';
    end if;
    v_mes := date_trunc('month', p_mes)::date;
    v_pessoal := exists (select 1 from public.perfil_financeiro p where p.id = p_perfil_id and p.nome = 'Pessoal');

    return query
    with contas as (
        select c.*
          from public.conta c
         where (c.perfil_financeiro_id = p_perfil_id or (c.perfil_financeiro_id is null and v_pessoal))
           and (
                (coalesce(c.is_fatura_cartao, false) = false and date_trunc('month', c.mes_referencia) = v_mes)
             or (c.is_fatura_cartao = true and date_trunc('month', c.cartao_competencia) = v_mes)
           )
    ),
    gastos as (
        -- gasto do mes por cartao e categoria de cartao, no perfil (mes_fatura = 1o dia, como no Flask)
        select l.cartao_id, l.categoria_cartao_id, sum(l.valor) as total
          from public.lancamento_agregado l
         where (l.perfil_financeiro_id = p_perfil_id or (l.perfil_financeiro_id is null and v_pessoal))
           and l.mes_fatura = v_mes
         group by l.cartao_id, l.categoria_cartao_id
    ),
    faturas as (
        select c.id,
               coalesce((select sum(g.total) from gastos g where g.cartao_id = c.item_despesa_id), 0) as executado,
               coalesce((select sum(greatest(lim.limite_mensal - coalesce(g.total, 0), 0))
                           from public.cartao_categoria_limite lim
                           left join gastos g
                             on g.cartao_id = lim.cartao_id and g.categoria_cartao_id = lim.categoria_cartao_id
                          where lim.cartao_id = c.item_despesa_id and lim.ativo), 0) as complemento
          from contas c
         where c.is_fatura_cartao = true
    )
    select c.id,
           case when c.is_fatura_cartao then 'FATURA' else 'DESPESA' end,
           c.descricao::text,
           case
               when not coalesce(c.is_fatura_cartao, false) then c.valor
               when c.status_pagamento = 'Pago' then f.executado
               else f.executado + f.complemento
           end,
           case when c.is_fatura_cartao then f.executado + f.complemento end,
           case when c.is_fatura_cartao then f.executado end,
           c.data_vencimento,
           c.data_pagamento,
           case
               when c.status_pagamento = 'Pago' then 'PAGA'
               when c.status_pagamento = 'Atrasado' or c.data_vencimento < v_hoje then 'VENCIDA'
               else 'PENDENTE'
           end,
           coalesce(c.status_pagamento, 'Pendente')::text,
           cat.nome::text,
           cat.cor::text,
           case when c.is_fatura_cartao then c.item_despesa_id end,
           case when c.is_fatura_cartao then item.nome::text end,
           c.numero_parcela,
           c.total_parcelas,
           coalesce(c.debito_automatico, false)
      from contas c
      left join faturas f on f.id = c.id
      left join public.item_despesa item on item.id = c.item_despesa_id
      left join public.categoria cat on cat.id = item.categoria_id
     order by 2, c.data_vencimento, c.descricao, c.id;
end
$$;

-- faturas_do_mes: texto de 20261028090000.
create or replace function financeiro.faturas_do_mes(p_perfil_id integer, p_mes date)
    returns table (cartao_id integer, cartao_nome text, fatura_id integer, competencia date, data_vencimento date,
                   situacao text, valor_executado numeric, valor_previsto numeric, compras integer, pode_gerir boolean)
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_mes     date;
    v_pessoal boolean;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    v_mes := date_trunc('month', p_mes::timestamp)::date;
    v_pessoal := exists (select 1 from public.perfil_financeiro p where p.id = p_perfil_id and p.nome = 'Pessoal');
    return query
    with cartoes as (
        select i.id, i.nome from public.item_despesa i
         where i.tipo = 'Agregador' and coalesce(i.ativo, true) and financeiro.pertence_ao_perfil(i.perfil_financeiro_id, p_perfil_id)
    ),
    gastos as (
        select l.cartao_id, l.categoria_cartao_id, sum(l.valor) as gasto, count(*) as qtd
          from public.lancamento_agregado l
         where l.mes_fatura = v_mes and (l.perfil_financeiro_id = p_perfil_id or (l.perfil_financeiro_id is null and v_pessoal))
         group by 1, 2
    )
    select c.id, c.nome::text, f.id, v_mes, f.data_vencimento,
           case when f.id is null then 'SEM_FATURA'
                when f.status_pagamento = 'Pago' or f.status_fatura = 'PAGA' then 'PAGA'
                when f.status_fatura = 'FECHADA' then 'FECHADA' else 'ABERTA' end,
           coalesce((select sum(g.gasto) from gastos g where g.cartao_id = c.id), 0),
           case when f.status_pagamento = 'Pago' then coalesce((select sum(g.gasto) from gastos g where g.cartao_id = c.id), 0)
                else coalesce((select sum(g.gasto) from gastos g where g.cartao_id = c.id), 0)
                     + coalesce((select sum(greatest(lim.limite_mensal - coalesce(g.gasto, 0), 0))
                                   from public.cartao_categoria_limite lim
                                   left join gastos g on g.cartao_id = c.id and g.categoria_cartao_id = lim.categoria_cartao_id
                                  where lim.cartao_id = c.id and lim.ativo), 0) end,
           coalesce((select sum(g.qtd) from gastos g where g.cartao_id = c.id), 0)::integer,
           financeiro.pode_gerir_perfil(p_perfil_id)
      from cartoes c
      left join public.conta f on f.id = financeiro.fatura_do_mes(c.id, v_mes)
     order by c.nome;
end
$$;

-- dashboard_resumo_tela: texto de 20261114090000.
create or replace function financeiro.dashboard_resumo_tela(p_perfil_id integer, p_mes_referencia text)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_hoje        date := (now() at time zone 'America/Sao_Paulo')::date;
    v_valor       text := btrim(coalesce(p_mes_referencia, ''));
    v_inicio      date;
    v_fim         date;
    v_dias        integer;
    v_saldo       numeric;
    v_receitas    numeric;
    v_recebidas   numeric;
    v_despesas    numeric;
    v_fat_total   numeric;
    v_fat_qtd     integer;
    v_rec_qtd     integer;
    v_rec_total   numeric;
    v_venc        jsonb;
    v_venc_total  numeric;
    v_categorias  jsonb;
    v_cartoes     jsonb;
    v_lim_total   numeric;
    v_uso_total   numeric;
    v_mobilidade  jsonb;
    v_alertas     jsonb := '[]'::jsonb;
    v_fluxo       jsonb;
    v_prev_mes    numeric;
    v_prev_pend   integer;
    v_prev_conf   integer;
    v_qtd         integer;
    v_venc_hoje   integer;
    v_percentual  numeric;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    -- _periodo_mes: YYYY-MM ou YYYY-MM-DD validos; senao, mes atual.
    if length(v_valor) = 7 then
        v_valor := v_valor || '-01';
    end if;
    begin
        if v_valor ~ '^\d{4}-\d{1,2}-\d{1,2}$' then
            v_inicio := date_trunc('month', v_valor::date)::date;
        end if;
    exception when others then
        v_inicio := null;
    end;
    v_inicio := coalesce(v_inicio, date_trunc('month', v_hoje)::date);
    v_fim := (v_inicio + interval '1 month' - interval '1 day')::date;
    v_dias := extract(day from v_fim)::integer;

    select coalesce(sum(cb.saldo_atual), 0) into v_saldo from public.conta_bancaria cb
     where financeiro.pertence_ao_perfil(cb.perfil_financeiro_id, p_perfil_id) and cb.status = 'ATIVO';
    -- D2: previsto = orcado + recebido sem previsao; o recebido de uma previsao nao soma de novo.
    v_receitas := coalesce((select sum(o.valor_esperado) from public.receita_orcamento o
                             where financeiro.pertence_ao_perfil(o.perfil_financeiro_id, p_perfil_id)
                               and date_trunc('month', o.mes_referencia) = v_inicio), 0)
                + coalesce((select sum(r.valor_recebido) from public.receita_realizada r
                             where financeiro.pertence_ao_perfil(r.perfil_financeiro_id, p_perfil_id)
                               and date_trunc('month', r.mes_referencia) = v_inicio and r.orcamento_id is null), 0);
    v_recebidas := coalesce((select sum(r.valor_recebido) from public.receita_realizada r
                              where financeiro.pertence_ao_perfil(r.perfil_financeiro_id, p_perfil_id)
                                and date_trunc('month', r.mes_referencia) = v_inicio), 0);
    v_despesas := coalesce((select sum(c.valor) from public.conta c
                             where financeiro.pertence_ao_perfil(c.perfil_financeiro_id, p_perfil_id)
                               and date_trunc('month', c.mes_referencia) = v_inicio and c.is_fatura_cartao is not true), 0)
                + coalesce((select sum(d.valor_previsto) from public.despesa_prevista d
                             where financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_perfil_id)
                               and date_trunc('month', d.data_atual_prevista) = v_inicio
                               and d.status in ('PREVISTA', 'ADIADA')), 0);

    -- _fluxo_caixa: 5 pontos lineares no mes.
    select jsonb_build_object(
               'labels', jsonb_agg(to_char(p.dia, 'FM00') || '/' || to_char(v_inicio, 'MM') order by p.ponto),
               'entradas', jsonb_agg(round(v_receitas * p.ponto / 5, 2) order by p.ponto),
               'saidas', jsonb_agg(round(v_despesas * p.ponto / 5, 2) order by p.ponto),
               'saldo_projetado', jsonb_agg(round(v_saldo + v_receitas * p.ponto / 5 - v_despesas * p.ponto / 5, 2) order by p.ponto),
               'resumo', jsonb_build_object('receitas_previstas', round(v_receitas, 2), 'despesas_previstas', round(v_despesas, 2),
                                            'saldo_final_projetado', round(v_saldo + v_receitas - v_despesas, 2),
                                            'receitas_recebidas', round(v_recebidas, 2),
                                            'diferenca_receitas', round(v_recebidas - v_receitas, 2)),
               'tipo', 'projecao_simplificada')
      into v_fluxo
      from (select g ponto, least(v_dias, 1 + (g - 1) * greatest(1, v_dias / 5)) dia from generate_series(1, 5) g) p;

    -- _total_faturas_periodo
    select coalesce(sum(coalesce(nullif(c.valor_consolidado, 0), nullif(c.valor_executado, 0), nullif(c.valor_planejado, 0), c.valor, 0)), 0),
           count(*)
      into v_fat_total, v_fat_qtd
      from public.conta c
     where financeiro.pertence_ao_perfil(c.perfil_financeiro_id, p_perfil_id) and c.is_fatura_cartao
       and date_trunc('month', c.mes_referencia) = v_inicio and c.status_pagamento is distinct from 'Pago'
       and c.status_pagamento is not null;

    -- _recorrencias_ativas
    select count(*), coalesce(sum(i.valor), 0) into v_rec_qtd, v_rec_total from public.item_despesa i
     where financeiro.pertence_ao_perfil(i.perfil_financeiro_id, p_perfil_id) and i.recorrente and i.ativo;

    -- _contas_a_vencer_7_dias (contas e faturas pendentes; 8 primeiras)
    select coalesce(jsonb_agg(jsonb_build_object(
               'id', x.id, 'data', x.data_vencimento, 'descricao', x.descricao,
               'origem', case when x.is_fatura_cartao then 'Fatura' else 'Conta' end, 'valor', round(coalesce(x.valor, 0), 2),
               'tipo', case when x.is_fatura_cartao then 'fatura' else 'despesa' end,
               'status_visual', case when x.data_vencimento = v_hoje then 'vence_hoje' else (x.data_vencimento - v_hoje) || ' dias' end)
           order by x.data_vencimento, x.id), '[]'::jsonb),
           coalesce(sum(coalesce(x.valor, 0)), 0),
           count(*) filter (where x.data_vencimento = v_hoje)
      into v_venc, v_venc_total, v_venc_hoje
      from (select c.* from public.conta c
             where financeiro.pertence_ao_perfil(c.perfil_financeiro_id, p_perfil_id)
               and c.data_vencimento between v_hoje and v_hoje + 7 and c.status_pagamento = 'Pendente'
             order by c.data_vencimento, c.id limit 8) x;

    -- _categorias_cartao: limites ativos + gastos do mes da fatura; 6 maiores gastos.
    with limites as (
        select l.categoria_cartao_id id, sum(coalesce(l.limite_mensal, 0)) limite, min(l.id) ordem
          from public.cartao_categoria_limite l join public.categoria_cartao cc on cc.id = l.categoria_cartao_id
         where financeiro.pertence_ao_perfil(l.perfil_financeiro_id, p_perfil_id) and l.ativo
         group by 1),
    gastos as (
        select la.categoria_cartao_id id, sum(coalesce(la.valor, 0)) gasto
          from public.lancamento_agregado la join public.categoria_cartao cc on cc.id = la.categoria_cartao_id
         where financeiro.pertence_ao_perfil(la.perfil_financeiro_id, p_perfil_id)
           and date_trunc('month', la.mes_fatura) = v_inicio
         group by 1),
    juntas as (
        select coalesce(l.id, g.id) id, coalesce(l.limite, 0) limite, coalesce(g.gasto, 0) gasto,
               case when l.id is not null then 0 else 1 end grupo, coalesce(l.ordem, g.id) ordem
          from limites l full join gastos g on g.id = l.id)
    select coalesce(jsonb_agg(jsonb_build_object(
               'categoria_cartao_id', j.id, 'nome', cc.nome, 'cor', cc.cor, 'icone', cc.icone,
               'limite', round(j.limite, 2), 'gasto', round(j.gasto, 2), 'disponivel', round(j.limite - j.gasto, 2),
               'percentual', financeiro.percentual_flask(j.gasto, j.limite),
               'status', financeiro.status_consumo_flask(financeiro.percentual_flask(j.gasto, j.limite)))
           order by j.gasto desc, j.grupo, j.ordem), '[]'::jsonb)
      into v_categorias
      from (select * from juntas order by gasto desc, grupo, ordem limit 6) j
      join public.categoria_cartao cc on cc.id = j.id;

    -- _cartoes_limites: cartoes (Agregador) ativos por nome.
    select coalesce(jsonb_agg(jsonb_build_object(
               'id', k.id, 'nome', k.nome, 'final', k.final, 'limite_total', round(k.limite, 2), 'utilizado', round(k.usado, 2),
               'disponivel', round(k.limite - k.usado, 2), 'percentual', financeiro.percentual_flask(k.usado, k.limite),
               'status', financeiro.status_consumo_flask(financeiro.percentual_flask(k.usado, k.limite)),
               'categorias_vinculadas', k.qtd)
           order by k.nome, k.id), '[]'::jsonb),
           coalesce(sum(k.limite), 0), coalesce(sum(k.usado), 0)
      into v_cartoes, v_lim_total, v_uso_total
      from (select i.id, i.nome,
                   coalesce(right((select cfg.numero_cartao::text from public.config_agregador cfg
                                    where cfg.item_despesa_id = i.id order by cfg.id limit 1), 4), '') final,
                   coalesce((select sum(coalesce(l.limite_mensal, 0)) from public.cartao_categoria_limite l
                              where l.cartao_id = i.id and l.ativo
                                and financeiro.pertence_ao_perfil(l.perfil_financeiro_id, p_perfil_id)), 0) limite,
                   (select count(*) from public.cartao_categoria_limite l
                     where l.cartao_id = i.id and l.ativo and financeiro.pertence_ao_perfil(l.perfil_financeiro_id, p_perfil_id)) qtd,
                   coalesce((select sum(la.valor) from public.lancamento_agregado la
                              where la.cartao_id = i.id and financeiro.pertence_ao_perfil(la.perfil_financeiro_id, p_perfil_id)
                                and date_trunc('month', la.mes_fatura) = v_inicio), 0) usado
              from public.item_despesa i
             where financeiro.pertence_ao_perfil(i.perfil_financeiro_id, p_perfil_id) and i.tipo = 'Agregador' and i.ativo) k;

    -- _mobilidade_ativa
    select jsonb_build_object(
               'tipo', m.tipo_modalidade,
               'nome', case m.tipo_modalidade when 'VEICULO' then 'Veiculo proprio' when 'TRANSPORTE_APP' then 'Transporte por app'
                                               when 'ASSINATURA' then 'Assinatura' else coalesce(nullif(m.tipo_modalidade, ''), 'Mobilidade') end,
               'custo_mensal', round(coalesce(nullif((select r.valor from public.item_despesa r where r.id = m.recorrencia_id), 0), 0), 2),
               'status', 'ativa',
               'categoria_cartao', (select jsonb_build_object('id', cc.id, 'nome', cc.nome) from public.categoria_cartao cc
                                     where cc.id = m.categoria_cartao_id))
      into v_mobilidade
      from public.mobilidade_cenario_ativo m
     where financeiro.pertence_ao_perfil(m.perfil_financeiro_id, p_perfil_id) and m.status = 'ATIVO'
     order by m.updated_at desc nulls first, m.id desc limit 1;
    v_mobilidade := coalesce(v_mobilidade, jsonb_build_object('tipo', null, 'nome', 'Sem modalidade ativa', 'custo_mensal', 0,
                                                              'status', 'nao_configurada', 'categoria_cartao', null))
                    || jsonb_build_object('alternativas', coalesce((
                           select jsonb_agg(jsonb_build_object('tipo', 'ASSINATURA', 'nome', a.nome,
                                                               'custo_mensal', round(coalesce(a.valor_mensal, 0), 2),
                                                               'status', 'alternativa') order by a.id)
                             from (select * from public.mobilidade_assinatura a
                                    where financeiro.pertence_ao_perfil(a.perfil_financeiro_id, p_perfil_id) and a.status = 'ATIVO'
                                    order by a.id limit 3) a), '[]'::jsonb));

    -- _alertas_operacionais
    if v_venc_hoje > 0 then
        v_alertas := v_alertas || jsonb_build_array(jsonb_build_object('tipo', 'vencimento', 'nivel', 'critico',
                                                                      'mensagem', v_venc_hoje || ' vencimento(s) hoje'));
    end if;
    select count(*) into v_qtd from jsonb_array_elements(v_categorias) x where (x ->> 'percentual')::numeric > 80;
    if v_qtd > 0 then
        v_alertas := v_alertas || jsonb_build_array(jsonb_build_object('tipo', 'limite', 'nivel', 'atencao',
                                                                      'mensagem', v_qtd || ' limite(s) acima de 80%'));
    end if;
    select count(*) into v_qtd from public.despesa_prevista d
     where financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_perfil_id) and d.data_atual_prevista < v_hoje
       and d.status in ('PREVISTA', 'ADIADA');
    if v_qtd > 0 then
        v_alertas := v_alertas || jsonb_build_array(jsonb_build_object('tipo', 'prevista', 'nivel', 'atencao',
                                                                      'mensagem', v_qtd || ' despesa(s) prevista(s) atrasada(s)'));
    end if;
    select count(*) into v_qtd from public.documento_empresarial_metadata dm
     where financeiro.pertence_ao_perfil(dm.perfil_financeiro_id, p_perfil_id) and dm.data_validade < v_hoje;
    if v_qtd > 0 then
        v_alertas := v_alertas || jsonb_build_array(jsonb_build_object('tipo', 'documento_empresarial', 'nivel', 'critico',
                         'mensagem', v_qtd || ' documento(s) empresarial(is) com validade vencida'));
    end if;
    select count(*) into v_qtd from public.documento_empresarial_metadata dm
     where financeiro.pertence_ao_perfil(dm.perfil_financeiro_id, p_perfil_id) and dm.data_validade between v_hoje and v_hoje + 30;
    if v_qtd > 0 then
        v_alertas := v_alertas || jsonb_build_array(jsonb_build_object('tipo', 'documento_empresarial', 'nivel', 'atencao',
                         'mensagem', v_qtd || ' documento(s) empresarial(is) com validade vencendo em 30 dias'));
    end if;

    -- Despesas previstas do mes (D1: so do perfil).
    select coalesce(sum(d.valor_previsto), 0), count(*) filter (where d.status in ('PREVISTA', 'ADIADA')),
           count(*) filter (where d.status = 'CONFIRMADA')
      into v_prev_mes, v_prev_pend, v_prev_conf
      from public.despesa_prevista d
     where financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_perfil_id)
       and d.data_atual_prevista between v_inicio and v_fim;

    v_percentual := financeiro.percentual_flask(v_uso_total, v_lim_total);
    return jsonb_build_object(
        'periodo', jsonb_build_object('mes_referencia', to_char(v_inicio, 'YYYY-MM'), 'inicio', v_inicio, 'fim', v_fim,
                                      'rotulo', to_char(v_inicio, 'MM/YYYY')),
        'kpis', jsonb_build_object(
            'saldo_consolidado', jsonb_build_object('valor', round(v_saldo, 2), 'subtitulo', 'Disponivel em contas', 'tendencia', null),
            'fluxo_projetado_30_dias', jsonb_build_object('valor', v_fluxo -> 'resumo' -> 'saldo_final_projetado',
                                                          'subtitulo', 'Saldo projetado', 'tendencia', null),
            'faturas_em_aberto', jsonb_build_object('valor', round(v_fat_total, 2), 'quantidade_cartoes', v_fat_qtd,
                                                    'subtitulo', v_fat_qtd || ' cartao(s)'),
            'recorrencias_ativas', jsonb_build_object('quantidade', v_rec_qtd, 'valor_mensal', round(v_rec_total, 2),
                                                      'subtitulo', 'fixas e variaveis')),
        'operacional', jsonb_build_object(
            'despesas_previstas_mes', jsonb_build_object('valor', round(v_prev_mes, 2), 'pendentes', v_prev_pend,
                                                         'confirmadas', v_prev_conf,
                                                         'percentual_orcamento', case when v_receitas > 0
                                                             then financeiro.percentual_flask(v_prev_mes, v_receitas) else 0 end),
            'contas_a_vencer_7_dias', jsonb_build_object('valor', round(v_venc_total, 2), 'quantidade', jsonb_array_length(v_venc)),
            'alertas_operacionais', jsonb_build_object('quantidade', jsonb_array_length(v_alertas), 'itens', v_alertas),
            'modalidade_mobilidade_ativa', v_mobilidade),
        'fluxo_caixa', v_fluxo,
        'categorias_cartao', v_categorias,
        'proximos_vencimentos', v_venc,
        'cartoes_limites', jsonb_build_object('itens', v_cartoes, 'limite_total', round(v_lim_total, 2),
                                              'utilizado_total', round(v_uso_total, 2),
                                              'disponivel_total', round(v_lim_total - v_uso_total, 2),
                                              'percentual_total', v_percentual, 'status', financeiro.status_consumo_flask(v_percentual)),
        'mobilidade', v_mobilidade,
        'acoes_rapidas', jsonb_build_array(
            jsonb_build_object('label', 'Confirmar despesas previstas', 'url', '/despesas-previstas'),
            jsonb_build_object('label', 'Importar fatura', 'url', '/importar-cartao'),
            jsonb_build_object('label', 'Gerenciar categorias do cartao', 'url', '/categorias'),
            jsonb_build_object('label', 'Revisar recorrencias', 'url', '/recorrencias'),
            jsonb_build_object('label', 'Gerenciar mobilidade', 'url', '/veiculos')),
        'alertas', v_alertas);
end
$$;

-- analisar_importacao_cartao: texto de 20261107090000.
create or replace function financeiro.analisar_importacao_cartao(p_perfil_id integer, p_cartao_id integer, p_competencia date,
                                                      p_linhas jsonb)
    returns jsonb
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_cartao    public.item_despesa;
    v_comp      date := date_trunc('month', p_competencia::timestamp)::date;
    v_l         jsonb;
    v_idx       bigint;
    v_saida     jsonb := '[]'::jsonb;
    v_msgs      jsonb;
    v_status    text;
    v_ignorar   boolean;
    v_data      date;
    v_valor     numeric;
    v_parc      integer;
    v_total     integer;
    v_norm      text;
    v_chave     text;
    v_chaves    text[] := '{}';
    v_usados    integer[] := '{}';
    v_dup       text;
    v_cat       integer;
    v_sug       jsonb;
    v_cc        integer;
    v_cc_res    integer;
    v_vinc      boolean;
    v_cc_origem text;
    v_class     text;
    v_conc      jsonb;
    v_conc_id   integer;
    v_manter    boolean;
    v_rec       integer;
    v_tipo      text;
    v_cat_origem text;
    v_bruto     numeric;
    v_credito   text;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    v_cartao := financeiro.cartao_do_perfil(p_perfil_id, p_cartao_id, true);
    if p_competencia is null then
        raise exception 'competencia obrigatoria' using errcode = '22023';
    end if;
    if p_linhas is null or jsonb_typeof(p_linhas) <> 'array' then
        raise exception 'Linhas da importacao invalidas' using errcode = '22023';
    end if;
    if jsonb_array_length(p_linhas) > 2000 then
        raise exception 'Arquivo com mais de 2000 linhas: divida a importacao' using errcode = '22023';
    end if;

    for v_l, v_idx in select e, o from jsonb_array_elements(p_linhas) with ordinality as x(e, o) loop
        if jsonb_typeof(v_l) <> 'object' then
            raise exception 'Linha % invalida', v_idx using errcode = '22023';
        end if;
        v_msgs := '[]'::jsonb;
        v_status := 'valido';
        v_ignorar := coalesce((v_l ->> 'ignorar')::boolean, false);
        v_dup := null;
        v_rec := null;
        v_conc := null;
        v_conc_id := null;
        v_manter := coalesce((v_l ->> 'manter_conciliada')::boolean, false);
        v_tipo := coalesce(nullif(v_l ->> 'tipo_movimento', ''), 'debito');
        begin
            v_data := nullif(v_l ->> 'data_compra', '')::date;
        exception when others then
            v_data := null;
        end;
        begin
            v_bruto := (v_l ->> 'valor')::numeric;
        exception when others then
            v_bruto := null;
        end;
        v_valor := round(abs(v_bruto), 2);
        -- Valor negativo nunca vira compra (o sinal nao e descartado): e credito, qualquer que seja o tipo informado.
        if v_bruto < 0 then
            v_tipo := 'credito';
        end if;
        -- Credito na fatura nao e despesa negativa: pagamento da fatura, estorno de compra e ajuste tem efeitos
        -- diferentes e nenhum entra como compra nem reduz a fatura por aqui (como o Flask, que nao importa credito).
        v_credito := case when v_tipo <> 'credito' then null
            when lower(coalesce(v_l ->> 'descricao_original', '')) ~ '(pagamento|pgto|pag[ .]?fatura|obrigado pelo pag)' then 'pagamento_fatura'
            when lower(coalesce(v_l ->> 'descricao_original', '')) ~ '(estorno|estornad|devolu|reembolso|cancelamento|chargeback)' then 'estorno'
            else 'credito_ajuste' end;
        begin
            v_parc := coalesce(nullif(v_l ->> 'parcela_atual', '')::integer, 1);
            v_total := coalesce(nullif(v_l ->> 'total_parcelas', '')::integer, 1);
        exception when others then
            v_parc := 0;
            v_total := 0;
        end;
        v_norm := btrim(coalesce(nullif(v_l ->> 'descricao_normalizada', ''), v_l ->> 'descricao_original', ''));

        -- Validacao (ImportacaoCartaoUnificadoService.validar_linhas)
        if v_tipo = 'credito' then
            v_status := 'ignorado';
            v_ignorar := true;
            v_msgs := v_msgs || case v_credito
                when 'pagamento_fatura' then '"Pagamento da fatura: nao e compra nem desconto; o pagamento e registrado em Despesas (pagar fatura)."'::jsonb
                when 'estorno' then '"Estorno de compra: nao importado; a compra original continua na fatura. Se ela deve sair, corrija pela propria compra."'::jsonb
                else '"Credito ou ajuste da administradora: nao importado como despesa."'::jsonb end;
        elsif v_valor is null or v_valor = 0 then
            v_status := 'ignorado';
            v_ignorar := true;
            v_msgs := v_msgs || '"Valor ausente ou zero."'::jsonb;
        else
            if v_data is null then
                v_status := 'revisar';
                v_msgs := v_msgs || '"Data de compra ausente."'::jsonb;
            end if;
            if v_norm = '' then
                v_status := 'revisar';
                v_msgs := v_msgs || '"Descricao ausente."'::jsonb;
            end if;
            if v_parc < 1 or v_total < 1 or v_parc > v_total or v_total > 60 then
                v_status := 'revisar';
                v_msgs := v_msgs || to_jsonb(format('Parcela fora do intervalo: %s/%s', v_parc, v_total));
            end if;
            if v_valor >= 100000000 then
                v_status := 'revisar';
                v_msgs := v_msgs || '"Valor acima do permitido."'::jsonb;
            end if;
        end if;

        -- Categoria de Despesa: a do usuario prevalece; senao, sugestao (palavra-chave, historico, fallback do cartao)
        v_sug := null;
        v_cat := null;
        v_cat_origem := null;
        if v_tipo <> 'credito' then
            if nullif(v_l ->> 'categoria_id', '') is not null then
                begin
                    v_cat := (v_l ->> 'categoria_id')::integer;
                exception when others then
                    v_cat := null;
                end;
                if v_cat is null or not exists (select 1 from public.categoria c where c.id = v_cat and coalesce(c.ativo, true)) then
                    v_cat := null;
                    v_msgs := v_msgs || '"Categoria da despesa inexistente ou inativa."'::jsonb;
                else
                    v_cat_origem := coalesce(nullif(v_l ->> 'categoria_origem', ''), 'manual');
                end if;
            else
                v_sug := financeiro.sugestao_categoria_importacao(p_perfil_id, v_l ->> 'descricao_classificacao', v_norm,
                                                                  v_cartao.categoria_id);
                v_cat := (v_sug ->> 'categoria_id')::integer;
                v_cat_origem := v_sug ->> 'origem';
                if v_sug ->> 'aviso' is not null then
                    v_msgs := v_msgs || to_jsonb(v_sug ->> 'aviso');
                end if;
            end if;
            if v_cat is null and v_status = 'valido' then
                v_status := 'revisar';
                v_msgs := v_msgs || '"Informe a categoria da despesa."'::jsonb;
            end if;
        end if;

        -- Duplicidade (chave de negocio do Flask) no lote e no banco; depois, conciliacao com compra ja lancada.
        v_chave := null;
        if v_status <> 'ignorado' and v_data is not null and v_norm <> '' and v_valor is not null then
            v_chave := concat_ws('|', p_cartao_id, v_comp, v_data, v_valor, lower(v_norm), v_parc, v_total);
            if v_chave = any(v_chaves) then
                v_dup := 'lote';
            elsif exists (select 1 from public.lancamento_agregado l
                           where l.cartao_id = p_cartao_id and financeiro.pertence_ao_perfil(l.perfil_financeiro_id, p_perfil_id)
                             and coalesce(l.mes_fatura_original, l.mes_fatura) = v_comp
                             and l.data_compra = v_data and l.valor = v_valor
                             and l.numero_parcela = v_parc and l.total_parcelas = v_total
                             and lower(coalesce(l.descricao_original_normalizada, l.descricao)) = lower(v_norm)) then
                v_dup := 'banco';
            end if;
            if v_dup is not null then
                v_status := 'duplicado';
                v_ignorar := true;
                v_msgs := v_msgs || '"Possivel duplicidade detectada."'::jsonb;
            else
                v_chaves := v_chaves || v_chave;
                -- Compra ja lancada (manual, por recorrencia ou importacao com outra descricao): mesmo cartao,
                -- competencia, valor e parcela, data a ate 5 dias (ou gerada por recorrencia). Cada lancamento
                -- concilia uma linha so.
                select l.id, jsonb_build_object('lancamento_id', l.id,
                                                'descricao', coalesce(nullif(l.descricao_exibida, ''), l.descricao),
                                                'data_compra', l.data_compra, 'valor', l.valor, 'categoria_id', l.categoria_id,
                                                'recorrente', coalesce(l.is_recorrente, false), 'mantida', v_manter)
                  into v_conc_id, v_conc
                  from public.lancamento_agregado l
                 where l.cartao_id = p_cartao_id and financeiro.pertence_ao_perfil(l.perfil_financeiro_id, p_perfil_id)
                   and coalesce(l.mes_fatura_original, l.mes_fatura) = v_comp and l.valor = v_valor
                   and coalesce(l.numero_parcela, 1) = v_parc and coalesce(l.total_parcelas, 1) = v_total
                   and (abs(l.data_compra - v_data) <= 5 or coalesce(l.is_recorrente, false))
                   and not l.id = any(v_usados)
                 order by abs(l.data_compra - v_data), l.id
                 limit 1;
                if v_conc_id is not null then
                    v_usados := v_usados || v_conc_id;
                    if not v_manter then
                        v_status := 'conciliado';
                        v_ignorar := true;
                    end if;
                    v_msgs := v_msgs || to_jsonb(format('Ja lancada no cartao: %s (%s, R$ %s)%s.', v_conc ->> 'descricao',
                        to_char((v_conc ->> 'data_compra')::date, 'DD/MM/YYYY'), to_char((v_conc ->> 'valor')::numeric, 'FM999999990.00'),
                        case when v_manter then '; mantida pelo usuario como compra diferente' else '; retirada da efetivacao' end));
                end if;
            end if;
        end if;

        -- Compra recorrente do cartao (reconhecer_despesa_fixa do Flask: nome igual, recorrente, no cartao).
        if v_status not in ('ignorado', 'duplicado', 'conciliado') and v_norm <> '' then
            select i.id into v_rec from public.item_despesa i
             where coalesce(i.recorrente, false) and coalesce(i.ativo, true) and i.tipo <> 'Agregador'
               and i.meio_pagamento = 'cartao' and i.cartao_id = p_cartao_id
               and financeiro.pertence_ao_perfil(i.perfil_financeiro_id, p_perfil_id)
               and lower(i.nome) = lower(v_norm)
             order by i.id limit 1;
            if v_rec is not null then
                -- Como vincular_linha_recorrencia do Flask: a recorrencia que ja tem compra nesta competencia (gerada ou
                -- importada antes) nao recebe outra, mesmo com valor diferente; a compra existente fica como esta.
                select l.id, jsonb_build_object('lancamento_id', l.id,
                                                'descricao', coalesce(nullif(l.descricao_exibida, ''), l.descricao),
                                                'data_compra', l.data_compra, 'valor', l.valor, 'categoria_id', l.categoria_id,
                                                'recorrente', true, 'mantida', false)
                  into v_conc_id, v_conc
                  from public.lancamento_agregado l
                 where l.item_despesa_id = v_rec and l.cartao_id = p_cartao_id
                   and coalesce(l.mes_fatura_original, l.mes_fatura) = v_comp
                 order by l.id limit 1;
                if v_conc_id is not null then
                    v_status := 'conciliado';
                    v_ignorar := true;
                    v_msgs := v_msgs || to_jsonb(format('Recorrencia ja lancada nesta fatura: %s (R$ %s); a compra existente fica como esta%s.',
                        v_conc ->> 'descricao', to_char((v_conc ->> 'valor')::numeric, 'FM999999990.00'),
                        case when (v_conc ->> 'valor')::numeric <> v_valor
                             then format(' (no arquivo, R$ %s: para corrigir, edite a compra)', to_char(v_valor, 'FM999999990.00'))
                             else '' end));
                    v_rec := null;
                else
                    v_msgs := v_msgs || '"Reconhecida como compra recorrente do cartao: o gerador nao a lanca de novo nesta competencia."'::jsonb;
                end if;
            end if;
        end if;

        -- Categoria do Cartao (resolver_categoria_cartao_para_lancamento)
        v_cc := null;
        v_cc_res := null;
        v_vinc := false;
        v_cc_origem := null;
        if v_cat is not null and v_tipo <> 'credito' then
            v_cc := financeiro.resolver_categoria_cartao(p_perfil_id, p_cartao_id, v_cat);
            if v_cc is not null then
                v_vinc := true;
                v_cc_origem := 'mapa_categoria_despesa';
            else
                select v.categoria_cartao_id into v_cc_res
                  from public.categoria_cartao_despesa v join public.categoria_cartao cc on cc.id = v.categoria_cartao_id
                 where v.categoria_id = v_cat and v.ativo and cc.ativo
                   and financeiro.pertence_ao_perfil(v.perfil_financeiro_id, p_perfil_id)
                 order by v.id limit 1;
                if v_cc_res is not null then
                    v_cc_origem := 'nao_vinculada_ao_cartao';
                    v_msgs := v_msgs || '"Esta Categoria do Cartao ainda nao esta vinculada ao cartao selecionado."'::jsonb;
                else
                    v_cc_origem := 'nao_configurada';
                    v_msgs := v_msgs || '"Categoria de despesa sem Categoria do Cartao configurada."'::jsonb;
                end if;
            end if;
        end if;

        v_class := case
            when v_status = 'duplicado' then 'duplicada'
            when v_status = 'conciliado' then 'conciliada'
            when v_ignorar or v_status = 'ignorado' then 'ignorada'
            when v_cat_origem = 'ambigua' then 'ambigua'
            when v_cat is null then 'categoria_despesa_pendente'
            when v_cc_origem = 'nao_vinculada_ao_cartao' then 'categoria_cartao_nao_vinculada'
            when v_cc is null then 'categoria_cartao_pendente'
            else 'classificada' end;
        if v_class = 'classificada' then
            v_msgs := v_msgs || '"Linha pronta para importacao."'::jsonb;
        end if;

        v_saida := v_saida || jsonb_build_object(
            'linha_id', coalesce(v_l ->> 'linha_id', 'linha-' || v_idx), 'tipo_credito', v_credito, 'linha_origem', coalesce((v_l ->> 'linha_origem')::integer, v_idx::integer),
            'status', v_status, 'ignorar', v_ignorar, 'tipo_movimento', v_tipo,
            'data_compra', v_data, 'valor', v_valor,
            'descricao_original', v_l ->> 'descricao_original', 'descricao_normalizada', v_norm,
            'descricao_exibida', coalesce(nullif(btrim(v_l ->> 'descricao_exibida'), ''), v_norm),
            'parcela_atual', v_parc, 'numero_parcela', v_parc, 'total_parcelas', v_total, 'parcela', v_parc || '/' || v_total,
            'categoria_id', v_cat, 'categoria_despesa_id', v_cat,
            'categoria_nome', (select c.nome from public.categoria c where c.id = v_cat),
            'categoria_origem', v_cat_origem, 'categoria_sugerida_origem', coalesce(v_sug ->> 'origem', v_cat_origem),
            'confianca_categoria', coalesce(v_sug ->> 'confianca', case when v_cat is not null then 'manual' else 'baixa' end),
            'palavras_chave_encontradas', coalesce(v_sug -> 'palavras_chave_encontradas', '[]'::jsonb),
            'categorias_candidatas', coalesce(v_sug -> 'categorias_candidatas', '[]'::jsonb),
            'categoria_cartao_id', v_cc, 'categoria_cartao_resolvida_id', v_cc_res,
            'categoria_cartao_nome', (select cc.nome from public.categoria_cartao cc where cc.id = coalesce(v_cc, v_cc_res)),
            'categoria_cartao_origem', v_cc_origem, 'categoria_cartao_vinculada_ao_cartao', v_vinc,
            'status_classificacao', v_class, 'duplicidade', v_dup, 'duplicada', v_status = 'duplicado',
            'ignorada', v_ignorar,
            'conciliacao', v_conc,
            'recorrencia_id', v_rec,
            'gerar_parcelas_futuras', coalesce((v_l ->> 'gerar_parcelas_futuras')::boolean, false),
            'origem_importacao', coalesce(nullif(v_l ->> 'origem_importacao', ''), 'csv'),
            'hash_deduplicacao', v_chave,
            'mensagens', v_msgs, 'avisos', v_msgs);
    end loop;

    return jsonb_build_object(
        'cartao_id', p_cartao_id, 'competencia', to_char(v_comp, 'YYYY-MM'),
        'situacao_fatura', financeiro.situacao_fatura(financeiro.fatura_do_mes(p_cartao_id, v_comp)),
        'linhas', v_saida,
        'validacoes', (select jsonb_build_object(
            'total_linhas', count(*),
            'validas', count(*) filter (where l ->> 'status' = 'valido'),
            'revisar', count(*) filter (where l ->> 'status' = 'revisar'),
            'duplicadas', count(*) filter (where l ->> 'status' = 'duplicado'),
            'conciliadas', count(*) filter (where jsonb_typeof(l -> 'conciliacao') = 'object'),
            'sem_categoria_cartao', count(*) filter (where l ->> 'tipo_movimento' = 'debito'
                                                       and l ->> 'status' not in ('duplicado', 'ignorado', 'conciliado')
                                                       and l ->> 'categoria_cartao_id' is null),
            'total_importavel', coalesce(sum((l ->> 'valor')::numeric) filter (where l ->> 'tipo_movimento' = 'debito'
                                                       and not (l ->> 'ignorar')::boolean), 0),
            'creditos', count(*) filter (where l ->> 'tipo_movimento' = 'credito'),
            'total_creditos', coalesce(sum((l ->> 'valor')::numeric) filter (where l ->> 'tipo_movimento' = 'credito'), 0),
            'ignorados', count(*) filter (where l ->> 'status' = 'ignorado'))
            from jsonb_array_elements(v_saida) l));
end
$$;

-- importar_fatura_cartao: texto de 20261124090000.
create or replace function financeiro.importar_fatura_cartao(p_perfil_id integer, p_cartao_id integer, p_competencia date,
                                                  p_linhas jsonb, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_anterior  financeiro.operacao_cartao;
    v_comp      date := date_trunc('month', p_competencia::timestamp)::date;
    v_analise   jsonb;
    v_l         jsonb;
    v_pendentes text[] := '{}';
    v_a_gravar  jsonb := '[]'::jsonb;
    v_ids       integer[] := '{}';
    v_meses     date[] := '{}';
    v_n         integer;
    v_inicio    integer;
    v_alvo      date;
    v_orig      date;
    v_fat       integer;
    v_passos    integer;
    v_ant       date;
    v_compra    text;
    v_id        integer;
    v_ns        constant uuid := '7f3a1b2c-4d5e-6f7a-8b9c-0d1e2f3a4b5c';  -- mesma identidade do gerador (namespace do Flask)
    v_res       jsonb;
    v_dup       integer;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);  -- FIN-ESCRITOR-UNICO-FINAL-1
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
    perform financeiro.cartao_do_perfil(p_perfil_id, p_cartao_id, true);
    perform pg_advisory_xact_lock(20261023, p_perfil_id);  -- mesma trava da geracao e das compras do perfil
    perform 1 from public.item_despesa where id = p_cartao_id for update;  -- cartao antes das faturas

    -- Analise refeita sob a trava: duplicidade e conciliacao valem para o que esta gravado agora.
    v_analise := financeiro.analisar_importacao_cartao(p_perfil_id, p_cartao_id, v_comp, p_linhas);
    for v_l in select e from jsonb_array_elements(v_analise -> 'linhas') e loop
        continue when (v_l ->> 'ignorar')::boolean;
        if v_l ->> 'status' <> 'valido' or v_l ->> 'categoria_id' is null then
            v_pendentes := v_pendentes || format('linha %s (%s): %s', v_l ->> 'linha_origem',
                coalesce(v_l ->> 'descricao_exibida', '-'), coalesce(v_l -> 'mensagens' ->> 0, v_l ->> 'status'));
        else
            v_a_gravar := v_a_gravar || v_l;
        end if;
    end loop;
    if cardinality(v_pendentes) > 0 then
        raise exception 'Importacao nao realizada: % linha(s) precisam de revisao ou devem ser retiradas: %',
            cardinality(v_pendentes), array_to_string(v_pendentes[1:5], '; ')
            using errcode = '22023', hint = 'REVISAR';
    end if;
    if jsonb_array_length(v_a_gravar) = 0 then
        raise exception 'Nenhuma linha para importar' using errcode = '22023';
    end if;

    for v_l in select e from jsonb_array_elements(v_a_gravar) e loop
        v_n := (v_l ->> 'total_parcelas')::integer;
        -- Parcelamento pedido pelo usuario: a parcela do arquivo e as futuras (gerar_apenas_atual_e_futuras do Flask);
        -- sem ele, so a parcela da fatura importada (como o Flask).
        v_inicio := (v_l ->> 'parcela_atual')::integer;
        v_compra := case when (v_l ->> 'recorrencia_id') is not null
            then extensions.uuid_generate_v5(v_ns, format('%s-%s', v_l ->> 'recorrencia_id', to_char(v_comp, 'YYYY-MM-DD')))::text
            else gen_random_uuid()::text end;
        v_ant := null;
        for v_k in v_inicio .. case when (v_l ->> 'gerar_parcelas_futuras')::boolean and v_n > 1 then v_n else v_inicio end loop
            v_orig := (v_comp + make_interval(months => v_k - v_inicio))::date;
            v_alvo := v_orig;
            if v_ant is not null and v_alvo <= v_ant then
                v_alvo := (v_ant + interval '1 month')::date;
            end if;
            v_passos := 0;
            loop  -- fatura paga nao recebe compra: proxima nao paga (como o Flask e o novo aplicativo)
                v_fat := financeiro.fatura_do_mes(p_cartao_id, v_alvo);
                exit when v_fat is null or not financeiro.fatura_esta_paga(v_fat);
                v_alvo := (v_alvo + interval '1 month')::date;
                v_passos := v_passos + 1;
                if v_passos > 24 then
                    raise exception 'Nao ha fatura aberta nos proximos 24 meses' using errcode = '22023';
                end if;
            end loop;
            v_ant := v_alvo;
            v_fat := financeiro.garantir_fatura(p_perfil_id, p_cartao_id, v_alvo);
            perform 1 from public.conta where id = v_fat for update;
            if financeiro.fatura_esta_paga(v_fat) then
                raise exception 'A fatura de % foi paga durante a importacao. Revise e tente de novo.',
                    to_char(v_alvo, 'MM/YYYY') using errcode = 'P0001';
            end if;
            if exists (select 1 from public.conta c where c.id = v_fat and c.status_fatura = 'FECHADA') then
                raise exception 'Importacao nao realizada: a fatura de % esta consolidada e "%" cairia nela. Retire a linha ou importe em outra competencia.',
                    to_char(v_alvo, 'MM/YYYY'), v_l ->> 'descricao_exibida' using errcode = 'P0001', hint = 'CONSOLIDADA';
            end if;
            insert into public.lancamento_agregado (perfil_financeiro_id, cartao_id, item_agregado_id, categoria_cartao_id,
                                                    categoria_id, descricao, descricao_original, descricao_original_normalizada,
                                                    descricao_exibida, valor, data_compra, mes_fatura, numero_parcela,
                                                    total_parcelas, observacoes, is_recorrente, item_despesa_id, compra_id,
                                                    is_importado, origem_importacao, criado_em, mes_fatura_original)
            values (coalesce((select c.perfil_financeiro_id from public.conta c where c.id = v_fat), p_perfil_id),
                    p_cartao_id, null, (v_l ->> 'categoria_cartao_id')::integer, (v_l ->> 'categoria_id')::integer,
                    left(v_l ->> 'descricao_normalizada', 200), v_l ->> 'descricao_original', v_l ->> 'descricao_normalizada',
                    case when v_n > 1 and (v_l ->> 'gerar_parcelas_futuras')::boolean
                         then format('%s (%s/%s)', v_l ->> 'descricao_exibida', v_k, v_n) else v_l ->> 'descricao_exibida' end,
                    (v_l ->> 'valor')::numeric, ((v_l ->> 'data_compra')::date + make_interval(months => v_k - v_inicio))::date,
                    v_alvo, v_k, v_n, '', (v_l ->> 'recorrencia_id') is not null, (v_l ->> 'recorrencia_id')::integer,
                    v_compra, true, left(coalesce(v_l ->> 'origem_importacao', 'csv'), 20), now() at time zone 'utc',
                    nullif(v_orig, v_alvo))
            returning id into v_id;
            v_ids := v_ids || v_id;
            if not v_alvo = any(v_meses) then
                v_meses := v_meses || v_alvo;
            end if;
        end loop;
    end loop;
    for i in 1..cardinality(v_meses) loop
        perform financeiro.recalcular_fatura(p_perfil_id, p_cartao_id, v_meses[i]);
    end loop;

    select count(*) into v_dup from jsonb_array_elements(v_analise -> 'linhas') e
     where e ->> 'status' in ('duplicado', 'conciliado');
    v_res := jsonb_build_object(
        'inseridos', cardinality(v_ids), 'linhas_importadas', jsonb_array_length(v_a_gravar), 'duplicados', v_dup,
        'lancamentos', to_jsonb(v_ids), 'faturas', to_jsonb(v_meses), 'cartao_id', p_cartao_id,
        'competencia', to_char(v_comp, 'YYYY-MM'));
    insert into financeiro.operacao_cartao (chave, user_id, perfil_financeiro_id, operacao, resultado)
    values (p_chave, (select auth.uid()), p_perfil_id, 'importar_fatura', v_res);
    return v_res;
end
$$;

-- compras_da_fatura: texto de 20261207090000.
drop function financeiro.compras_da_fatura(integer, integer, date);

create function financeiro.compras_da_fatura(p_perfil_id integer, p_cartao_id integer, p_mes date)
    returns table (id integer, descricao text, valor numeric, data_compra date, numero_parcela integer,
                   total_parcelas integer, categoria_nome text, recorrente boolean, bloqueio text, pode_editar boolean,
                   categoria_cartao_id integer)
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_pessoal boolean;
    v_gerir   boolean;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    perform financeiro.cartao_do_perfil(p_perfil_id, p_cartao_id, false);
    v_pessoal := exists (select 1 from public.perfil_financeiro p where p.id = p_perfil_id and p.nome = 'Pessoal');
    v_gerir := financeiro.pode_gerir_perfil(p_perfil_id);
    return query
        select l.id, coalesce(nullif(l.descricao_exibida, ''), l.descricao)::text, l.valor, l.data_compra,
               l.numero_parcela, l.total_parcelas, cat.nome::text, coalesce(l.is_recorrente, false),
               financeiro.bloqueio_da_parcela(l.id), v_gerir and financeiro.bloqueio_da_parcela(l.id) is null,
               l.categoria_cartao_id
          from public.lancamento_agregado l
          left join public.categoria cat on cat.id = l.categoria_id
         where l.cartao_id = p_cartao_id and l.mes_fatura = date_trunc('month', p_mes::timestamp)::date
           and (l.perfil_financeiro_id = p_perfil_id or (l.perfil_financeiro_id is null and v_pessoal))
         order by l.data_compra, l.id;
end
$$;

revoke execute on function financeiro.compras_da_fatura(integer, integer, date) from public, anon;
grant execute on function financeiro.compras_da_fatura(integer, integer, date) to authenticated;

drop function financeiro.remover_apelido_recorrencia(integer, bigint);
drop function financeiro.criar_apelido_recorrencia(integer, integer, text);
drop function financeiro.apelidos_da_recorrencia(integer, integer);
drop function financeiro.recorrencia_cartao_do_perfil(integer, integer);
drop function financeiro.reverter_ocorrencia_recorrencia(integer, bigint, uuid);
drop function financeiro.conciliar_ocorrencia_recorrencia(integer, integer, text, integer, text, uuid);
drop function financeiro.realizar_ocorrencia_recorrencia(integer, integer, jsonb, text, jsonb);
drop table financeiro.recorrencia_apelido;
drop table financeiro.ocorrencia_recorrencia_cartao;
drop function financeiro.texto_cobranca(text);
drop function financeiro.natureza_da_compra(integer, boolean, integer, integer);
