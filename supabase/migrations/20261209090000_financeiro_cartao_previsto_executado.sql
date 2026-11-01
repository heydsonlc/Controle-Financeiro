-- FIN-CARTAO-PREVISTO-EXECUTADO-01 — separacao definitiva entre previsao e execucao das despesas fixas do cartao.
--
-- NAO aplicar no Supabase remoto sem autorizacao especifica
-- (scripts/supabase_migrations.py aplicar --versoes 20261209090000).
-- Validada em cluster local descartavel (tests/test_supabase_cartao_previsto_executado.py) e ensaiada numa copia fiel
-- da producao. Doc: docs/FIN_CARTAO_DESPESAS_FIXAS_01.md (secao 7). Gerada por
-- scripts/gerar_migration_cartao_previsto_executado.py.
-- Reversao: supabase/reversao/20261209090000_cartao_previsto_executado_anterior.sql.
--
-- Regras:
-- - a compra que a recorrencia preve (gerada, ainda sem cobranca real) e PREVISTA: aparece no planejamento pelo valor
--   previsto, mas nao entra no executado da fatura nem no valor a pagar (pagamento, lista de Despesas, faturas do mes,
--   Cartoes, Dashboard);
-- - a cobranca real (importada, realizada ou conciliada) e CONFIRMADA: o executado e o valor cobrado; o previsto fica em
--   ocorrencia_recorrencia_cartao; o valor-base da recorrencia nao muda;
-- - previsto da fatura = executado + previsoes pendentes + o que falta dos limites (o valor exibido nao muda);
-- - pagamento: paga o executado; as previsoes ainda pendentes ficam NAO_COBRADA naquela fatura (gatilho em
--   pagamento_fatura) e voltam a aguardar cobranca no estorno; a cobranca que chegar depois entra como compra da
--   recorrencia na proxima fatura aberta;
-- - faturas pagas antes desta regra ficam como foram pagas (previsao em fatura paga = PAGA, executada);
-- - nenhum dado existente e alterado; o valor_executado gravado das faturas abertas se atualiza no proximo recalculo
--   (as telas e o pagamento usam o executado calculado na hora).
--
-- Funcoes existentes substituidas pelo texto vigente com os trechos marcados "FIN-CARTAO-PREVISTO-EXECUTADO-01": executado_fatura,
-- recalcular_fatura, contas_do_mes, faturas_do_mes, fatura_por_categoria, lancamentos_fatura_por_categoria,
-- dashboard_resumo_tela, analisar_importacao_cartao, reverter_ocorrencia_recorrencia; compras_da_fatura recriada (coluna
-- nova no fim: valor_executado).

-- =====================================================================================================================
-- 1. Situacao da previsao da recorrencia e executado da compra
-- =====================================================================================================================
-- Compra FIXA (recorrencia no cartao):
-- - CONFIRMADA: cobranca real importada, realizada ou conciliada (executado = valor da compra);
-- - PREVISTA: gerada pela recorrencia, sem cobranca, em fatura nao paga (executado = 0; o valor e o previsto);
-- - NAO_COBRADA: a fatura foi paga sem ela (marcada no pagamento; executado = 0; o estorno do pagamento a devolve);
-- - PAGA: em fatura paga antes desta regra (historico preservado: executado = valor, como foi pago).
-- Demais naturezas: sem situacao, executado = valor.
create function financeiro.situacao_previsao(p_lancamento_id integer, p_natureza text, p_importado boolean,
                                             p_cartao_id integer, p_mes_fatura date)
    returns text
    language sql
    stable
    set search_path = ''
as $$
    select case
               when p_natureza is distinct from 'FIXA' then null
               when coalesce(p_importado, false) then 'CONFIRMADA'
               else coalesce((select case o.origem when 'NAO_COBRADA' then 'NAO_COBRADA' else 'CONFIRMADA' end
                                from financeiro.ocorrencia_recorrencia_cartao o
                               where o.lancamento_id = p_lancamento_id and o.revertida_em is null),
                             case when coalesce(financeiro.fatura_esta_paga(financeiro.fatura_do_mes(p_cartao_id, p_mes_fatura)), false)
                                  then 'PAGA' else 'PREVISTA' end)
           end
$$;

