-- Reversao da 20261225090000 (FIN-CARTOES-EXECUTADO-01): volta as funcoes ao texto anterior (cartao: o publicado antes
-- dela; dashboard_resumo_tela: o da 20261224090000) e remove previsto_fatura. Nenhum dado muda.

CREATE OR REPLACE FUNCTION financeiro.valor_executado_compra(p_valor numeric, p_situacao text)
 RETURNS numeric
 LANGUAGE sql
 IMMUTABLE
 SET search_path TO ''
AS $function$
    select case when p_situacao in ('PREVISTA', 'NAO_COBRADA') then 0 else coalesce(p_valor, 0) end
$function$;

CREATE OR REPLACE FUNCTION financeiro.executado_fatura(p_fatura_id integer)
 RETURNS numeric
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
    -- FIN-CARTAO-PREVISTO-EXECUTADO-01: previsao de recorrencia ainda sem cobranca (ou nao cobrada) nao e executada
    -- FIN-CARTAO-NUBANK-CREDITOS-01: menos os creditos da fatura (estorno, IOF devolvido, ajuste): o valor a pagar
    select coalesce(sum(financeiro.valor_executado_compra(l.valor, financeiro.situacao_previsao(l.id, financeiro.natureza_da_compra(l.total_parcelas, l.is_recorrente, l.item_despesa_id, l.categoria_cartao_id), l.is_importado, l.cartao_id, l.mes_fatura))), 0)
           - financeiro.creditos_fatura(p_fatura_id)
      from public.conta c
      join public.lancamento_agregado l on l.cartao_id = c.item_despesa_id and l.mes_fatura = c.cartao_competencia
     where c.id = p_fatura_id
       and financeiro.pertence_ao_perfil(l.perfil_financeiro_id, coalesce(c.perfil_financeiro_id,
               (select p.id from public.perfil_financeiro p where p.nome = 'Pessoal' order by p.id limit 1)))
$function$;

CREATE OR REPLACE FUNCTION financeiro.recalcular_fatura(p_perfil_id integer, p_cartao_id integer, p_competencia date)
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    v_id       integer;
    v_pessoal  boolean;
    v_plan     numeric;
    v_exec     numeric;
begin
    v_id := financeiro.fatura_do_mes(p_cartao_id, p_competencia);
    if v_id is null or financeiro.fatura_esta_paga(v_id) then
        return;
    end if;
    v_pessoal := exists (select 1 from public.perfil_financeiro p where p.id = p_perfil_id and p.nome = 'Pessoal');
    v_plan := financeiro.planejado_fatura(p_perfil_id, p_cartao_id, p_competencia);
    -- FIN-CARTAO-PREVISTO-EXECUTADO-01: previsao de recorrencia ainda sem cobranca nao e executada
    select coalesce(sum(financeiro.valor_executado_compra(l.valor, financeiro.situacao_previsao(l.id, financeiro.natureza_da_compra(l.total_parcelas, l.is_recorrente, l.item_despesa_id, l.categoria_cartao_id), l.is_importado, l.cartao_id, l.mes_fatura))), 0)
      into v_exec from public.lancamento_agregado l
     where l.cartao_id = p_cartao_id and l.mes_fatura = p_competencia
       and (l.perfil_financeiro_id = p_perfil_id or (l.perfil_financeiro_id is null and v_pessoal));
    -- FIN-CARTAO-NUBANK-CREDITOS-01: creditos da fatura abatem o executado e o planejado (valor a pagar)
    v_exec := v_exec - financeiro.creditos_fatura(v_id);
    v_plan := v_plan - financeiro.creditos_fatura(v_id);
    update public.conta set valor_planejado = v_plan, valor_executado = v_exec, estouro_orcamento = v_exec > v_plan,
                            valor = v_plan
     where id = v_id;
end
$function$;

