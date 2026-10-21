-- MOBILE-CONTAS-1 — contas do mes (somente leitura), por perfil financeiro.
--
-- NAO aplicar no Supabase remoto sem autorizacao especifica
-- (scripts/supabase_migrations.py aplicar --versoes 20261022090000).
-- Validada em cluster PostgreSQL local descartavel, com testes de equivalencia
-- contra o Flask (tests/test_supabase_contas_mes.py).
--
-- Reproduz a LEITURA de GET /api/despesas/?mes_referencia= do Flask
-- (backend/routes/despesas.py, listar_despesas), SEM os efeitos colaterais dele:
-- nao gera recorrencias nem faturas virtuais e nao baixa debito automatico.
--
-- Regras:
-- - competencia gravada: conta.mes_referencia (nao cartao) e conta.cartao_competencia
--   (faturas); nunca o mes do vencimento;
-- - perfil: o pedido, e o "Pessoal" tambem ve linhas com perfil NULL (condicao_perfil);
-- - fatura PAGA vale o executado; PENDENTE vale o previsto
--   (executado + soma de max(0, limite - gasto) por categoria de cartao com limite
--   ativo, como _calcular_totais_fatura_cartao_previsto; vigencia do limite e
--   ignorada, como no Flask);
-- - compras de cartao (lancamento_agregado) nao sao contas: so entram via fatura;
-- - situacao: PAGA se status 'Pago'; VENCIDA se 'Atrasado' ou nao paga com
--   vencimento antes de hoje em America/Sao_Paulo; senao PENDENTE.

create function financeiro.contas_do_mes(p_perfil_id integer, p_mes date)
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

-- Compras de UMA fatura do perfil (detalhe somente leitura).
create function financeiro.lancamentos_da_fatura(p_perfil_id integer, p_conta_id integer)
    returns table (
        id integer, descricao text, valor numeric, data_compra date,
        numero_parcela integer, total_parcelas integer, categoria_cartao text
    )
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_pessoal boolean;
    v_cartao integer;
    v_competencia date;
begin
    if not financeiro.pode_acessar_perfil(p_perfil_id) then
        raise exception 'Perfil financeiro nao autorizado' using errcode = '42501';
    end if;
    v_pessoal := exists (select 1 from public.perfil_financeiro p where p.id = p_perfil_id and p.nome = 'Pessoal');

    select c.item_despesa_id, date_trunc('month', c.cartao_competencia)::date
      into v_cartao, v_competencia
      from public.conta c
     where c.id = p_conta_id
       and c.is_fatura_cartao = true
       and (c.perfil_financeiro_id = p_perfil_id or (c.perfil_financeiro_id is null and v_pessoal));
    if v_cartao is null then
        -- Mesmo erro para "nao existe" e "de outro perfil": nao revela ids alheios.
        raise exception 'Fatura nao encontrada no perfil' using errcode = '42501';
    end if;

    return query
        select l.id, coalesce(nullif(l.descricao_exibida, ''), l.descricao)::text, l.valor, l.data_compra,
               l.numero_parcela, l.total_parcelas, cc.nome::text
          from public.lancamento_agregado l
          left join public.categoria_cartao cc on cc.id = l.categoria_cartao_id
         where l.cartao_id = v_cartao
           and l.mes_fatura = v_competencia
           and (l.perfil_financeiro_id = p_perfil_id or (l.perfil_financeiro_id is null and v_pessoal))
         order by l.data_compra, l.id;
end
$$;

-- D1: indicio (nao afirmacao) de competencia ainda nao gerada pelo Flask: alguma
-- despesa recorrente MENSAL ativa ja iniciada sem conta no mes, ou cartao ativo sem
-- fatura no mes. Mes vazio sem esse indicio nao gera aviso.
create function financeiro.mes_pode_estar_incompleto(p_perfil_id integer, p_mes date)
    returns boolean
    language plpgsql
    stable
    security definer
    set search_path = ''
as $$
declare
    v_mes date;
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

    return exists (
        select 1
          from public.item_despesa i
         where (i.perfil_financeiro_id = p_perfil_id or (i.perfil_financeiro_id is null and v_pessoal))
           and coalesce(i.ativo, true)
           and coalesce(i.recorrente, false)
           and coalesce(i.tipo_recorrencia, 'mensal') = 'mensal'
           and i.tipo <> 'Agregador'
           and i.data_vencimento is not null
           and date_trunc('month', i.data_vencimento) <= v_mes
           and not exists (select 1 from public.conta c
                            where c.item_despesa_id = i.id and date_trunc('month', c.mes_referencia) = v_mes)
    ) or exists (
        select 1
          from public.item_despesa cartao
         where (cartao.perfil_financeiro_id = p_perfil_id or (cartao.perfil_financeiro_id is null and v_pessoal))
           and cartao.tipo = 'Agregador'
           and coalesce(cartao.ativo, true)
           and not exists (select 1 from public.conta c
                            where c.item_despesa_id = cartao.id and c.is_fatura_cartao = true
                              and date_trunc('month', c.cartao_competencia) = v_mes)
    );
end
$$;

revoke execute on function financeiro.contas_do_mes(integer, date) from public, anon;
revoke execute on function financeiro.lancamentos_da_fatura(integer, integer) from public, anon;
revoke execute on function financeiro.mes_pode_estar_incompleto(integer, date) from public, anon;
grant execute on function financeiro.contas_do_mes(integer, date) to authenticated;
grant execute on function financeiro.lancamentos_da_fatura(integer, integer) to authenticated;
grant execute on function financeiro.mes_pode_estar_incompleto(integer, date) to authenticated;