create function financeiro.valor_executado_compra(p_valor numeric, p_situacao text)
    returns numeric
    language sql
    immutable
    set search_path = ''
as $$
    select case when p_situacao in ('PREVISTA', 'NAO_COBRADA') then 0 else coalesce(p_valor, 0) end
$$;

-- =====================================================================================================================
-- 2. Pagamento da fatura: previsoes sem cobranca ficam marcadas como nao cobradas; o estorno devolve
-- =====================================================================================================================
alter table financeiro.ocorrencia_recorrencia_cartao drop constraint ocorrencia_recorrencia_cartao_origem_check;
alter table financeiro.ocorrencia_recorrencia_cartao
    add constraint ocorrencia_recorrencia_cartao_origem_check check (origem in ('IMPORTACAO', 'CONCILIACAO', 'NAO_COBRADA')),
    add column pagamento_id bigint references financeiro.pagamento_fatura (id) on delete set null;
comment on column financeiro.ocorrencia_recorrencia_cartao.pagamento_id is
    'FIN-CARTAO-PREVISTO-EXECUTADO-01: pagamento da fatura que deixou a previsao sem cobranca (NAO_COBRADA).';

-- Gatilho em financeiro.pagamento_fatura (pagamento de fatura pelo novo aplicativo): o valor pago foi o executado, sem as
-- previsoes pendentes; elas ficam registradas como nao cobradas naquela fatura (executado 0, a fatura paga continua
-- igual ao que foi pago). No estorno do pagamento, as marcas daquele pagamento sao desfeitas (a previsao volta a
-- aguardar cobranca). Pagamentos de despesa e os registros de estorno do Flask nao sao afetados.
create function financeiro.previsoes_no_pagamento_da_fatura()
    returns trigger
    language plpgsql
    security definer
    set search_path = ''
as $$
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
$$;

create trigger previsoes_no_pagamento_da_fatura
    after insert or update of estorno_movimento_id on financeiro.pagamento_fatura
    for each row execute function financeiro.previsoes_no_pagamento_da_fatura();

-- =====================================================================================================================
-- 3. Leituras, pagamento e importacao: texto vigente + os trechos marcados
-- =====================================================================================================================

-- executado_fatura: texto de 20261031090000 + os trechos marcados.
create or replace function financeiro.executado_fatura(p_fatura_id integer)
    returns numeric
    language sql
    stable
    security definer
    set search_path = ''
as $$
    -- FIN-CARTAO-PREVISTO-EXECUTADO-01: previsao de recorrencia ainda sem cobranca (ou nao cobrada) nao e executada
    select coalesce(sum(financeiro.valor_executado_compra(l.valor, financeiro.situacao_previsao(l.id, financeiro.natureza_da_compra(l.total_parcelas, l.is_recorrente, l.item_despesa_id, l.categoria_cartao_id), l.is_importado, l.cartao_id, l.mes_fatura))), 0)
      from public.conta c
      join public.lancamento_agregado l on l.cartao_id = c.item_despesa_id and l.mes_fatura = c.cartao_competencia
     where c.id = p_fatura_id
       and financeiro.pertence_ao_perfil(l.perfil_financeiro_id, coalesce(c.perfil_financeiro_id,
               (select p.id from public.perfil_financeiro p where p.nome = 'Pessoal' order by p.id limit 1)))
$$;

-- recalcular_fatura: texto de 20261028090000 + os trechos marcados.
create or replace function financeiro.recalcular_fatura(p_perfil_id integer, p_cartao_id integer, p_competencia date)
    returns void
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
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
    update public.conta set valor_planejado = v_plan, valor_executado = v_exec, estouro_orcamento = v_exec > v_plan,
                            valor = v_plan
     where id = v_id;
end
$$;

-- contas_do_mes: texto de 20261208090000 + os trechos marcados.
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
               coalesce((select sum(g.total) from gastos g where g.cartao_id = c.item_despesa_id), 0) as executado,
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
$$;

-- faturas_do_mes: texto de 20261208090000 + os trechos marcados.
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
    select c.id, c.nome::text, f.id, v_mes, f.data_vencimento,
           case when f.id is null then 'SEM_FATURA'
                when f.status_pagamento = 'Pago' or f.status_fatura = 'PAGA' then 'PAGA'
                when f.status_fatura = 'FECHADA' then 'FECHADA' else 'ABERTA' end,
           coalesce((select sum(g.gasto) from gastos g where g.cartao_id = c.id), 0),
           case when f.status_pagamento = 'Pago' then coalesce((select sum(g.gasto) from gastos g where g.cartao_id = c.id), 0)
                else coalesce((select sum(g.gasto) from gastos g where g.cartao_id = c.id), 0)
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
$$;