CREATE OR REPLACE FUNCTION financeiro.contas_do_mes(p_perfil_id integer, p_mes date)
 RETURNS TABLE(id integer, grupo text, nome text, valor numeric, valor_previsto numeric, valor_executado numeric, data_vencimento date, data_pagamento date, situacao text, status_pagamento text, categoria_nome text, categoria_cor text, cartao_id integer, cartao_nome text, numero_parcela integer, total_parcelas integer, debito_automatico boolean)
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
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
           and c.status_pagamento is distinct from 'Substituida'  -- FIN-MVP-MOB-01: preservada, fora das despesas do mes
           and (
                (coalesce(c.is_fatura_cartao, false) = false and date_trunc('month', c.mes_referencia) = v_mes)
             or (c.is_fatura_cartao = true and date_trunc('month', c.cartao_competencia) = v_mes)
           )
    ),
    gastos as (
        -- gasto do mes por cartao e categoria de cartao, no perfil (mes_fatura = 1o dia, como no Flask)
        -- FIN-CARTAO-PREVISTO-EXECUTADO-01: total = executado (sem previsao pendente); pendente = previsoes aguardando cobranca
        select l.cartao_id, l.categoria_cartao_id, sum(financeiro.valor_executado_compra(l.valor, sit.s)) as total,
               sum(l.valor) filter (where sit.s = 'PREVISTA') as pendente,
               -- FIN-CARTAO-DESPESAS-FIXAS-01: parceladas e fixas nao consomem o limite da Categoria do Cartao
               sum(l.valor) filter (where financeiro.natureza_da_compra(l.total_parcelas, l.is_recorrente, l.item_despesa_id, l.categoria_cartao_id) = 'CATEGORIA') as total_categoria
          from public.lancamento_agregado l
         cross join lateral (select financeiro.situacao_previsao(l.id, financeiro.natureza_da_compra(l.total_parcelas, l.is_recorrente, l.item_despesa_id, l.categoria_cartao_id), l.is_importado, l.cartao_id, l.mes_fatura) as s) sit
         where (l.perfil_financeiro_id = p_perfil_id or (l.perfil_financeiro_id is null and v_pessoal))
           and l.mes_fatura = v_mes
         group by l.cartao_id, l.categoria_cartao_id
    ),
    faturas as (
        select c.id,
               -- FIN-CARTAO-NUBANK-CREDITOS-01: executado das compras menos os creditos da fatura (valor a pagar)
               coalesce((select sum(g.total) from gastos g where g.cartao_id = c.item_despesa_id), 0)
                   - financeiro.creditos_fatura(c.id) as executado,
               coalesce((select sum(g.pendente) from gastos g where g.cartao_id = c.item_despesa_id), 0) as pendente,
               coalesce((select sum(greatest(lim.limite_mensal - coalesce(g.total_categoria, 0), 0))
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
               else f.executado + f.pendente + f.complemento
           end,
           case when c.is_fatura_cartao then f.executado + f.pendente + f.complemento end,
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
$function$;

CREATE OR REPLACE FUNCTION financeiro.faturas_do_mes(p_perfil_id integer, p_mes date)
 RETURNS TABLE(cartao_id integer, cartao_nome text, fatura_id integer, competencia date, data_vencimento date, situacao text, valor_executado numeric, valor_previsto numeric, compras integer, pode_gerir boolean)
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
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
        -- FIN-CARTAO-PREVISTO-EXECUTADO-01: gasto = executado (sem previsao pendente); pendente = previsoes aguardando cobranca
        select l.cartao_id, l.categoria_cartao_id, sum(financeiro.valor_executado_compra(l.valor, sit.s)) as gasto,
               count(*) as qtd, sum(l.valor) filter (where sit.s = 'PREVISTA') as pendente,
               -- FIN-CARTAO-DESPESAS-FIXAS-01: parceladas e fixas nao consomem o limite da Categoria do Cartao
               sum(l.valor) filter (where financeiro.natureza_da_compra(l.total_parcelas, l.is_recorrente, l.item_despesa_id, l.categoria_cartao_id) = 'CATEGORIA') as gasto_categoria
          from public.lancamento_agregado l
         cross join lateral (select financeiro.situacao_previsao(l.id, financeiro.natureza_da_compra(l.total_parcelas, l.is_recorrente, l.item_despesa_id, l.categoria_cartao_id), l.is_importado, l.cartao_id, l.mes_fatura) as s) sit
         where l.mes_fatura = v_mes and (l.perfil_financeiro_id = p_perfil_id or (l.perfil_financeiro_id is null and v_pessoal))
         group by 1, 2
    )
    -- FIN-CARTAO-NUBANK-CREDITOS-01: executado e previsto ja descontam os creditos da fatura
    select c.id, c.nome::text, f.id, v_mes, f.data_vencimento,
           case when f.id is null then 'SEM_FATURA'
                when f.status_pagamento = 'Pago' or f.status_fatura = 'PAGA' then 'PAGA'
                when f.status_fatura = 'FECHADA' then 'FECHADA' else 'ABERTA' end,
           (coalesce((select sum(g.gasto) from gastos g where g.cartao_id = c.id), 0) - financeiro.creditos_fatura(f.id)),
           case when f.status_pagamento = 'Pago' then (coalesce((select sum(g.gasto) from gastos g where g.cartao_id = c.id), 0) - financeiro.creditos_fatura(f.id))
                else (coalesce((select sum(g.gasto) from gastos g where g.cartao_id = c.id), 0) - financeiro.creditos_fatura(f.id))
                     + coalesce((select sum(g.pendente) from gastos g where g.cartao_id = c.id), 0)
                     + coalesce((select sum(greatest(lim.limite_mensal - coalesce(g.gasto_categoria, 0), 0))
                                   from public.cartao_categoria_limite lim
                                   left join gastos g on g.cartao_id = c.id and g.categoria_cartao_id = lim.categoria_cartao_id
                                  where lim.cartao_id = c.id and lim.ativo), 0) end,
           coalesce((select sum(g.qtd) from gastos g where g.cartao_id = c.id), 0)::integer,
           financeiro.pode_gerir_perfil(p_perfil_id)
      from cartoes c
      left join public.conta f on f.id = financeiro.fatura_do_mes(c.id, v_mes)
     order by c.nome;
end
$function$;

CREATE OR REPLACE FUNCTION financeiro.fatura_por_categoria(p_perfil_id integer, p_cartao_id integer, p_mes date)
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    v_mes        date := date_trunc('month', p_mes::timestamp)::date;
    v_grupos     jsonb;
    v_total      numeric;
    v_com        numeric;
    v_sem        numeric;
    v_limite     numeric;
    v_vinculadas numeric;
    v_fixas      numeric;  -- FIN-CARTAO-DESPESAS-FIXAS-01
    v_parceladas numeric;
    v_pendente   numeric;  -- FIN-CARTAO-PREVISTO-EXECUTADO-01
    v_fatura     integer;  -- FIN-CARTAO-NUBANK-CREDITOS-01
    v_creditos   numeric;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    perform financeiro.cartao_do_perfil(p_perfil_id, p_cartao_id, false);
    v_fatura := financeiro.fatura_do_mes(p_cartao_id, v_mes);
    v_creditos := financeiro.creditos_fatura(v_fatura);
    with lanc as (
        -- FIN-CARTAO-PREVISTO-EXECUTADO-01: valor = executado (a previsao pendente nao entra no gasto nem no total da fatura)
        select financeiro.valor_executado_compra(l.valor, sit.s) as valor, l.categoria_cartao_id, nat.n as natureza,
               case when sit.s = 'PREVISTA' then l.valor else 0 end as pendente
          from public.lancamento_agregado l
         cross join lateral (select financeiro.natureza_da_compra(l.total_parcelas, l.is_recorrente, l.item_despesa_id, l.categoria_cartao_id) as n) nat
         cross join lateral (select financeiro.situacao_previsao(l.id, nat.n, l.is_importado, l.cartao_id, l.mes_fatura) as s) sit
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
               coalesce((select sum(x.valor) from lanc x where x.natureza = 'CATEGORIA' and x.categoria_cartao_id = lim.categoria_cartao_id), 0) as gasto,
               (select count(*) from lanc x where x.natureza = 'CATEGORIA' and x.categoria_cartao_id = lim.categoria_cartao_id) as qtd,
               'categoria_cartao' as tipo
          from limites lim
        union all
        -- 2. categorias com lancamento mas sem limite ativo neste cartao
        select 2, min(cc.id), x.categoria_cartao_id, 0, sum(x.valor), count(*), 'categoria_sem_limite'
          from lanc x join public.categoria_cartao cc on cc.id = x.categoria_cartao_id
         where x.categoria_cartao_id is not null and x.natureza = 'CATEGORIA'
           and x.categoria_cartao_id not in (select l2.categoria_cartao_id from limites l2)
         group by x.categoria_cartao_id
        union all
        -- 3 e 4. FIN-CARTAO-DESPESAS-FIXAS-01: obrigacoes ja contratadas, fora das Categorias do Cartao (nao consomem limite)
        select 3, 0, null, null, sum(x.valor), count(*), 'compras_parceladas'
          from lanc x where x.natureza = 'PARCELADA' having count(*) > 0
        union all
        select 4, 0, null, null, sum(x.valor), count(*), 'despesas_fixas'
          from lanc x where x.natureza = 'FIXA' having count(*) > 0
        union all
        -- 5. sem Categoria do Cartao (o que nao e parcelada nem fixa)
        select 5, 0, null, null, sum(x.valor), count(*), 'sem_categoria'
          from lanc x where x.natureza = 'OUTROS' having count(*) > 0
        union all
        -- 6. FIN-CARTAO-NUBANK-CREDITOS-01: creditos da fatura (estorno, IOF devolvido, ajuste), negativos: abatem o valor a pagar
        select 6, 0, null, null, -sum(cf.valor), count(*), 'creditos'
          from financeiro.credito_fatura cf where cf.fatura_id = v_fatura having count(*) > 0
    )
    select coalesce(jsonb_agg(jsonb_build_object(
               -- os grupos de parceladas e fixas levam o proprio filtro de "Ver lancamentos" (tela de Cartoes)
               'categoria_cartao_id', case when g.tipo in ('compras_parceladas', 'despesas_fixas', 'creditos') then to_jsonb(g.tipo)
                                           else to_jsonb(g.categoria_cartao_id) end,
               'categoria_cartao_nome', case g.tipo when 'sem_categoria' then 'Sem Categoria do Cartao'
                                                    when 'compras_parceladas' then 'Compras parceladas'
                                                    when 'despesas_fixas' then 'Despesas fixas'
                                                    when 'creditos' then 'Creditos e ajustes'
                                                    else coalesce(cc.nome, 'Categoria do Cartao') end,
               'natureza', case g.tipo when 'compras_parceladas' then 'PARCELADA' when 'despesas_fixas' then 'FIXA'
                                       when 'creditos' then 'CREDITO'
                                       when 'sem_categoria' then 'OUTROS' else 'CATEGORIA' end,
               'previsto_pendente', case when g.tipo = 'despesas_fixas' then (select coalesce(sum(x.pendente), 0) from lanc x) end,
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
                              when g.tipo in ('compras_parceladas', 'despesas_fixas') then 'Contratada'
                              when g.tipo = 'creditos' then 'Abatido'
                              else 'Revisar' end,
               'quantidade_lancamentos', g.qtd,
               'vinculada_ao_cartao', g.tipo = 'categoria_cartao',
               'sem_categoria', g.tipo = 'sem_categoria',
               'categoria_sem_limite', g.tipo = 'categoria_sem_limite',
               'avisos', case g.tipo when 'sem_categoria' then '["Lancamentos sem Categoria do Cartao devem ser revisados."]'::jsonb
                                     when 'categoria_sem_limite' then '["Categoria sem limite neste cartao."]'::jsonb
                                     when 'compras_parceladas' then '["Parcelas ja contratadas: nao consomem limite de Categoria do Cartao."]'::jsonb
                                     when 'creditos' then '["Estornos, IOF devolvido e ajustes da administradora: abatem o valor a pagar; a compra original continua registrada."]'::jsonb
                                     when 'despesas_fixas' then case when (select coalesce(sum(x.pendente), 0) from lanc x) > 0
                                         then jsonb_build_array('R$ ' || to_char((select sum(x.pendente) from lanc x), 'FM999999990.00')
                                                                || ' previstos aguardando cobranca: fora do executado e do valor a pagar.')
                                         else '["Recorrencias do cartao: nao consomem limite de Categoria do Cartao."]'::jsonb end
                                     else '[]'::jsonb end,
               'tipo_grupo', g.tipo) order by g.ordem, g.ordem2), '[]'::jsonb)
      into v_grupos
      from grupos g left join public.categoria_cartao cc on cc.id = g.categoria_cartao_id;

    select coalesce(sum(ex.v), 0),
           coalesce(sum(ex.v) filter (where nat.n = 'CATEGORIA'), 0),
           coalesce(sum(ex.v) filter (where nat.n = 'OUTROS'), 0),
           coalesce(sum(ex.v) filter (where nat.n = 'FIXA'), 0),
           coalesce(sum(ex.v) filter (where nat.n = 'PARCELADA'), 0),
           coalesce(sum(ex.v) filter (where nat.n = 'CATEGORIA' and l.categoria_cartao_id in (
               select lim.categoria_cartao_id from public.cartao_categoria_limite lim
                where lim.cartao_id = p_cartao_id and lim.perfil_financeiro_id = p_perfil_id and lim.ativo)), 0)
           , coalesce(sum(l.valor) filter (where sit.s = 'PREVISTA'), 0)
      into v_total, v_com, v_sem, v_fixas, v_parceladas, v_vinculadas, v_pendente
      from public.lancamento_agregado l
     cross join lateral (select financeiro.natureza_da_compra(l.total_parcelas, l.is_recorrente, l.item_despesa_id, l.categoria_cartao_id) as n) nat  -- FIN-CARTAO-DESPESAS-FIXAS-01
     cross join lateral (select financeiro.situacao_previsao(l.id, nat.n, l.is_importado, l.cartao_id, l.mes_fatura) as s) sit  -- FIN-CARTAO-PREVISTO-EXECUTADO-01
     cross join lateral (select financeiro.valor_executado_compra(l.valor, sit.s) as v) ex
     where l.cartao_id = p_cartao_id and l.mes_fatura = v_mes
       and financeiro.pertence_ao_perfil(l.perfil_financeiro_id, p_perfil_id);
    select coalesce(sum(lim.limite_mensal), 0) into v_limite from public.cartao_categoria_limite lim
     where lim.cartao_id = p_cartao_id and lim.perfil_financeiro_id = p_perfil_id and lim.ativo;

    return jsonb_build_object(
        'cartao_id', p_cartao_id,
        'mes_referencia', to_char(v_mes, 'YYYY-MM'),
        -- FIN-CARTAO-NUBANK-CREDITOS-01: total da fatura = valor a pagar (compras executadas - creditos)
        'total_fatura', v_total - v_creditos,
        'total_compras', v_total,
        'total_creditos', v_creditos,
        -- FIN-CARTOES-MULTIPLOS-01: a fatura (unica do contrato) por cartao vinculado; o que nao tem cartao identificado, a parte
        'por_cartao', financeiro.fatura_por_cartao(p_perfil_id, p_cartao_id, v_mes),
        'total_com_categoria', v_com,
        'total_sem_categoria_cartao', v_sem,
        'total_despesas_fixas', v_fixas,
        'total_compras_parceladas', v_parceladas,
        'total_previsto_pendente', v_pendente,
        'limite_total', v_limite,
        'disponivel_total', v_limite - v_vinculadas,
        'percentual_total', case when v_limite > 0 then round(v_vinculadas / v_limite * 100, 2) else 0 end,
        'status_total', financeiro.status_consumo(v_vinculadas, v_limite),
        'situacao_fatura', financeiro.situacao_fatura(financeiro.fatura_do_mes(p_cartao_id, v_mes)),
        'categorias', v_grupos);
end
$function$;

CREATE OR REPLACE FUNCTION financeiro.previsoes_no_pagamento_da_fatura()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    v_fatura public.conta;
begin
    if tg_op = 'INSERT' then
        if new.origem <> 'NOVO_APP' or new.estorno_movimento_id is not null then
            return null;
        end if;
        select * into v_fatura from public.conta where id = new.fatura_id;
        if not found or not coalesce(v_fatura.is_fatura_cartao, false) then
            return null;
        end if;
        insert into financeiro.ocorrencia_recorrencia_cartao (perfil_financeiro_id, lancamento_id, item_despesa_id, cartao_id,
                                                              competencia, valor_previsto, valor_executado, descricao_cobranca,
                                                              origem, lancamento_antes, pagamento_id, user_id)
        select new.perfil_financeiro_id, l.id, l.item_despesa_id, l.cartao_id, coalesce(l.mes_fatura_original, l.mes_fatura),
               l.valor, 0, null, 'NAO_COBRADA', to_jsonb(l), new.id, new.user_id
          from public.lancamento_agregado l
         where l.cartao_id = v_fatura.item_despesa_id and l.mes_fatura = v_fatura.cartao_competencia
           and financeiro.pertence_ao_perfil(l.perfil_financeiro_id, coalesce(v_fatura.perfil_financeiro_id,
                   (select p.id from public.perfil_financeiro p where p.nome = 'Pessoal' order by p.id limit 1)))
           and financeiro.natureza_da_compra(l.total_parcelas, l.is_recorrente, l.item_despesa_id, l.categoria_cartao_id) = 'FIXA'
           and not coalesce(l.is_importado, false)
           and not exists (select 1 from financeiro.ocorrencia_recorrencia_cartao o
                            where o.lancamento_id = l.id and o.revertida_em is null)
         order by l.id;
    elsif old.estorno_movimento_id is null and new.estorno_movimento_id is not null then
        update financeiro.ocorrencia_recorrencia_cartao
           set revertida_em = now(), revertida_por = new.estorno_user_id
         where pagamento_id = new.id and origem = 'NAO_COBRADA' and revertida_em is null;
    end if;
    return null;
end
$function$;

CREATE OR REPLACE FUNCTION financeiro.dados_pagamento_fatura(p_perfil_id integer, p_fatura_id integer)
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    v_fatura    public.conta;
    v_paga      boolean;
    v_executado numeric;
    v_gerir     boolean;
    v_novo      boolean;
    v_vigente   integer;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    select * into v_fatura from public.conta c where c.id = p_fatura_id and c.is_fatura_cartao;
    if not found or not financeiro.pertence_ao_perfil(v_fatura.perfil_financeiro_id, p_perfil_id) then
        raise exception 'Fatura nao encontrada neste perfil' using errcode = '42501';
    end if;
    v_paga := financeiro.fatura_esta_paga(v_fatura.id);
    v_executado := case when v_paga then coalesce(v_fatura.valor_executado, 0) else financeiro.executado_fatura(v_fatura.id) end;
    v_gerir := financeiro.pode_gerir_perfil(p_perfil_id);
    v_novo := financeiro.gerador_do_perfil(p_perfil_id) = 'NOVO';
    v_vigente := financeiro.pagamento_vigente(v_fatura.id);
    return jsonb_build_object(
        'fatura', jsonb_build_object(
            'id', v_fatura.id, 'cartao_id', v_fatura.item_despesa_id,
            'cartao_nome', (select i.nome from public.item_despesa i where i.id = v_fatura.item_despesa_id),
            'competencia', v_fatura.cartao_competencia, 'data_vencimento', v_fatura.data_vencimento,
            'valor_executado', v_executado, 'paga', v_paga, 'status_fatura', v_fatura.status_fatura),
        'contas', coalesce((select jsonb_agg(jsonb_build_object('id', cb.id, 'nome', cb.nome, 'instituicao', cb.instituicao,
                                                                'saldo', financeiro.saldo_da_conta(cb.id)) order by cb.nome, cb.id)
                              from public.conta_bancaria cb
                             where cb.status = 'ATIVO' and financeiro.pertence_ao_perfil(cb.perfil_financeiro_id, p_perfil_id)),
                           '[]'::jsonb),
        'pagamentos', coalesce((
            select jsonb_agg(jsonb_build_object(
                       'movimento_id', m.id, 'data_pagamento', m.data_movimento, 'valor_pago', m.valor,
                       'conta_bancaria_id', m.conta_bancaria_id, 'conta_nome', cb.nome,
                       'valor_executado', p.valor_executado, 'tipo_ajuste', p.tipo_ajuste,
                       'justificativa', p.justificativa, 'origem', coalesce(p.origem, 'FLASK'),
                       'vigente', coalesce(m.id = v_vigente, false) and v_paga,
                       'estorno', case when e.id is null then null else jsonb_build_object(
                           'movimento_id', e.id, 'data', e.data_movimento, 'valor', e.valor,
                           'motivo', p.estorno_motivo) end) order by m.id)
              from public.movimento_financeiro m
              left join public.conta_bancaria cb on cb.id = m.conta_bancaria_id
              left join financeiro.pagamento_fatura p on p.movimento_id = m.id
              left join lateral (select x.id, x.data_movimento, x.valor from public.movimento_financeiro x
                                  where x.movimento_original_id = m.id and x.tipo = 'CREDITO'
                                  order by x.id limit 1) e on true
             where (m.conta_id = v_fatura.id or m.fatura_id = v_fatura.id) and m.tipo = 'DEBITO' and m.origem = 'FATURA'),
            '[]'::jsonb),
        'sistema', case when v_novo then 'NOVO' else 'FLASK' end,
        'pode_pagar', v_gerir and v_novo and not v_paga and v_executado > 0,
        'pode_estornar', v_gerir and v_novo and v_paga and v_vigente is not null);
end
$function$;

CREATE OR REPLACE FUNCTION financeiro.dashboard_resumo_tela(p_perfil_id integer, p_mes_referencia text)
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
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
    -- FIN-RECEITAS-SALDO-01: previstas e recebidas pela regra unica de receitas_totais_do_mes (a mesma da tela de
    -- Despesas): estorno nao conta; previsao parcialmente recebida conta o previsto; recebido acima do previsto conta o
    -- recebido; recebimento sem previsao conta uma vez.
    select (t ->> 'previstas')::numeric, (t ->> 'recebidas')::numeric
      into v_receitas, v_recebidas
      from financeiro.receitas_totais_do_mes(p_perfil_id, v_inicio) t;
    v_despesas := coalesce((select sum(c.valor) from public.conta c
                             where financeiro.pertence_ao_perfil(c.perfil_financeiro_id, p_perfil_id)
                               and date_trunc('month', c.mes_referencia) = v_inicio and c.is_fatura_cartao is not true
                               and c.status_pagamento is distinct from 'Substituida'), 0)  -- FIN-MVP-MOB-01
                + coalesce((select sum(d.valor_previsto) from public.despesa_prevista d
                             where financeiro.pertence_ao_perfil(d.perfil_financeiro_id, p_perfil_id)
                               and date_trunc('month', d.data_atual_prevista) = v_inicio
                               and d.status in ('PREVISTA', 'ADIADA')
                               and financeiro.prevista_financeira(d.origem_tipo, d.origem_id)), 0);  -- FIN-MVP-MOB-01

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

    -- _total_faturas_periodo (FIN-CARTAO-PREVISTO-EXECUTADO-01: executado atual, sem previsoes pendentes)
    select coalesce(sum(coalesce(nullif(c.valor_consolidado, 0), nullif(financeiro.executado_fatura(c.id), 0), nullif(c.valor_planejado, 0), c.valor, 0)), 0),
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
           and financeiro.natureza_da_compra(la.total_parcelas, la.is_recorrente, la.item_despesa_id, la.categoria_cartao_id) = 'CATEGORIA'  -- FIN-CARTAO-DESPESAS-FIXAS-01
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
                                -- FIN-CARTAO-DESPESAS-FIXAS-01: uso dos limites sem as obrigacoes ja contratadas
                                and financeiro.natureza_da_compra(la.total_parcelas, la.is_recorrente, la.item_despesa_id, la.categoria_cartao_id) not in ('PARCELADA', 'FIXA')
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
       and d.status in ('PREVISTA', 'ADIADA')
       and financeiro.prevista_financeira(d.origem_tipo, d.origem_id);  -- FIN-MVP-MOB-01
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
       and d.data_atual_prevista between v_inicio and v_fim
       and d.status <> 'SUPRIMIDA'
       and financeiro.prevista_financeira(d.origem_tipo, d.origem_id);  -- FIN-MVP-MOB-01

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
$function$;

drop function financeiro.previsto_fatura(integer);