-- fatura_por_categoria: texto de 20261208090000 + os trechos marcados.
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
    v_fixas      numeric;  -- FIN-CARTAO-DESPESAS-FIXAS-01
    v_parceladas numeric;
    v_pendente   numeric;  -- FIN-CARTAO-PREVISTO-EXECUTADO-01
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    perform financeiro.cartao_do_perfil(p_perfil_id, p_cartao_id, false);
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
    )
    select coalesce(jsonb_agg(jsonb_build_object(
               -- os grupos de parceladas e fixas levam o proprio filtro de "Ver lancamentos" (tela de Cartoes)
               'categoria_cartao_id', case when g.tipo in ('compras_parceladas', 'despesas_fixas') then to_jsonb(g.tipo)
                                           else to_jsonb(g.categoria_cartao_id) end,
               'categoria_cartao_nome', case g.tipo when 'sem_categoria' then 'Sem Categoria do Cartao'
                                                    when 'compras_parceladas' then 'Compras parceladas'
                                                    when 'despesas_fixas' then 'Despesas fixas'
                                                    else coalesce(cc.nome, 'Categoria do Cartao') end,
               'natureza', case g.tipo when 'compras_parceladas' then 'PARCELADA' when 'despesas_fixas' then 'FIXA'
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
                              else 'Revisar' end,
               'quantidade_lancamentos', g.qtd,
               'vinculada_ao_cartao', g.tipo = 'categoria_cartao',
               'sem_categoria', g.tipo = 'sem_categoria',
               'categoria_sem_limite', g.tipo = 'categoria_sem_limite',
               'avisos', case g.tipo when 'sem_categoria' then '["Lancamentos sem Categoria do Cartao devem ser revisados."]'::jsonb
                                     when 'categoria_sem_limite' then '["Categoria sem limite neste cartao."]'::jsonb
                                     when 'compras_parceladas' then '["Parcelas ja contratadas: nao consomem limite de Categoria do Cartao."]'::jsonb
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
        'total_fatura', v_total,
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
$$;

-- lancamentos_fatura_por_categoria: texto de 20261208090000 + os trechos marcados.
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
    if v_filtro not in ('todos', 'sem_categoria', 'despesas_fixas', 'compras_parceladas') then  -- FIN-CARTAO-DESPESAS-FIXAS-01
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
                       'natureza', nat.n,
                       -- FIN-CARTAO-PREVISTO-EXECUTADO-01: situacao da previsao, previsto e executado da compra
                       'situacao_ocorrencia', sit.s,
                       'valor_previsto', case when nat.n = 'FIXA' then coalesce((select o.valor_previsto
                           from financeiro.ocorrencia_recorrencia_cartao o where o.lancamento_id = l.id and o.revertida_em is null), l.valor) end,
                       'valor_executado', financeiro.valor_executado_compra(l.valor, sit.s),
                       'status_classificacao', case
                           when nat.n in ('PARCELADA', 'FIXA') then 'classificado'  -- nao precisam de Categoria do Cartao
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
             cross join lateral (select financeiro.natureza_da_compra(l.total_parcelas, l.is_recorrente, l.item_despesa_id, l.categoria_cartao_id) as n) nat
             cross join lateral (select financeiro.situacao_previsao(l.id, nat.n, l.is_importado, l.cartao_id, l.mes_fatura) as s) sit
             where l.cartao_id = p_cartao_id and l.mes_fatura = v_mes
               and financeiro.pertence_ao_perfil(l.perfil_financeiro_id, p_perfil_id)
               and (v_filtro = 'todos' or (v_filtro = 'sem_categoria' and nat.n = 'OUTROS')
                    or (v_filtro = 'despesas_fixas' and nat.n = 'FIXA')
                    or (v_filtro = 'compras_parceladas' and nat.n = 'PARCELADA')
                    or (nat.n = 'CATEGORIA' and l.categoria_cartao_id = v_cc))), '[]'::jsonb));
end
$$;

-- dashboard_resumo_tela: texto de 20261208090000 + os trechos marcados.
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

-- analisar_importacao_cartao: texto de 20261208090000 + os trechos marcados.
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
    v_cands     jsonb;    -- FIN-CARTAO-DESPESAS-FIXAS-01: recorrencias do cartao que combinam com a descricao
    v_desempate jsonb;
    v_texto     text;
    v_rec_cat   integer;
    v_rec_nome  text;
    v_realiza   integer;  -- compra prevista que esta linha realiza
    v_prev      numeric;
    v_occ       public.lancamento_agregado;
    v_fat_occ   integer;
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

        -- FIN-CARTAO-DESPESAS-FIXAS-01: recorrencia do cartao pela descricao. O nome da recorrencia ou um apelido de cobranca
        -- (financeiro.recorrencia_apelido) aparece como palavras inteiras no texto normalizado da linha: mesmo
        -- cartao, recorrencia ativa paga no cartao. O valor nunca identifica; so desempata quando ha mais de uma.
        v_cands := '[]'::jsonb;
        v_rec_cat := null;
        v_rec_nome := null;
        v_realiza := null;
        v_prev := null;
        v_texto := ' ' || financeiro.texto_cobranca(v_norm) || ' ';
        if v_tipo <> 'credito' and btrim(v_texto) <> '' then
            select coalesce(jsonb_agg(jsonb_build_object('id', i.id, 'nome', i.nome, 'categoria_id', i.categoria_id,
                                                         'valor', i.valor,
                                                         'exato', financeiro.texto_cobranca(i.nome) = btrim(v_texto)
                                                                  or exists (select 1 from financeiro.recorrencia_apelido a
                                                                              where a.item_despesa_id = i.id and a.ativo
                                                                                and a.apelido = btrim(v_texto)))
                                      order by i.id), '[]'::jsonb)
              into v_cands
              from public.item_despesa i
             where coalesce(i.recorrente, false) and coalesce(i.ativo, true) and i.tipo <> 'Agregador'
               and i.meio_pagamento = 'cartao' and i.cartao_id = p_cartao_id
               and financeiro.pertence_ao_perfil(i.perfil_financeiro_id, p_perfil_id)
               and ((financeiro.texto_cobranca(i.nome) <> ''
                     and position(' ' || financeiro.texto_cobranca(i.nome) || ' ' in v_texto) > 0)
                    or exists (select 1 from financeiro.recorrencia_apelido a
                                where a.item_despesa_id = i.id and a.ativo
                                  and position(' ' || a.apelido || ' ' in v_texto) > 0));
            -- Desempate: a que bate com o texto inteiro; depois, a de valor igual. Persistindo, nenhuma (revisar).
            if jsonb_array_length(v_cands) > 1 then
                select coalesce(jsonb_agg(c), '[]'::jsonb) into v_desempate
                  from jsonb_array_elements(v_cands) c where (c ->> 'exato')::boolean;
                if jsonb_array_length(v_desempate) = 1 then
                    v_cands := v_desempate;
                else
                    select coalesce(jsonb_agg(c), '[]'::jsonb) into v_desempate
                      from jsonb_array_elements(v_cands) c where (c ->> 'valor')::numeric = round(abs(v_bruto), 2);
                    if jsonb_array_length(v_desempate) = 1 then
                        v_cands := v_desempate;
                    end if;
                end if;
            end if;
        end if;
        v_rec := case when jsonb_array_length(v_cands) = 1 then (v_cands -> 0 ->> 'id')::integer end;
        v_rec_cat := (v_cands -> 0 ->> 'categoria_id')::integer;
        v_rec_nome := v_cands -> 0 ->> 'nome';

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
            -- FIN-CARTAO-DESPESAS-FIXAS-01: linha reconhecida como a recorrencia usa a Categoria de Despesa dela
            elsif v_rec is not null and exists (select 1 from public.categoria c where c.id = v_rec_cat and coalesce(c.ativo, true)) then
                v_cat := v_rec_cat;
                v_cat_origem := 'recorrencia';
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
                   and abs(l.data_compra - v_data) <= 5
                   -- FIN-CARTAO-DESPESAS-FIXAS-01: compra de recorrencia (prevista ou realizada) nunca e conciliada so pelo valor
                   -- (ChatGPT de R$ 109,90 nao e o Claude); ela e encontrada pela descricao, abaixo.
                   and not (coalesce(l.is_recorrente, false) and l.item_despesa_id is not null)
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

        -- FIN-CARTAO-DESPESAS-FIXAS-01: ocorrencia da recorrencia reconhecida pela descricao (acima). Com a previsao do mes ainda sem
        -- cobranca, a linha a realiza: a compra prevista fica (identidade da recorrencia) com o valor real, e o
        -- previsto vai para financeiro.ocorrencia_recorrencia_cartao. Previsao ja realizada, ou em fatura paga ou
        -- consolidada: a linha sai da efetivacao, a compra existente fica como esta.
        if v_status in ('ignorado', 'duplicado', 'conciliado') or v_norm = '' then
            v_rec := null;
        elsif jsonb_array_length(v_cands) > 1 then
            v_status := 'revisar';
            v_msgs := v_msgs || to_jsonb(format('Mais de uma recorrencia do cartao combina com a descricao (%s): a linha nao foi vinculada; revise os nomes ou os apelidos de cobranca.',
                (select string_agg(c ->> 'nome', ', ' order by (c ->> 'id')::integer) from jsonb_array_elements(v_cands) c)));
        elsif v_rec is not null then
            select l.* into v_occ
              from public.lancamento_agregado l
             where l.item_despesa_id = v_rec and l.cartao_id = p_cartao_id
               and coalesce(l.mes_fatura_original, l.mes_fatura) = v_comp
               -- FIN-CARTAO-PREVISTO-EXECUTADO-01: a previsao que a fatura paga deixou sem cobranca nao e a ocorrencia; a cobranca
               -- real que chega depois entra como compra da recorrencia (na proxima fatura aberta)
               and not exists (select 1 from financeiro.ocorrencia_recorrencia_cartao o
                                where o.lancamento_id = l.id and o.revertida_em is null and o.origem = 'NAO_COBRADA')
             order by l.id limit 1;
            if found then
                v_fat_occ := financeiro.fatura_do_mes(p_cartao_id, v_occ.mes_fatura);
                if coalesce(v_occ.is_recorrente, false) and coalesce(v_occ.total_parcelas, 1) = 1
                   and not coalesce(v_occ.is_importado, false)
                   and not exists (select 1 from financeiro.ocorrencia_recorrencia_cartao o
                                    where o.lancamento_id = v_occ.id and o.revertida_em is null)
                   and (v_fat_occ is null or not (financeiro.fatura_esta_paga(v_fat_occ)
                        or exists (select 1 from public.conta c where c.id = v_fat_occ and c.status_fatura = 'FECHADA'))) then
                    v_realiza := v_occ.id;
                    v_prev := v_occ.valor;
                    v_msgs := v_msgs || to_jsonb(format('Cobranca real da recorrencia "%s": confirma a previsao de R$ %s desta fatura (executado R$ %s%s).',
                        v_rec_nome, to_char(v_prev, 'FM999999990.00'), to_char(v_valor, 'FM999999990.00'),
                        case when v_valor <> v_prev then '; diferenca R$ ' || to_char(v_valor - v_prev, 'FM999999990.00') else '' end));
                else
                    v_conc := jsonb_build_object('lancamento_id', v_occ.id,
                                                 'descricao', coalesce(nullif(v_occ.descricao_exibida, ''), v_occ.descricao),
                                                 'data_compra', v_occ.data_compra, 'valor', v_occ.valor, 'categoria_id', v_occ.categoria_id,
                                                 'recorrente', true, 'mantida', false);
                    v_status := 'conciliado';
                    v_ignorar := true;
                    v_msgs := v_msgs || to_jsonb(format('Recorrencia ja lancada nesta fatura: %s (R$ %s); a compra existente fica como esta%s.',
                        v_conc ->> 'descricao', to_char((v_conc ->> 'valor')::numeric, 'FM999999990.00'),
                        case when (v_conc ->> 'valor')::numeric <> v_valor
                             then format(' (no arquivo, R$ %s: para corrigir, edite a compra)', to_char(v_valor, 'FM999999990.00'))
                             else '' end));
                    v_rec := null;
                end if;
            else
                v_msgs := v_msgs || to_jsonb(format('Reconhecida como compra recorrente do cartao ("%s"): o gerador nao a lanca de novo nesta competencia.', v_rec_nome));
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
            elsif v_rec is null then  -- FIN-CARTAO-DESPESAS-FIXAS-01: recorrencia nao precisa de Categoria do Cartao
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
            when v_rec is not null then 'classificada'
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
            'recorrencia_nome', case when v_rec is not null then v_rec_nome end,
            'recorrencias_candidatas', case when jsonb_array_length(v_cands) > 1 then v_cands end,
            'realiza_lancamento_id', v_realiza,
            'valor_previsto', v_prev,
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
            'realizacoes', count(*) filter (where l ->> 'realiza_lancamento_id' is not null and not (l ->> 'ignorar')::boolean),
            'sem_categoria_cartao', count(*) filter (where l ->> 'tipo_movimento' = 'debito'
                                                       and l ->> 'status' not in ('duplicado', 'ignorado', 'conciliado')
                                                       and l ->> 'categoria_cartao_id' is null
                                                       and l ->> 'recorrencia_id' is null and (l ->> 'total_parcelas')::integer <= 1),
            'total_importavel', coalesce(sum((l ->> 'valor')::numeric) filter (where l ->> 'tipo_movimento' = 'debito'
                                                       and not (l ->> 'ignorar')::boolean), 0),
            'creditos', count(*) filter (where l ->> 'tipo_movimento' = 'credito'),
            'total_creditos', coalesce(sum((l ->> 'valor')::numeric) filter (where l ->> 'tipo_movimento' = 'credito'), 0),
            'ignorados', count(*) filter (where l ->> 'status' = 'ignorado'))
            from jsonb_array_elements(v_saida) l));
end
$$;

-- reverter_ocorrencia_recorrencia: texto de 20261208090000 + os trechos marcados.
create or replace function financeiro.reverter_ocorrencia_recorrencia(p_perfil_id integer, p_ocorrencia_id bigint, p_chave uuid)
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = ''
as $$
declare
    v_anterior financeiro.operacao_cartao;
    v_oc       financeiro.ocorrencia_recorrencia_cartao;
    v_l        public.lancamento_agregado;
    v_antes    public.lancamento_agregado;
    v_abs      public.lancamento_agregado;
    v_fat      integer;
    v_res      jsonb;
begin
    perform financeiro.exigir_escrita_novo(p_perfil_id);
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
    perform pg_advisory_xact_lock(20261023, p_perfil_id);
    select * into v_oc from financeiro.ocorrencia_recorrencia_cartao where id = p_ocorrencia_id for update;
    if not found or v_oc.perfil_financeiro_id <> p_perfil_id then
        raise exception 'Ocorrencia nao encontrada neste perfil' using errcode = '42501';
    end if;
    if v_oc.revertida_em is not null then
        raise exception 'Ocorrencia ja revertida' using errcode = 'P0001';
    end if;
    if v_oc.origem = 'NAO_COBRADA' then  -- FIN-CARTAO-PREVISTO-EXECUTADO-01: desfeita so pelo estorno do pagamento da fatura
        raise exception 'Previsao nao cobrada no pagamento da fatura: e desfeita pelo estorno do pagamento' using errcode = 'P0001';
    end if;
    select * into v_l from public.lancamento_agregado where id = v_oc.lancamento_id for update;
    if not found then
        raise exception 'A compra da ocorrencia foi excluida: nada a reverter' using errcode = 'P0001';
    end if;
    v_antes := jsonb_populate_record(null::public.lancamento_agregado, v_oc.lancamento_antes);
    if v_l.valor <> v_oc.valor_executado or v_l.mes_fatura <> v_antes.mes_fatura or v_l.cartao_id <> v_antes.cartao_id then
        raise exception 'A compra foi alterada depois da conciliacao: a reversao nao e feita' using errcode = 'P0001';
    end if;
    v_fat := financeiro.fatura_do_mes(v_l.cartao_id, v_l.mes_fatura);
    perform 1 from public.conta where id = v_fat for update;
    if v_fat is not null and (financeiro.fatura_esta_paga(v_fat)
                              or exists (select 1 from public.conta c where c.id = v_fat and c.status_fatura = 'FECHADA')) then
        raise exception 'A fatura de % esta paga ou consolidada: a reversao nao e feita', to_char(v_l.mes_fatura, 'MM/YYYY')
            using errcode = 'P0001';
    end if;
    update public.lancamento_agregado
       set valor = v_antes.valor, data_compra = v_antes.data_compra, descricao_original = v_antes.descricao_original,
           descricao_original_normalizada = v_antes.descricao_original_normalizada, is_importado = v_antes.is_importado,
           origem_importacao = v_antes.origem_importacao
     where id = v_l.id;
    if v_oc.lancamento_absorvido is not null then
        v_abs := jsonb_populate_record(null::public.lancamento_agregado, v_oc.lancamento_absorvido);
        if exists (select 1 from public.lancamento_agregado where id = v_abs.id) then
            raise exception 'Ja existe compra com o id da cobranca absorvida (%)', v_abs.id using errcode = 'P0001';
        end if;
        insert into public.lancamento_agregado select (v_abs).*;
    end if;
    update financeiro.ocorrencia_recorrencia_cartao set revertida_em = now(), revertida_por = (select auth.uid())
     where id = v_oc.id;
    perform financeiro.recalcular_fatura(p_perfil_id, v_l.cartao_id, v_l.mes_fatura);
    v_res := jsonb_build_object('ocorrencia_id', v_oc.id, 'lancamento_id', v_l.id, 'valor_restaurado', v_antes.valor,
                                'cobranca_restaurada_id', v_abs.id);
    insert into financeiro.operacao_cartao (chave, user_id, perfil_financeiro_id, operacao, resultado)
    values (p_chave, (select auth.uid()), p_perfil_id, 'reverter_ocorrencia_recorrencia', v_res);
    return v_res;
end
$$;

-- compras_da_fatura: texto de 20261208090000 + situacao e executado da compra (tipo de retorno muda).
drop function financeiro.compras_da_fatura(integer, integer, date);

create function financeiro.compras_da_fatura(p_perfil_id integer, p_cartao_id integer, p_mes date)
    returns table (id integer, descricao text, valor numeric, data_compra date, numero_parcela integer,
                   total_parcelas integer, categoria_nome text, recorrente boolean, bloqueio text, pode_editar boolean,
                   categoria_cartao_id integer, valor_previsto numeric, natureza text, situacao_ocorrencia text,
                   valor_executado numeric)
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
               l.categoria_cartao_id,
               -- FIN-CARTAO-DESPESAS-FIXAS-01: previsto da ocorrencia (o valor antes da cobranca real; sem cobranca, o proprio valor)
               case when nat.n = 'FIXA' then coalesce(o.valor_previsto, l.valor) when nat.n = 'PARCELADA' then l.valor end,
               nat.n,
               sit.s,  -- FIN-CARTAO-PREVISTO-EXECUTADO-01
               financeiro.valor_executado_compra(l.valor, sit.s)
          from public.lancamento_agregado l
          left join public.categoria cat on cat.id = l.categoria_id
          left join financeiro.ocorrencia_recorrencia_cartao o on o.lancamento_id = l.id and o.revertida_em is null
         cross join lateral (select financeiro.natureza_da_compra(l.total_parcelas, l.is_recorrente, l.item_despesa_id, l.categoria_cartao_id) as n) nat
         cross join lateral (select financeiro.situacao_previsao(l.id, nat.n, l.is_importado, l.cartao_id, l.mes_fatura) as s) sit
         where l.cartao_id = p_cartao_id and l.mes_fatura = date_trunc('month', p_mes::timestamp)::date
           and (l.perfil_financeiro_id = p_perfil_id or (l.perfil_financeiro_id is null and v_pessoal))
         order by l.data_compra, l.id;
end
$$;

-- Internas: sem EXECUTE para o navegador.
revoke execute on function financeiro.situacao_previsao(integer, text, boolean, integer, date) from public, anon, authenticated;
revoke execute on function financeiro.valor_executado_compra(numeric, text) from public, anon, authenticated;
revoke execute on function financeiro.previsoes_no_pagamento_da_fatura() from public, anon, authenticated;
revoke execute on function financeiro.compras_da_fatura(integer, integer, date) from public, anon;
grant execute on function financeiro.compras_da_fatura(integer, integer, date) to authenticated;
